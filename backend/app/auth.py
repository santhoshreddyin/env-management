"""Authentication and role-based access.

SSO (OIDC or SAML) is terminated by the platform gateway or an auth proxy such as
oauth2-proxy, which forwards the user identity and group membership as headers
(`AUTH_MODE=header`). For local development `AUTH_MODE=dev` runs every request as a
fixed user.
"""

import re
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status

from app.config import settings

VIEWER = "viewer"
MAINTAINER = "maintainer"


@dataclass
class User:
    name: str
    roles: set[str] = field(default_factory=set)

    @property
    def is_maintainer(self) -> bool:
        return MAINTAINER in self.roles


def _split_groups(raw: str) -> set[str]:
    return {g for g in re.split(r"[,\s]+", raw) if g}


def get_current_user(request: Request) -> User:
    if settings.auth_mode == "header":
        name = (request.headers.get(settings.auth_user_header) or "").strip()
        if not name:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
        groups = _split_groups(request.headers.get(settings.auth_groups_header, ""))
        roles: set[str] = set()
        if groups & set(settings.maintainer_groups):
            roles |= {MAINTAINER, VIEWER}
        if not settings.viewer_groups or groups & set(settings.viewer_groups):
            roles.add(VIEWER)
        return User(name=name, roles=roles)

    roles = set(settings.dev_roles)
    if MAINTAINER in roles:
        roles.add(VIEWER)
    return User(name=settings.dev_user, roles=roles)


def require_viewer(user: User = Depends(get_current_user)) -> User:
    if VIEWER not in user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewer role required")
    return user


def require_maintainer(user: User = Depends(get_current_user)) -> User:
    if MAINTAINER not in user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Maintainer role required")
    return user
