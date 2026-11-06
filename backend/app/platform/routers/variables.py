"""Configuration and variables (CFG-01..09) and secret references (SEC-01..05)."""

import csv
import io
import json
from datetime import datetime
from typing import Any, Literal

import yaml
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import CONTRIBUTOR, ENV_MANAGER, User, check, require_viewer
from app.database import get_db
from app.models import (
    ApprovalRequest,
    BulkOperation,
    ConfigTemplateKey,
    Environment,
    SystemInstance,
    Variable,
    VariableHistory,
)
from app.platform.common import apply, audit, aware, bump, check_version, get_or_404, now, policy
from app.platform.notify import emit
from app.platform.routers.environments import get_env, resolve_env
from app.platform.services import credential_warnings, effective_config

router = APIRouter(tags=["configuration"])

KEY_PATTERN = r"^[A-Za-z_][A-Za-z0-9_.\-]*$"
MASK = "••••••••"
META = ["description", "owner", "value_type", "sensitivity", "vault_ref", "last_rotated_at", "rotation_due_at",
        "rotation_owner"]


class VariableIn(BaseModel):
    key: str = Field(min_length=1, max_length=255, pattern=KEY_PATTERN)
    value: str = ""
    is_secret: bool = False
    description: str | None = None
    owner: str | None = None
    value_type: Literal["string", "number", "boolean", "url", "json"] = "string"
    sensitivity: Literal["public", "internal", "confidential", "restricted"] = "internal"
    vault_ref: str | None = None
    last_rotated_at: datetime | None = None
    rotation_due_at: datetime | None = None
    rotation_owner: str | None = None


class VariablePatch(BaseModel):
    key: str | None = Field(default=None, min_length=1, max_length=255, pattern=KEY_PATTERN)
    value: str | None = None
    is_secret: bool | None = None
    description: str | None = None
    owner: str | None = None
    value_type: Literal["string", "number", "boolean", "url", "json"] | None = None
    sensitivity: Literal["public", "internal", "confidential", "restricted"] | None = None
    vault_ref: str | None = None
    last_rotated_at: datetime | None = None
    rotation_due_at: datetime | None = None
    rotation_owner: str | None = None
    row_version: int | None = None


def var_out(v: Variable, reveal: bool = False, warnings: list[str] | None = None) -> dict[str, Any]:
    secret = v.is_secret
    return {
        "id": v.id, "environment_id": v.environment_id, "instance_id": v.instance_id, "key": v.key,
        "value": v.value if (not secret or reveal) else ("" if not v.value else MASK),
        "masked": secret and not reveal, "is_secret": secret,
        "scope": "instance" if v.instance_id else ("environment" if v.environment_id else "global"),
        **{m: getattr(v, m) for m in META},
        "last_rotated_at": aware(v.last_rotated_at), "rotation_due_at": aware(v.rotation_due_at),
        "rotation_overdue": bool(secret and v.rotation_due_at and aware(v.rotation_due_at) < now()),
        "row_version": v.row_version, "updated_at": aware(v.updated_at), "updated_by": v.updated_by,
        "created_at": aware(v.created_at), "warnings": warnings or [],
    }


def _validate_value(key: str, value: str, value_type: str) -> None:
    if not value:
        return
    try:
        if value_type == "number":
            float(value)
        elif value_type == "boolean" and value.lower() not in ("true", "false", "1", "0", "yes", "no"):
            raise ValueError
        elif value_type == "json":
            json.loads(value)
        elif value_type == "url" and "://" not in value:
            raise ValueError
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"value: '{key}' must be a valid {value_type}") from None


def _scope_filter(env_id: int | None, instance_id: int | None):
    if instance_id is not None:
        return Variable.instance_id == instance_id
    if env_id is None:
        return (Variable.environment_id.is_(None)) & (Variable.instance_id.is_(None))
    return (Variable.environment_id == env_id) & (Variable.instance_id.is_(None))


def _ensure_unique(db: Session, env_id: int | None, instance_id: int | None, key: str, exclude: int | None = None):
    existing = db.scalar(select(Variable).where(_scope_filter(env_id, instance_id), Variable.key == key))
    if existing is not None and existing.id != exclude:
        where = "this instance" if instance_id else ("this environment" if env_id else "global defaults")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Variable '{key}' already exists in {where}")


def _history(db: Session, v: Variable, action: str, user: User, old: str | None, new: str | None,
             changes: dict | None = None) -> None:
    db.add(VariableHistory(variable_id=v.id, environment_id=v.environment_id, instance_id=v.instance_id, key=v.key,
                           action=action, user=user.name, is_secret=v.is_secret,
                           old_value=None if v.is_secret else old, new_value=None if v.is_secret else new,
                           changes=changes))


def _protected(db: Session, env: Environment | None) -> bool:
    return env is not None and env.env_type in (policy(db, "protected_types") or [])


def _env_for_scope(db: Session, env_id: int | None, instance_id: int | None, user: User) -> Environment | None:
    if instance_id is not None:
        inst = get_or_404(db, SystemInstance, instance_id, "Instance")
        return get_env(db, inst.environment_id, user)
    return get_env(db, env_id, user) if env_id is not None else None


def create_var(db: Session, user: User, env_id: int | None, instance_id: int | None, payload: VariableIn,
               action: str = "create") -> Variable:
    env = _env_for_scope(db, env_id, instance_id, user)
    check(user, ENV_MANAGER if (env is None or _protected(db, env)) else CONTRIBUTOR, env, "change configuration")
    _ensure_unique(db, env.id if env else None, instance_id, payload.key)
    _validate_value(payload.key, payload.value, payload.value_type)
    data = payload.model_dump()
    if payload.is_secret and payload.vault_ref:
        data["value"] = ""  # SEC-01: secrets are held by vault reference, not value
    v = Variable(environment_id=env.id if env else None, instance_id=instance_id, updated_by=user.name, **data)
    db.add(v)
    db.flush()
    _history(db, v, action, user, None, v.value)
    audit(db, user, f"variable_{action}", "variable", v.id, {"key": v.key, "environment_id": v.environment_id,
                                                            "instance_id": instance_id, "secret": v.is_secret})
    return v


def update_var(db: Session, user: User, v: Variable, payload: VariablePatch) -> Variable:
    env = _env_for_scope(db, v.environment_id, v.instance_id, user)
    check(user, ENV_MANAGER if (env is None or _protected(db, env)) else CONTRIBUTOR, env, "change configuration")
    check_version(v, payload.row_version)
    data = payload.model_dump(exclude_unset=True, exclude={"row_version"})
    if "key" in data:
        _ensure_unique(db, v.environment_id, v.instance_id, data["key"], exclude=v.id)
    _validate_value(data.get("key", v.key), data.get("value", v.value) or "", data.get("value_type", v.value_type))
    if v.is_secret and data.get("value") == MASK:
        data.pop("value")  # the masked placeholder was echoed back unchanged
    old_value = v.value
    diff = apply(v, data)
    if v.is_secret and v.vault_ref:
        v.value = ""
    if diff:
        bump(v, user)
        meta = {k: [str(a) if a is not None else None, str(b) if b is not None else None]
                for k, (a, b) in diff.items() if k != "value"}
        _history(db, v, "update", user, old_value, v.value, meta or None)
        audit(db, user, "variable_update", "variable", v.id,
              {"key": v.key, "environment_id": v.environment_id, "fields": list(diff)})
    return v


def delete_var(db: Session, user: User, v: Variable) -> None:
    env = _env_for_scope(db, v.environment_id, v.instance_id, user)
    check(user, ENV_MANAGER if (env is None or _protected(db, env)) else CONTRIBUTOR, env, "change configuration")
    _history(db, v, "delete", user, v.value, None)
    audit(db, user, "variable_delete", "variable", v.id, {"key": v.key, "environment_id": v.environment_id})
    db.delete(v)


def _get_var(db: Session, var_id: int, env_id: int | None = None) -> Variable:
    v = db.get(Variable, var_id)
    if v is None or (env_id is not None and (v.environment_id != env_id or v.instance_id is not None)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variable not found")
    return v


# --- Environment-scoped CRUD (CFG-01) ---------------------------------------------------


@router.get("/environments/{env_id}/variables")
def list_variables(env_id: int, q: str | None = None, user: User = Depends(require_viewer),
                   db: Session = Depends(get_db)):
    get_env(db, env_id, user)
    query = select(Variable).where(_scope_filter(env_id, None)).order_by(Variable.key)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(Variable.key.ilike(like), Variable.description.ilike(like)))
    return [var_out(v) for v in db.scalars(query)]


@router.post("/environments/{env_id}/variables", status_code=status.HTTP_201_CREATED)
def create_variable(env_id: int, payload: VariableIn, user: User = Depends(require_viewer),
                    db: Session = Depends(get_db)):
    v = create_var(db, user, env_id, None, payload)
    warnings = credential_warnings(v.key, v.value, v.is_secret)
    _config_changed(db, v.environment, f"{v.key} added")
    db.commit()
    return var_out(v, warnings=warnings)


@router.patch("/environments/{env_id}/variables/{var_id}")
def update_variable(env_id: int, var_id: int, payload: VariablePatch, user: User = Depends(require_viewer),
                    db: Session = Depends(get_db)):
    v = update_var(db, user, _get_var(db, var_id, env_id), payload)
    _config_changed(db, v.environment, f"{v.key} changed")
    db.commit()
    return var_out(v, warnings=credential_warnings(v.key, v.value, v.is_secret))


@router.delete("/environments/{env_id}/variables/{var_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variable(env_id: int, var_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    v = _get_var(db, var_id, env_id)
    env = v.environment
    delete_var(db, user, v)
    _config_changed(db, env, f"{v.key} deleted")
    db.commit()


def _config_changed(db: Session, env: Environment | None, what: str) -> None:
    emit(db, "config.changed", f"Configuration changed{' in ' + env.name if env else ' (global)'}", what,
         environment=env, entity_type="environment", entity_id=env.id if env else None)


# --- Global and instance scopes (CFG-02) ------------------------------------------------


@router.get("/global-variables")
def list_global(_: User = Depends(require_viewer), db: Session = Depends(get_db)):
    return [var_out(v) for v in db.scalars(select(Variable).where(_scope_filter(None, None)).order_by(Variable.key))]


@router.post("/global-variables", status_code=status.HTTP_201_CREATED)
def create_global(payload: VariableIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    v = create_var(db, user, None, None, payload)
    db.commit()
    return var_out(v, warnings=credential_warnings(v.key, v.value, v.is_secret))


@router.get("/instances/{instance_id}/variables")
def list_instance_vars(instance_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    _env_for_scope(db, None, instance_id, user)
    return [var_out(v) for v in db.scalars(select(Variable).where(Variable.instance_id == instance_id)
                                           .order_by(Variable.key))]


@router.post("/instances/{instance_id}/variables", status_code=status.HTTP_201_CREATED)
def create_instance_var(instance_id: int, payload: VariableIn, user: User = Depends(require_viewer),
                        db: Session = Depends(get_db)):
    v = create_var(db, user, None, instance_id, payload)
    db.commit()
    return var_out(v, warnings=credential_warnings(v.key, v.value, v.is_secret))


@router.patch("/variables/{var_id}")
def patch_any_variable(var_id: int, payload: VariablePatch, user: User = Depends(require_viewer),
                       db: Session = Depends(get_db)):
    v = update_var(db, user, _get_var(db, var_id), payload)
    db.commit()
    return var_out(v, warnings=credential_warnings(v.key, v.value, v.is_secret))


@router.delete("/variables/{var_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_any_variable(var_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    delete_var(db, user, _get_var(db, var_id))
    db.commit()


@router.get("/variables/search")
def search_variables(q: str = Query(min_length=1), user: User = Depends(require_viewer),
                     db: Session = Depends(get_db)):
    like = f"%{q.lower()}%"
    rows = db.scalars(select(Variable).where(or_(Variable.key.ilike(like), Variable.description.ilike(like),
                                                 (Variable.is_secret.is_(False)) & Variable.value.ilike(like)))
                      .order_by(Variable.key).limit(200)).all()
    names = {e.id: e for e in db.scalars(select(Environment))}
    return [var_out(v) | {"environment": names[v.environment_id].name if v.environment_id in names else None}
            for v in rows if v.environment_id is None or (v.environment_id in names and user.can_see(names[v.environment_id]))]


# --- Reveal (SEC-02) and history (CFG-05) -----------------------------------------------


@router.post("/variables/{var_id}/reveal")
def reveal(var_id: int, reason: str | None = None, user: User = Depends(require_viewer),
           db: Session = Depends(get_db)):
    """Controlled, logged reveal of a secret value (or its vault reference)."""
    v = _get_var(db, var_id)
    env = _env_for_scope(db, v.environment_id, v.instance_id, user)
    check(user, CONTRIBUTOR, env, "reveal secret values")
    audit(db, user, "secret_reveal", "variable", v.id, {"key": v.key, "environment_id": v.environment_id,
                                                        "reason": reason})
    db.commit()
    return {"id": v.id, "key": v.key, "value": v.value, "vault_ref": v.vault_ref}


@router.get("/variables/{var_id}/history")
def variable_history(var_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    rows = db.scalars(select(VariableHistory).where(VariableHistory.variable_id == var_id)
                      .order_by(VariableHistory.id.desc())).all()
    if rows and rows[0].environment_id:
        env = db.get(Environment, rows[0].environment_id)
        if env and not user.can_see(env):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Variable not found")
    return [_hist_out(h) for h in rows]


def _hist_out(h: VariableHistory) -> dict[str, Any]:
    return {"id": h.id, "variable_id": h.variable_id, "environment_id": h.environment_id, "key": h.key,
            "action": h.action, "at": aware(h.at), "user": h.user, "is_secret": h.is_secret,
            "old_value": h.old_value, "new_value": h.new_value, "changes": h.changes,
            "restorable": not h.is_secret and h.action in ("update", "delete", "import", "copy")}


@router.get("/environments/{env_id}/variable-history")
def environment_history(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    get_env(db, env_id, user)
    rows = db.scalars(select(VariableHistory).where(VariableHistory.environment_id == env_id)
                      .order_by(VariableHistory.id.desc()).limit(500))
    return [_hist_out(h) for h in rows]


@router.post("/variables/history/{history_id}/restore")
def restore_history(history_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Restore the value a variable had before this change (re-creating it if it was deleted)."""
    h = get_or_404(db, VariableHistory, history_id, "History entry")
    if h.is_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "Secret values are not kept in history; re-enter the secret")
    v = db.get(Variable, h.variable_id)
    target = h.old_value if h.action != "create" else h.new_value
    if v is None:
        payload = VariableIn(key=h.key, value=target or "")
        v = create_var(db, user, h.environment_id if h.instance_id is None else None, h.instance_id, payload,
                       action="restore")
    else:
        update_var(db, user, v, VariablePatch(value=target or ""))
        v_hist = db.scalars(select(VariableHistory).where(VariableHistory.variable_id == v.id)
                            .order_by(VariableHistory.id.desc())).first()
        if v_hist is not None and v_hist.action == "update":
            v_hist.action = "restore"
    db.commit()
    return var_out(v)


# --- Effective config, comparison, templates (CFG-02/04/08/09) --------------------------


@router.get("/environments/{env_id}/config")
def environment_config(env_id: int, instance_id: int | None = None, user: User = Depends(require_viewer),
                       db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    return [var_out(r["variable"]) | {"source": r["source"], "overrides": r["overrides"]}
            for r in effective_config(db, env, instance_id)]


@router.get("/config/compare")
def compare_config(env_ids: str = Query(..., description="Comma-separated environment ids (2 or more)"),
                   effective: bool = True, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """CFG-04: keys × environments with differences and missing keys. Secrets compare equal/different only."""
    ids = [int(x) for x in env_ids.split(",") if x.strip()]
    if len(ids) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "env_ids: choose at least two environments")
    envs = [get_env(db, i, user) for i in ids]
    columns: dict[int, dict[str, Variable]] = {}
    for e in envs:
        if effective:
            columns[e.id] = {r["variable"].key: r["variable"] for r in effective_config(db, e)}
        else:
            columns[e.id] = {v.key: v for v in db.scalars(select(Variable).where(_scope_filter(e.id, None)))}
    keys = sorted(set().union(*[c.keys() for c in columns.values()]))
    rows = []
    for k in keys:
        cells = {}
        values = []
        secret = False
        for e in envs:
            v = columns[e.id].get(k)
            if v is None:
                cells[str(e.id)] = None
                continue
            secret = secret or v.is_secret
            fingerprint = ("vault:" + v.vault_ref) if v.vault_ref else v.value
            values.append(fingerprint)
            cells[str(e.id)] = {"value": MASK if v.is_secret else v.value, "is_secret": v.is_secret,
                                "scope": "global" if v.environment_id is None else "environment"}
        missing = [e.name for e in envs if columns[e.id].get(k) is None]
        rows.append({"key": k, "cells": cells, "missing_in": missing, "is_secret": secret,
                     "differs": bool(missing) or len(set(values)) > 1})
    return {"environments": [{"id": e.id, "name": e.name} for e in envs], "rows": rows,
            "summary": {"keys": len(rows), "different": sum(r["differs"] for r in rows),
                        "missing": sum(bool(r["missing_in"]) for r in rows)}}


class TemplateKeyIn(BaseModel):
    env_type: str
    key: str = Field(min_length=1, max_length=255, pattern=KEY_PATTERN)
    required: bool = True
    is_secret: bool = False
    default_value: str | None = None
    description: str | None = None


@router.get("/config-templates")
def list_templates(_: User = Depends(require_viewer), db: Session = Depends(get_db)):
    return [{c.name: getattr(t, c.name) for c in ConfigTemplateKey.__table__.columns}
            for t in db.scalars(select(ConfigTemplateKey).order_by(ConfigTemplateKey.env_type, ConfigTemplateKey.key))]


@router.post("/config-templates", status_code=status.HTTP_201_CREATED)
def add_template(payload: TemplateKeyIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    check(user, ENV_MANAGER, None, "edit configuration templates")
    t = ConfigTemplateKey(**payload.model_dump())
    db.add(t)
    audit(db, user, "template_add", "config_template", payload.key, payload.model_dump())
    db.commit()
    return {"id": t.id, **payload.model_dump()}


@router.delete("/config-templates/{tid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(tid: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    check(user, ENV_MANAGER, None, "edit configuration templates")
    t = get_or_404(db, ConfigTemplateKey, tid, "Template key")
    audit(db, user, "template_delete", "config_template", t.key, {"env_type": t.env_type})
    db.delete(t)
    db.commit()


def template_check(db: Session, env: Environment) -> dict[str, Any]:
    keys = db.scalars(select(ConfigTemplateKey).where(ConfigTemplateKey.env_type.in_([env.env_type, "*"]))).all()
    present = {r["variable"].key: r["variable"] for r in effective_config(db, env)}
    missing, empty = [], []
    for t in keys:
        v = present.get(t.key)
        if v is None:
            (missing if t.required else empty).append({"key": t.key, "required": t.required,
                                                       "default_value": t.default_value, "is_secret": t.is_secret,
                                                       "description": t.description})
        elif t.required and not (v.value or v.vault_ref):
            empty.append({"key": t.key, "required": True, "default_value": t.default_value,
                          "is_secret": t.is_secret, "description": t.description})
    return {"environment_id": env.id, "template_keys": len(keys), "missing": missing, "empty": empty,
            "complete": not missing and not [e for e in empty if e["required"]]}


@router.get("/environments/{env_id}/config/check")
def check_template(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    return template_check(db, get_env(db, env_id, user))


@router.post("/environments/{env_id}/config/apply-template")
def apply_template(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Add the template's missing keys (with their defaults) to the environment."""
    env = get_env(db, env_id, user)
    result = template_check(db, env)
    added = []
    for m in result["missing"]:
        create_var(db, user, env.id, None, VariableIn(key=m["key"], value=m["default_value"] or "",
                                                      is_secret=m["is_secret"], description=m["description"]))
        added.append(m["key"])
    db.commit()
    return {"added": added}


# --- Import / export (CFG-06, SEC-03) ---------------------------------------------------


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _export_rows(db: Session, env: Environment, include_secrets: bool, effective: bool) -> list[dict[str, Any]]:
    items = ([r["variable"] for r in effective_config(db, env)] if effective
             else list(db.scalars(select(Variable).where(_scope_filter(env.id, None)).order_by(Variable.key))))
    rows = []
    for v in items:
        if v.is_secret and not include_secrets:
            value = f"vault:{v.vault_ref}" if v.vault_ref else None
        else:
            value = v.value if not (v.is_secret and v.vault_ref) else f"vault:{v.vault_ref}"
        rows.append({"key": v.key, "value": value, "is_secret": v.is_secret, "description": v.description,
                     "value_type": v.value_type, "sensitivity": v.sensitivity})
    return rows


def _render(rows: list[dict[str, Any]], fmt: str) -> tuple[str, str]:
    if fmt == "json":
        return json.dumps({r["key"]: r["value"] for r in rows}, indent=2), "application/json"
    if fmt == "yaml":
        return yaml.safe_dump({r["key"]: r["value"] for r in rows}, sort_keys=True), "application/x-yaml"
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["key", "value", "is_secret", "description", "value_type", "sensitivity"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
        return buf.getvalue(), "text/csv"
    lines = []
    for r in rows:
        if r["value"] is None:
            lines.append(f"# {r['key']} is secret and was excluded")
        else:
            lines.append(f'{r["key"]}="{_escape(str(r["value"]))}"')
    return "\n".join(lines) + ("\n" if lines else ""), "text/plain"


def export_config(db: Session, env: Environment, user: User, fmt: str, include_secrets: bool,
                  effective: bool = False) -> Response:
    if include_secrets:
        check(user, ENV_MANAGER, env, "export secret values")
    rows = _export_rows(db, env, include_secrets, effective)
    body, media = _render(rows, fmt)
    audit(db, user, "config_export", "environment", env.id,
          {"format": fmt, "include_secrets": include_secrets, "keys": len(rows)})
    db.commit()
    ext = {"env": "env", "json": "json", "yaml": "yaml", "csv": "csv"}[fmt]
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{env.name}.{ext}"'})


@router.get("/environments/{env_id}/variables/export/dotenv", response_class=Response)
def export_dotenv(env_id: int, include_secrets: bool = False, user: User = Depends(require_viewer),
                  db: Session = Depends(get_db)):
    """Export as .env. Secrets are excluded unless include_secrets (env_manager, audited)."""
    return export_config(db, get_env(db, env_id, user), user, "env", include_secrets)


@router.get("/environments/{env_id}/variables/export", response_class=Response)
def export_variables(env_id: int, format: Literal["env", "json", "yaml", "csv"] = "env",
                     include_secrets: bool = False, effective: bool = False, user: User = Depends(require_viewer),
                     db: Session = Depends(get_db)):
    return export_config(db, get_env(db, env_id, user), user, format, include_secrets, effective)


@router.get("/config/{env_ref}", response_class=Response, tags=["pipelines"])
def pipeline_config(env_ref: str, format: Literal["env", "json", "yaml", "csv"] = "json",
                    instance: str | None = None, include_secrets: bool = False,
                    user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """CFG-09: effective configuration for pipelines (`/api/v1/config/SIT2?format=env`), by name or id."""
    env = resolve_env(db, env_ref)
    if not user.can_see(env):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment not found")
    inst_id = None
    if instance:
        inst = db.scalar(select(SystemInstance).where(SystemInstance.environment_id == env.id,
                                                      or_(SystemInstance.instance_name == instance,
                                                          SystemInstance.system_id == instance)))
        if inst is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Instance '{instance}' not found in {env.name}")
        inst_id = inst.id
    if include_secrets:
        check(user, ENV_MANAGER, env, "read secret values")
    items = [r["variable"] for r in effective_config(db, env, inst_id)]
    rows = [{"key": v.key, "value": (f"vault:{v.vault_ref}" if v.vault_ref else (v.value if (not v.is_secret or include_secrets) else None)),
             "is_secret": v.is_secret, "description": v.description, "value_type": v.value_type,
             "sensitivity": v.sensitivity} for v in items]
    body, media = _render(rows, format)
    audit(db, user, "config_read", "environment", env.id, {"format": format, "instance": instance,
                                                           "include_secrets": include_secrets})
    db.commit()
    return Response(content=body, media_type=media)


def parse_config(content: bytes, fmt: str) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig")
    if fmt == "env":
        out = []
        for n, line in enumerate(text.splitlines(), start=1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("export "):
                s = s[7:]
            if "=" not in s:
                raise ValueError(f"line {n}: expected KEY=value")
            k, v = s.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
            out.append({"key": k.strip(), "value": v, "line": n})
        return out
    if fmt in ("json", "yaml"):
        data = json.loads(text) if fmt == "json" else yaml.safe_load(text)
        if isinstance(data, dict):
            return [{"key": k, "value": "" if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else str(v))}
                    for k, v in data.items()]
        if isinstance(data, list):
            return data
        raise ValueError("Expected a mapping of KEY: value")
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        if "is_secret" in r and isinstance(r["is_secret"], str):
            r["is_secret"] = r["is_secret"].strip().lower() in ("true", "1", "yes", "y")
    return rows


@router.post("/environments/{env_id}/variables/import")
async def import_variables(env_id: int, file: UploadFile = File(...),
                           format: Literal["env", "json", "yaml", "csv"] | None = None,
                           mode: Literal["merge", "replace"] = "merge", dry_run: bool = True,
                           user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """CFG-06: preview (dry_run) then apply. `replace` also deletes keys missing from the file."""
    from app.platform.common import fmt_of

    env = get_env(db, env_id, user)
    check(user, ENV_MANAGER if _protected(db, env) else CONTRIBUTOR, env, "import configuration")
    fmt = fmt_of(file.filename, format)
    if fmt not in ("env", "json", "yaml", "csv"):
        fmt = "env"
    try:
        rows = parse_config(await file.read(), fmt)
    except Exception as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not read the file: {e}")
    return apply_variable_rows(db, env, user, rows, mode, dry_run, source=file.filename or fmt)


def apply_variable_rows(db: Session, env: Environment, user: User, rows: list[dict[str, Any]], mode: str,
                        dry_run: bool, source: str, kind: str = "import") -> dict[str, Any]:
    import re

    existing = {v.key: v for v in db.scalars(select(Variable).where(_scope_filter(env.id, None)))}
    issues, plan, seen = [], [], set()
    for idx, r in enumerate(rows, start=1):
        key = str(r.get("key") or "").strip()
        line = r.get("line", idx)
        if not re.match(KEY_PATTERN, key):
            issues.append({"row": line, "key": key, "message": f"Invalid key '{key}': use letters, digits and _"})
            continue
        if key in seen:
            issues.append({"row": line, "key": key, "message": f"Duplicate key '{key}'"})
            continue
        seen.add(key)
        value = "" if r.get("value") is None else str(r.get("value"))
        is_secret = bool(r.get("is_secret", existing[key].is_secret if key in existing else False))
        cur = existing.get(key)
        warnings = credential_warnings(key, value, is_secret)
        if cur is None:
            plan.append({"key": key, "action": "create", "old": None, "new": "" if is_secret else value,
                         "is_secret": is_secret, "warnings": warnings, "_value": value,
                         "_meta": {k: r.get(k) for k in ("description", "value_type", "sensitivity") if r.get(k)}})
        elif value.startswith("vault:") and cur.vault_ref == value[6:]:
            plan.append({"key": key, "action": "unchanged", "old": None, "new": None, "is_secret": True, "warnings": []})
        elif cur.value != value:
            plan.append({"key": key, "action": "update", "old": MASK if cur.is_secret else cur.value,
                         "new": MASK if cur.is_secret else value, "is_secret": cur.is_secret, "warnings": warnings,
                         "_value": value, "_meta": {}})
        else:
            plan.append({"key": key, "action": "unchanged", "old": None, "new": None, "is_secret": cur.is_secret,
                         "warnings": []})
    if mode == "replace":
        for k, cur in existing.items():
            if k not in seen:
                plan.append({"key": k, "action": "delete", "old": MASK if cur.is_secret else cur.value, "new": None,
                             "is_secret": cur.is_secret, "warnings": []})
    counts = {a: sum(p["action"] == a for p in plan) for a in ("create", "update", "delete", "unchanged")}
    public_plan = [{k: v for k, v in p.items() if not k.startswith("_")} for p in plan]
    report = {"dry_run": dry_run, "valid": not issues, "issues": issues, "plan": public_plan, "counts": counts,
              "bulk_operation_id": None, "approval_id": None}
    if dry_run or issues:
        return report
    changes = []
    for p in plan:
        if p["action"] == "create":
            v = create_var(db, user, env.id, None, VariableIn(key=p["key"], value=p["_value"], is_secret=p["is_secret"],
                                                              **p["_meta"]), action=kind)
            changes.append({"entity": "variable", "id": v.id, "before": None,
                            "after": {"key": v.key, "value": None if v.is_secret else v.value}})
        elif p["action"] == "update":
            v = existing[p["key"]]
            before = {"key": v.key, "value": None if v.is_secret else v.value}
            update_var(db, user, v, VariablePatch(value=p["_value"]))
            changes.append({"entity": "variable", "id": v.id, "before": before,
                            "after": {"key": v.key, "value": None if v.is_secret else v.value}})
        elif p["action"] == "delete":
            v = existing[p["key"]]
            changes.append({"entity": "variable", "id": v.id, "after": None,
                            "before": {"key": v.key, "value": None if v.is_secret else v.value,
                                       "is_secret": v.is_secret, "environment_id": env.id}})
            delete_var(db, user, v)
    op = BulkOperation(user=user.name, kind="variables", changes=changes,
                       summary=f"{kind.capitalize()} {source} into {env.name}: {counts['create']} created, "
                               f"{counts['update']} updated, {counts['delete']} deleted")
    db.add(op)
    db.flush()
    _config_changed(db, env, op.summary)
    db.commit()
    report["bulk_operation_id"] = op.id
    return report


class BulkVariablesIn(BaseModel):
    upserts: list[dict[str, Any]] = []
    deletes: list[str] = []
    dry_run: bool = False


@router.post("/environments/{env_id}/variables/bulk")
def bulk_variables(env_id: int, payload: BulkVariablesIn, user: User = Depends(require_viewer),
                   db: Session = Depends(get_db)):
    """CFG-07 bulk edit: upsert many keys and delete others in one reversible operation."""
    env = get_env(db, env_id, user)
    check(user, ENV_MANAGER if _protected(db, env) else CONTRIBUTOR, env, "bulk edit configuration")
    existing = {v.key: v for v in db.scalars(select(Variable).where(_scope_filter(env.id, None)))}
    rows = [{"key": k, "value": v.value, "is_secret": v.is_secret} for k, v in existing.items()
            if k not in payload.deletes]
    by_key = {r["key"]: r for r in rows}
    for u in payload.upserts:
        by_key[u["key"]] = {**by_key.get(u["key"], {}), **u}
    return apply_variable_rows(db, env, user, list(by_key.values()), "replace", payload.dry_run, "bulk edit", "update")


class CopyIn(BaseModel):
    source_environment_id: int
    target_environment_id: int
    keys: list[str] | None = None
    overwrite: bool = False
    include_secrets: bool = False
    dry_run: bool = False


@router.post("/variables/copy")
def copy_variables(payload: CopyIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """CFG-07: copy keys between environments. Protected targets create an approval request instead."""
    src = get_env(db, payload.source_environment_id, user)
    dst = get_env(db, payload.target_environment_id, user)
    source_vars = {v.key: v for v in db.scalars(select(Variable).where(_scope_filter(src.id, None)))}
    target_vars = {v.key: v for v in db.scalars(select(Variable).where(_scope_filter(dst.id, None)))}
    keys = payload.keys or sorted(source_vars)
    rows = [{"key": k, "value": v.value, "is_secret": v.is_secret}
            for k, v in target_vars.items()]
    by_key = {r["key"]: r for r in rows}
    skipped = []
    for k in keys:
        v = source_vars.get(k)
        if v is None:
            continue
        if v.is_secret and not payload.include_secrets:
            skipped.append(k)
            continue
        if k in target_vars and not payload.overwrite:
            skipped.append(k)
            continue
        by_key[k] = {"key": k, "value": v.value, "is_secret": v.is_secret, "description": v.description}
    if _protected(db, dst) and not user.can(ENV_MANAGER, dst) and not payload.dry_run:
        check(user, CONTRIBUTOR, dst, "request configuration changes")
        req = ApprovalRequest(kind="variables_copy", environment_id=dst.id, requested_by=user.name,
                              summary=f"Copy {len(keys) - len(skipped)} keys from {src.name} to {dst.name}",
                              payload={**payload.model_dump(), "rows": list(by_key.values())})
        db.add(req)
        db.flush()
        audit(db, user, "approval_requested", "approval", req.id, {"summary": req.summary})
        emit(db, "approval.requested", req.summary, f"Requested by {user.name}", environment=dst,
             entity_type="approval", entity_id=req.id, recipients={dst.owner or "", dst.delivery_manager or ""})
        db.commit()
        return {"approval_id": req.id, "status": "pending", "skipped": skipped,
                "message": f"{dst.name} is protected; the copy is waiting for approval"}
    if payload.include_secrets:
        check(user, ENV_MANAGER, dst, "copy secret values")
    report = apply_variable_rows(db, dst, user, list(by_key.values()), "merge", payload.dry_run,
                                 f"copy from {src.name}", "copy")
    report["skipped"] = skipped
    return report
