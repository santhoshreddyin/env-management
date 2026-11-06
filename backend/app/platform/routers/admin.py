"""Governance and administration (GOV-01..09), notifications and subscriptions, saved views."""

import json
import secrets
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import (
    ENV_MANAGER,
    LEVELS,
    ROLES,
    SCOPE_TYPES,
    User,
    check,
    hash_token,
    require_admin,
    require_viewer,
)
from app.config import settings
from app.database import get_db
from app.flows.models import AuditLog
from app.models import (
    ApiToken,
    AppSetting,
    ApprovalRequest,
    BulkOperation,
    Environment,
    Notification,
    SavedView,
    Subscription,
    SystemInstance,
    Variable,
    VariableHistory,
    Webhook,
)
from app.platform.common import (
    DEFAULT_SETTINGS,
    audit,
    aware,
    get_or_404,
    get_setting,
    now,
    tabular_response,
    verify_audit_chain,
)
from app.platform.notify import EVENTS, emit

router = APIRouter(tags=["administration"])


# --- Me ---------------------------------------------------------------------------------


@router.get("/me/access")
def my_access(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.recipient == user.name,
                                                                            Notification.read.is_(False)))
    return {"name": user.name, "role": user.role_label, "level": user.global_level, "roles": sorted(user.roles),
            "groups": sorted(user.groups),
            "assignments": [a.__dict__ for a in user.assignments], "unread_notifications": unread or 0,
            "instance": settings.app_env, "role_levels": {r: LEVELS[r] for r in ROLES}}


# --- Settings (GOV-04/08, ENV-06) -------------------------------------------------------


@router.get("/admin/settings")
def list_settings(_: User = Depends(require_viewer), db: Session = Depends(get_db)):
    return {k: get_setting(db, k) for k in DEFAULT_SETTINGS}


@router.put("/admin/settings/{key}")
def put_setting(key: str, value: Any = Body(...), user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if key not in DEFAULT_SETTINGS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown setting '{key}'")
    if type(value) is not type(DEFAULT_SETTINGS[key]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"{key}: expected a {'list' if isinstance(DEFAULT_SETTINGS[key], list) else 'mapping'}")
    row = db.get(AppSetting, key) or AppSetting(key=key)
    old = row.value
    row.value = value
    row.updated_by = user.name
    db.add(row)
    audit(db, user, "setting_update", "setting", key, {"old": old, "new": value})
    db.commit()
    return {"key": key, "value": get_setting(db, key)}


# --- Role assignments (GOV-01) and API tokens -------------------------------------------


class AssignmentIn(BaseModel):
    principal: str = Field(min_length=1, description='User name, or "group:<name>"')
    role: Literal["viewer", "booker", "contributor", "env_manager", "admin"]
    scope_type: Literal["global", "environment", "programme", "region", "family"] = "global"
    scope_value: str | None = None


@router.get("/admin/roles")
def list_assignments(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.models import RoleAssignment

    return {"roles": ROLES, "scope_types": SCOPE_TYPES, "assignments": [
        {"id": r.id, "principal": r.principal, "role": r.role, "scope_type": r.scope_type, "scope_value": r.scope_value,
         "created_by": r.created_by, "created_at": aware(r.created_at)}
        for r in db.scalars(select(RoleAssignment).order_by(RoleAssignment.principal))]}


@router.post("/admin/roles", status_code=status.HTTP_201_CREATED)
def add_assignment(payload: AssignmentIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.models import RoleAssignment

    if payload.scope_type != "global" and not payload.scope_value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "scope_value: required for a scoped role")
    r = RoleAssignment(**payload.model_dump(), created_by=user.name)
    db.add(r)
    db.flush()
    audit(db, user, "role_grant", "role_assignment", r.id, payload.model_dump())
    db.commit()
    return {"id": r.id, **payload.model_dump()}


@router.delete("/admin/roles/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def remove_assignment(rid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.models import RoleAssignment

    r = get_or_404(db, RoleAssignment, rid, "Role assignment")
    audit(db, user, "role_revoke", "role_assignment", r.id, {"principal": r.principal, "role": r.role,
                                                             "scope": f"{r.scope_type}:{r.scope_value}"})
    db.delete(r)
    db.commit()


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: Literal["viewer", "booker", "contributor", "env_manager"] = "contributor"


@router.get("/admin/tokens")
def list_tokens(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "prefix": t.prefix, "role": t.role, "created_by": t.created_by,
             "created_at": aware(t.created_at), "last_used_at": aware(t.last_used_at), "revoked": t.revoked}
            for t in db.scalars(select(ApiToken).order_by(ApiToken.name))]


@router.post("/admin/tokens", status_code=status.HTTP_201_CREATED)
def create_token(payload: TokenIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Create a pipeline/integration token. The token is shown once."""
    if db.scalar(select(ApiToken).where(ApiToken.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A token called '{payload.name}' already exists")
    token = "emt_" + secrets.token_urlsafe(32)
    t = ApiToken(name=payload.name, role=payload.role, token_hash=hash_token(token), prefix=token[:10],
                 created_by=user.name)
    db.add(t)
    db.flush()
    audit(db, user, "token_create", "api_token", t.id, {"name": t.name, "role": t.role})
    db.commit()
    return {"id": t.id, "name": t.name, "role": t.role, "token": token}


@router.delete("/admin/tokens/{tid}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(tid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = get_or_404(db, ApiToken, tid, "Token")
    t.revoked = True
    audit(db, user, "token_revoke", "api_token", t.id, {"name": t.name})
    db.commit()


# --- Webhooks (INT-06/07) ---------------------------------------------------------------


class WebhookIn(BaseModel):
    name: str = Field(min_length=1)
    url: str = Field(pattern=r"^https?://")
    kind: Literal["generic", "slack", "teams"] = "generic"
    events: list[str] = ["*"]
    secret: str | None = None
    active: bool = True


def _hook_out(h: Webhook) -> dict[str, Any]:
    return {"id": h.id, "name": h.name, "url": h.url, "kind": h.kind, "events": h.events, "active": h.active,
            "has_secret": bool(h.secret), "last_status": h.last_status, "last_delivery_at": aware(h.last_delivery_at)}


@router.get("/admin/webhooks")
def list_webhooks(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"events": EVENTS, "webhooks": [_hook_out(h) for h in db.scalars(select(Webhook).order_by(Webhook.name))]}


@router.post("/admin/webhooks", status_code=status.HTTP_201_CREATED)
def create_webhook(payload: WebhookIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    h = Webhook(**payload.model_dump(), created_by=user.name)
    db.add(h)
    db.flush()
    audit(db, user, "webhook_create", "webhook", h.id, payload.model_dump(exclude={"secret"}))
    db.commit()
    return _hook_out(h)


@router.put("/admin/webhooks/{hid}")
def update_webhook(hid: int, payload: WebhookIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    h = get_or_404(db, Webhook, hid, "Webhook")
    for k, v in payload.model_dump().items():
        if k == "secret" and v is None:
            continue
        setattr(h, k, v)
    audit(db, user, "webhook_update", "webhook", h.id, payload.model_dump(exclude={"secret"}))
    db.commit()
    return _hook_out(h)


@router.delete("/admin/webhooks/{hid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(hid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    h = get_or_404(db, Webhook, hid, "Webhook")
    audit(db, user, "webhook_delete", "webhook", h.id, {"name": h.name})
    db.delete(h)
    db.commit()


@router.post("/admin/webhooks/{hid}/test")
def test_webhook(hid: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    h = get_or_404(db, Webhook, hid, "Webhook")
    from app.platform import notify

    result = notify.transport["webhook"]({"url": h.url, "kind": h.kind, "secret": h.secret},
                                         {"event": "test", "title": "Test message from Env Management",
                                          "body": f"Sent by {user.name}", "at": now().isoformat(), "data": {}})
    h.last_status, h.last_delivery_at = result, now()
    db.commit()
    return {"result": result}



# --- Notifications and subscriptions (BKG-09, HLT-06) -----------------------------------


@router.get("/notifications")
def my_notifications(unread_only: bool = False, limit: int = 100, user: User = Depends(require_viewer),
                     db: Session = Depends(get_db)):
    q = select(Notification).where(Notification.recipient == user.name).order_by(Notification.id.desc()).limit(limit)
    if unread_only:
        q = q.where(Notification.read.is_(False))
    return [{"id": n.id, "at": aware(n.at), "event": n.event, "title": n.title, "body": n.body,
             "entity_type": n.entity_type, "entity_id": n.entity_id, "read": n.read} for n in db.scalars(q)]


@router.post("/notifications/read")
def mark_read(ids: list[int] | None = None, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    q = select(Notification).where(Notification.recipient == user.name, Notification.read.is_(False))
    if ids:
        q = q.where(Notification.id.in_(ids))
    n = 0
    for row in db.scalars(q):
        row.read = True
        n += 1
    db.commit()
    return {"marked": n}


class SubscriptionIn(BaseModel):
    environment_id: int | None = None
    events: list[str] = ["*"]
    channel: Literal["inapp", "email"] = "inapp"
    email: str | None = None


@router.get("/subscriptions")
def my_subscriptions(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    envs = {e.id: e.name for e in db.scalars(select(Environment))}
    return {"events": EVENTS, "subscriptions": [
        {"id": s.id, "environment_id": s.environment_id, "environment": envs.get(s.environment_id, "All environments"),
         "events": s.events, "channel": s.channel, "email": s.email}
        for s in db.scalars(select(Subscription).where(Subscription.user == user.name))]}


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
def subscribe(payload: SubscriptionIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    if payload.channel == "email" and not payload.email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "email: required for e-mail subscriptions")
    s = Subscription(user=user.name, **payload.model_dump())
    db.add(s)
    db.commit()
    return {"id": s.id, **payload.model_dump()}


@router.delete("/subscriptions/{sid}", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(sid: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    s = get_or_404(db, Subscription, sid, "Subscription")
    if s.user != user.name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    db.delete(s)
    db.commit()


# --- Saved views (RPT-02) ---------------------------------------------------------------


class ViewIn(BaseModel):
    page: str
    name: str = Field(min_length=1, max_length=100)
    config: dict[str, Any]
    shared: bool = False


@router.get("/views")
def list_views(page: str, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    rows = db.scalars(select(SavedView).where(SavedView.page == page,
                                              or_(SavedView.user == user.name, SavedView.shared.is_(True)))
                      .order_by(SavedView.name))
    return [{"id": v.id, "page": v.page, "name": v.name, "config": v.config, "shared": v.shared,
             "owner": v.user, "mine": v.user == user.name} for v in rows]


@router.post("/views", status_code=status.HTTP_201_CREATED)
def save_view(payload: ViewIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    v = db.scalar(select(SavedView).where(SavedView.user == user.name, SavedView.page == payload.page,
                                          SavedView.name == payload.name)) or SavedView(user=user.name)
    v.page, v.name, v.config, v.shared = payload.page, payload.name, payload.config, payload.shared
    db.add(v)
    db.commit()
    return {"id": v.id, **payload.model_dump()}


@router.delete("/views/{vid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_view(vid: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    v = get_or_404(db, SavedView, vid, "View")
    if v.user != user.name:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own views")
    db.delete(v)
    db.commit()


# --- Audit (GOV-02) ---------------------------------------------------------------------


@router.get("/audit/search")
def audit_search(q: str | None = None, user_name: str | None = Query(None, alias="user"), action: str | None = None,
                 entity_type: str | None = None, entity_id: str | None = None, start: datetime | None = None,
                 end: datetime | None = None, limit: int = Query(500, le=10000),
                 format: Literal["json", "csv", "xlsx"] = "json", user: User = Depends(require_viewer),
                 db: Session = Depends(get_db)):
    check(user, ENV_MANAGER, None, "read the audit log")
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if user_name:
        query = query.where(AuditLog.user == user_name)
    if action:
        query = query.where(AuditLog.action.in_(action.split(",")))
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if start:
        query = query.where(AuditLog.at >= start)
    if end:
        query = query.where(AuditLog.at < end)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(AuditLog.details).like(like), func.lower(AuditLog.action).like(like),
                                func.lower(AuditLog.user).like(like)))
    rows = [{"id": r.id, "at": aware(r.at), "user": r.user, "action": r.action, "entity_type": r.entity_type,
             "entity_id": r.entity_id, "details": json.loads(r.details) if r.details else None, "hash": r.hash}
            for r in db.scalars(query)]
    if format != "json":
        audit(db, user, "export", "audit", None, {"format": format, "rows": len(rows)})
        db.commit()
        return tabular_response(rows, format, "audit-log")
    return rows


@router.get("/audit/verify")
def audit_verify(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    check(user, ENV_MANAGER, None, "verify the audit log")
    return verify_audit_chain(db)


# --- Bulk operations rollback (GOV-05) --------------------------------------------------


@router.get("/bulk-operations")
def list_bulk(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    return [{"id": o.id, "at": aware(o.at), "user": o.user, "kind": o.kind, "summary": o.summary,
             "changes": len(o.changes), "rolled_back_at": aware(o.rolled_back_at), "rolled_back_by": o.rolled_back_by}
            for o in db.scalars(select(BulkOperation).order_by(BulkOperation.id.desc()).limit(200))]


@router.get("/bulk-operations/{op_id}")
def get_bulk(op_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    o = get_or_404(db, BulkOperation, op_id, "Bulk operation")
    return {"id": o.id, "at": aware(o.at), "user": o.user, "kind": o.kind, "summary": o.summary, "changes": o.changes,
            "rolled_back_at": aware(o.rolled_back_at)}


@router.post("/bulk-operations/{op_id}/rollback")
def rollback_bulk(op_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Undo a bulk import / update: created rows are removed, updated rows get their old values back."""
    from datetime import date

    o = get_or_404(db, BulkOperation, op_id, "Bulk operation")
    check(user, ENV_MANAGER, None, "roll back bulk operations")
    if o.rolled_back_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already rolled back")
    undone, skipped = 0, []
    for c in reversed(o.changes):
        model = {"environment": Environment, "variable": Variable, "instance": SystemInstance}.get(c["entity"])
        if c["entity"] == "environment_integration":
            from app.models import EnvironmentIntegration as model  # noqa: N813
        if model is None:
            continue
        obj = db.get(model, c["id"])
        if c["before"] is None:  # created → remove (environments are soft-deleted)
            if obj is None:
                continue
            if model is Environment:
                obj.deleted_at, obj.deleted_by = now(), user.name
            else:
                db.delete(obj)
            undone += 1
        elif c["after"] is None and model is Variable:  # deleted variable → recreate (non-secret value)
            b = c["before"]
            if b.get("value") is None:
                skipped.append(f"{b['key']} (secret value not kept)")
                continue
            db.add(Variable(environment_id=b.get("environment_id"), key=b["key"], value=b["value"],
                            updated_by=user.name))
            undone += 1
        elif obj is not None:
            for k, v in c["before"].items():
                if k == "value" and v is None:
                    skipped.append(f"{getattr(obj, 'key', obj.id)} (secret value not kept)")
                    continue
                col = model.__table__.columns.get(k)
                if col is not None and v is not None and col.type.python_type is date and isinstance(v, str):
                    v = date.fromisoformat(v[:10])
                setattr(obj, k, v)
            if hasattr(obj, "row_version"):
                obj.row_version += 1
            if model is Variable:
                db.add(VariableHistory(variable_id=obj.id, environment_id=obj.environment_id, key=obj.key,
                                       action="restore", user=user.name, is_secret=obj.is_secret,
                                       new_value=None if obj.is_secret else obj.value))
            undone += 1
    o.rolled_back_at, o.rolled_back_by = now(), user.name
    audit(db, user, "bulk_rollback", "bulk_operation", o.id, {"undone": undone, "skipped": skipped})
    db.commit()
    return {"undone": undone, "skipped": skipped}


# --- Approval requests (GOV-03, CFG-07) -------------------------------------------------


@router.get("/approvals")
def list_approvals(status_: str = Query("pending", alias="status"), user: User = Depends(require_viewer),
                   db: Session = Depends(get_db)):
    envs = {e.id: e for e in db.scalars(select(Environment))}
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.status.in_(status_.split(",")))
                      .order_by(ApprovalRequest.id.desc()))
    return [{"id": r.id, "kind": r.kind, "environment_id": r.environment_id,
             "environment": envs[r.environment_id].name if r.environment_id in envs else None, "summary": r.summary,
             "status": r.status, "requested_by": r.requested_by, "requested_at": aware(r.requested_at),
             "decided_by": r.decided_by, "decided_at": aware(r.decided_at), "decision_note": r.decision_note,
             "can_decide": user.can(ENV_MANAGER, envs.get(r.environment_id))}
            for r in rows if r.environment_id is None or user.can_see(envs[r.environment_id])]


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None


@router.post("/approvals/{aid}/decision")
def decide_approval(aid: int, payload: ApprovalDecisionIn, user: User = Depends(require_viewer),
                    db: Session = Depends(get_db)):
    from app.platform.routers.variables import apply_variable_rows

    r = get_or_404(db, ApprovalRequest, aid, "Approval request")
    env = db.get(Environment, r.environment_id) if r.environment_id else None
    check(user, ENV_MANAGER, env, "decide approval requests")
    if r.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Request already {r.status}")
    if r.requested_by == user.name:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot approve your own request")
    result = None
    if payload.decision == "approve" and r.kind == "variables_copy" and env is not None:
        requester = User(name=r.requested_by, roles={"env_manager", "viewer"})
        result = apply_variable_rows(db, env, requester, r.payload["rows"], "merge", False,
                                     f"approved copy #{r.id}", "copy")
    r.status = "approved" if payload.decision == "approve" else "rejected"
    r.decided_by, r.decided_at, r.decision_note = user.name, now(), payload.note
    audit(db, user, f"approval_{r.status}", "approval", r.id, {"summary": r.summary, "note": payload.note})
    emit(db, "approval.decided", f"{r.summary}: {r.status}", payload.note, environment=env, entity_type="approval",
         entity_id=r.id, recipients={r.requested_by})
    db.commit()
    return {"id": r.id, "status": r.status, "result": result}


# --- Sample data (RPT-10) ---------------------------------------------------------------


@router.post("/admin/sample-data")
def load_sample(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.platform.sample import seed_platform

    if db.scalar(select(func.count()).select_from(Environment)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Sample data can only be loaded into an empty inventory")
    result = seed_platform(db, user)
    db.commit()
    return result
