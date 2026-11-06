"""Authentication and role-based access (GOV-01, INT-05).

SSO (OIDC or SAML) is terminated by the platform gateway or an auth proxy such as
oauth2-proxy, which forwards the user identity and group membership as headers
(`AUTH_MODE=header`). For local development `AUTH_MODE=dev` runs every request as a
fixed user. Pipelines and integrations authenticate with API tokens
(`Authorization: Bearer emt_...`).

Roles, lowest to highest: viewer < booker < contributor < env_manager < admin. The
legacy "maintainer" role (integration data editing) is equivalent to admin. Roles come
from the user's groups (settings) and from role assignments stored in the database,
which can be scoped to an environment, programme (portfolio), region or family.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db

VIEWER = "viewer"
BOOKER = "booker"
CONTRIBUTOR = "contributor"
ENV_MANAGER = "env_manager"
ADMIN = "admin"
MAINTAINER = "maintainer"

LEVELS = {VIEWER: 1, BOOKER: 2, CONTRIBUTOR: 3, ENV_MANAGER: 4, ADMIN: 5, MAINTAINER: 5}
ROLES = [VIEWER, BOOKER, CONTRIBUTOR, ENV_MANAGER, ADMIN]
SCOPE_TYPES = ["global", "environment", "programme", "region", "family"]


@dataclass
class Assignment:
    role: str
    scope_type: str
    scope_value: str | None


@dataclass
class User:
    name: str
    roles: set[str] = field(default_factory=set)
    groups: set[str] = field(default_factory=set)
    assignments: list[Assignment] = field(default_factory=list)
    is_token: bool = False

    @property
    def is_maintainer(self) -> bool:
        return MAINTAINER in self.roles

    @property
    def global_level(self) -> int:
        levels = [LEVELS.get(r, 0) for r in self.roles]
        levels += [LEVELS.get(a.role, 0) for a in self.assignments if a.scope_type == "global"]
        return max(levels, default=0)

    def level_for(self, env: Any | None) -> int:
        """Effective role level for an environment (anything with name/id/programme/region/family)."""
        level = self.global_level
        if env is None:
            return level
        for a in self.assignments:
            if a.scope_type == "global" or a.scope_value is None:
                continue
            value = a.scope_value.lower()
            target = {
                "environment": [str(getattr(env, "id", "")), (getattr(env, "name", "") or "").lower()],
                "programme": [(getattr(env, "programme", "") or "").lower()],
                "region": [(getattr(env, "region", "") or "").lower()],
                "family": [(getattr(env, "family", "") or "").lower()],
            }.get(a.scope_type, [])
            if value in target:
                level = max(level, LEVELS.get(a.role, 0))
        return level

    def can(self, level: str, env: Any | None = None) -> bool:
        return self.level_for(env) >= LEVELS[level]

    def can_see(self, env: Any) -> bool:
        """Portfolio segregation (GOV-06): when on, only admins and users with a scoped role see an environment."""
        if not settings.portfolio_segregation:
            return self.has_any_role
        if self.global_level >= LEVELS[ADMIN]:
            return True
        scoped = User(self.name, set(), self.groups, [a for a in self.assignments if a.scope_type != "global"])
        return scoped.level_for(env) >= 1

    @property
    def has_any_role(self) -> bool:
        return self.global_level >= 1 or bool(self.assignments)

    @property
    def role_label(self) -> str:
        lvl = self.global_level
        for r in reversed(ROLES):
            if LEVELS[r] <= lvl:
                return r
        return "none"


def _split_groups(raw: str) -> set[str]:
    return {g for g in re.split(r"[,\s]+", raw) if g}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _token_user(token: str, db: Session) -> User:
    from app.models import ApiToken

    row = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(token), ApiToken.revoked.is_(False)))
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API token")
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return User(name=f"token:{row.name}", roles={row.role, VIEWER}, is_token=True)


def _load_assignments(db: Session, name: str, groups: set[str]) -> list[Assignment]:
    from app.models import RoleAssignment

    principals = [name] + [f"group:{g}" for g in groups]
    try:
        rows = db.scalars(select(RoleAssignment).where(RoleAssignment.principal.in_(principals))).all()
    except Exception:  # table missing (very old database before migration)
        db.rollback()
        return []
    return [Assignment(r.role, r.scope_type, r.scope_value) for r in rows]


def _group_roles(groups: set[str]) -> set[str]:
    roles: set[str] = set()
    mapping = [
        (settings.maintainer_groups, {MAINTAINER, ADMIN}),
        (settings.admin_groups, {ADMIN, MAINTAINER}),
        (settings.env_manager_groups, {ENV_MANAGER}),
        (settings.contributor_groups, {CONTRIBUTOR}),
        (settings.booker_groups, {BOOKER}),
    ]
    for configured, granted in mapping:
        if groups & set(configured):
            roles |= granted
    if not settings.viewer_groups or groups & set(settings.viewer_groups):
        roles.add(VIEWER)
    return roles


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("X-API-Token", "")
    if token.startswith("emt_"):
        return _token_user(token, db)

    if settings.auth_mode == "header":
        name = (request.headers.get(settings.auth_user_header) or "").strip()
        if not name:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
        groups = _split_groups(request.headers.get(settings.auth_groups_header, ""))
        roles = _group_roles(groups)
        if roles & {MAINTAINER, ADMIN}:
            roles.add(VIEWER)
        return User(name=name, roles=roles, groups=groups, assignments=_load_assignments(db, name, groups))

    roles = set(settings.dev_roles)
    if roles & {MAINTAINER, ADMIN}:
        roles |= {MAINTAINER, ADMIN}
    if roles:
        roles.add(VIEWER)
    return User(name=settings.dev_user, roles=roles, assignments=_load_assignments(db, settings.dev_user, set()))


def require_viewer(user: User = Depends(get_current_user)) -> User:
    if not user.has_any_role:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewer role required")
    return user


def require_maintainer(user: User = Depends(get_current_user)) -> User:
    if MAINTAINER not in user.roles and ADMIN not in user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Maintainer role required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.global_level < LEVELS[ADMIN]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    return user


def check(user: User, level: str, env: Any | None = None, action: str = "do this") -> None:
    """Raise 403 unless the user holds `level` (globally or for `env`)."""
    if not user.can(level, env):
        where = f" for {getattr(env, 'name', None)}" if env is not None and getattr(env, "name", None) else ""
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"The {level} role{where} is required to {action}")
