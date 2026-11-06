"""Enterprise integrations: CMDB sync (INT-02), infrastructure discovery (INT-09), chat commands (INT-07).

CI/CD deployment events (INT-03) are in deployments.py (`/ci/deployments`), pipeline config in
variables.py (`/config/{env}`), ticket sync (INT-04) in operations.py (`/tickets/webhook`),
monitoring ingestion (HLT-03) in operations.py and the calendar feed (INT-08) in bookings.py.
"""

import re
import shlex
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import CONTRIBUTOR, ENV_MANAGER, User, check, require_viewer
from app.database import get_db
from app.flows.models import System
from app.models import Booking, Environment, SystemInstance
from app.platform.common import audit, aware, bump, now
from app.platform.routers.environments import EDITABLE, _create, env_out, resolve_env, validate_env_fields
from app.platform.services import effective_health

router = APIRouter(tags=["integrations"])

# --- CMDB (INT-02) ----------------------------------------------------------------------

CMDB_FIELD_MAP = {
    # ServiceNow cmdb_ci_environment-style keys → platform fields
    "sys_id": "cmdb_id", "name": "name", "short_description": "description", "u_environment_type": "env_type",
    "environment_type": "env_type", "owned_by": "owner", "managed_by": "technical_contact",
    "support_group": "support_group", "cost_center": "cost_centre", "u_programme": "programme",
    "location": "hosting_location", "u_region": "region", "u_platform": "platform", "u_network_zone": "network_zone",
}


def _val(v: Any) -> Any:
    """ServiceNow reference fields come as {"display_value": ..., "value": ...}."""
    if isinstance(v, dict):
        return v.get("display_value") or v.get("value")
    return v


@router.get("/cmdb/export")
def cmdb_export(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Environments and system instances as configuration items for the CMDB to pull."""
    envs = [e for e in db.scalars(select(Environment).where(Environment.deleted_at.is_(None))) if user.can_see(e)]
    names = dict(db.execute(select(System.id, System.name)).tuples().all())
    cis = []
    for e in envs:
        cis.append({"ci_class": "environment", "correlation_id": f"env-{e.id}", "sys_id": e.cmdb_id, "name": e.name,
                    "short_description": e.description, "environment_type": e.env_type, "operational_status": e.status,
                    "owned_by": e.owner, "support_group": e.support_group, "cost_center": e.cost_centre,
                    "u_programme": e.programme, "u_region": e.region, "u_platform": e.platform,
                    "health": effective_health(e)})
        for i in e.instances:
            cis.append({"ci_class": "application_instance", "correlation_id": f"inst-{i.id}",
                        "parent_correlation_id": f"env-{e.id}", "name": i.instance_name,
                        "application": names.get(i.system_id, i.system_id), "version": i.deployed_version,
                        "url": i.url, "mode": i.mode, "health": effective_health(i)})
    return {"exported_at": now(), "count": len(cis), "items": cis}


class CmdbSyncIn(BaseModel):
    items: list[dict[str, Any]]
    dry_run: bool = True
    field_map: dict[str, str] | None = Field(None, description="Override source → platform field mapping")


@router.post("/cmdb/sync")
def cmdb_sync(payload: CmdbSyncIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Upsert environments from CMDB records, matched on CMDB id then name. Preview with dry_run."""
    check(user, ENV_MANAGER, None, "sync from the CMDB")
    mapping = {**CMDB_FIELD_MAP, **(payload.field_map or {})}
    plan, issues = [], []
    for n, raw in enumerate(payload.items, start=1):
        data = {}
        for k, v in raw.items():
            target = mapping.get(k)
            if target in EDITABLE:
                data[target] = _val(v)
        if not data.get("name"):
            issues.append({"row": n, "message": "name is missing"})
            continue
        env = None
        if data.get("cmdb_id"):
            env = db.scalar(select(Environment).where(Environment.cmdb_id == data["cmdb_id"]))
        env = env or db.scalar(select(Environment).where(func.lower(Environment.name) == data["name"].lower()))
        if env is None:
            errs = [e for e in validate_env_fields(db, {"env_type": "DEV", **data})
                    if not e.startswith(("owner", "delivery_manager", "support_group", "cost_centre"))]
            if errs:
                issues += [{"row": n, "message": e} for e in errs]
                continue
            plan.append({"row": n, "action": "create", "name": data["name"], "changes": data})
        else:
            diff = {k: [getattr(env, k), v] for k, v in data.items() if v is not None and getattr(env, k) != v}
            plan.append({"row": n, "action": "update" if diff else "unchanged", "name": env.name, "id": env.id,
                         "changes": diff})
    if payload.dry_run or issues:
        return {"dry_run": payload.dry_run, "valid": not issues, "issues": issues, "plan": plan}
    for p in plan:
        if p["action"] == "create":
            _create(db, {"env_type": "DEV", **p["changes"]}, user)
        elif p["action"] == "update":
            env = db.get(Environment, p["id"])
            for k, (_, v) in p["changes"].items():
                setattr(env, k, v)
            bump(env, user)
    audit(db, user, "cmdb_sync", "environment", None,
          {"created": sum(p["action"] == "create" for p in plan), "updated": sum(p["action"] == "update" for p in plan)})
    db.commit()
    return {"dry_run": False, "valid": True, "issues": [], "plan": plan}


# --- Infrastructure discovery (INT-09) --------------------------------------------------


class DiscoveredResource(BaseModel):
    name: str
    system_id: str | None = None
    version: str | None = None
    url: str | None = None
    kind: str | None = None  # deployment, vm, function, database…
    labels: dict[str, str] = {}


class DiscoveryIn(BaseModel):
    source: Literal["kubernetes", "aws", "azure", "gcp", "vmware", "other"]
    environment: str
    resources: list[DiscoveredResource]
    create_missing: bool = False
    dry_run: bool = False


@router.post("/discovery/ingest")
def discovery_ingest(payload: DiscoveryIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Verify the inventory against what a discovery job found (e.g. `kubectl get deploy -o json` mapped to
    name/version). Matches instances by instance name, system id or the `app`/`system` label."""
    env = resolve_env(db, payload.environment)
    check(user, CONTRIBUTOR, env, "ingest discovery results")
    instances = list(env.instances)
    by_key: dict[str, SystemInstance] = {}
    for i in instances:
        by_key[i.instance_name.lower()] = i
        by_key.setdefault(i.system_id.lower(), i)
    systems = {s.id.lower(): s.id for s in db.scalars(select(System))}
    verified, mismatched, unknown, created = [], [], [], []
    seen: set[int] = set()
    for r in payload.resources:
        keys = [r.name, r.system_id or "", r.labels.get("app", ""), r.labels.get("system", "")]
        inst = next((by_key[k.lower()] for k in keys if k and k.lower() in by_key), None)
        if inst is None:
            sid = next((systems[k.lower()] for k in keys if k and k.lower() in systems), None)
            if payload.create_missing and sid and not payload.dry_run:
                inst = SystemInstance(environment_id=env.id, system_id=sid, instance_name=r.name, url=r.url,
                                      deployed_version=r.version, last_verified=now().date(),
                                      verified_by=f"discovery:{payload.source}")
                db.add(inst)
                db.flush()
                created.append(r.name)
            else:
                unknown.append({"name": r.name, "kind": r.kind, "version": r.version, "matching_system": sid})
            continue
        seen.add(inst.id)
        if r.version and inst.deployed_version and r.version != inst.deployed_version:
            mismatched.append({"instance": inst.instance_name, "recorded": inst.deployed_version, "discovered": r.version})
        if not payload.dry_run:
            inst.last_verified = now().date()
            inst.verified_by = f"discovery:{payload.source}"
            if r.version and not inst.deployed_version:
                inst.deployed_version = r.version
            if r.url and not inst.url:
                inst.url = r.url
        verified.append(inst.instance_name)
    not_found = [i.instance_name for i in instances if i.id not in seen and i.mode == "real"]
    result = {"environment": env.name, "verified": verified, "version_mismatches": mismatched,
              "unknown_resources": unknown, "created": created, "recorded_but_not_found": not_found,
              "dry_run": payload.dry_run}
    if not payload.dry_run:
        audit(db, user, "discovery", "environment", env.id,
              {"source": payload.source, "verified": len(verified), "mismatches": len(mismatched),
               "unknown": len(unknown), "created": len(created)})
        db.commit()
    return result


# --- Chat commands (INT-07) -------------------------------------------------------------

HELP = ("Commands: `status <env>` · `who <env>` · `free <type> <YYYY-MM-DD> <YYYY-MM-DD>` · "
        "`book <env> <YYYY-MM-DD> <YYYY-MM-DD> <project>`")


@router.post("/chatops/command")
async def chat_command(request: Request, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Basic commands from Slack slash commands (form `text=`) or Teams outgoing webhooks (JSON `text`).
    Returns a message in Slack's format (`text`), which Teams also renders."""
    from app.platform.routers.bookings import BookingIn, create_booking

    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        text = body.get("text", "")
    else:
        text = (await request.form()).get("text", "")
    text = re.sub(r"<at>.*?</at>", "", str(text)).strip()
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    if not parts or parts[0].lower() in ("help", "?"):
        return {"response_type": "ephemeral", "text": HELP}
    cmd, args = parts[0].lower(), parts[1:]
    try:
        if cmd == "status" and args:
            env = resolve_env(db, args[0])
            bad = [f"{i.instance_name}: {effective_health(i)}" for i in env.instances
                   if effective_health(i) not in ("Healthy", "Unknown")]
            return {"response_type": "in_channel",
                    "text": f"*{env.name}* ({env.env_type}) is *{effective_health(env)}*, lifecycle {env.status}."
                            + (f" Issues: {'; '.join(bad)}" if bad else "")}
        if cmd == "who" and args:
            env = resolve_env(db, args[0])
            t = now()
            active = db.scalars(select(Booking).where(Booking.environment_id == env.id, Booking.status == "Active",
                                                      Booking.start_at <= t, Booking.end_at > t)).all()
            if not active:
                return {"response_type": "in_channel", "text": f"{env.name} is not booked right now. Owner: {env.owner or 'n/a'}"}
            return {"response_type": "in_channel", "text": f"{env.name}: " + "; ".join(
                f"{b.project} ({b.team or b.requested_by}) until {aware(b.end_at):%d %b}" for b in active)}
        if cmd == "free" and len(args) >= 3:
            from app.platform.services import find_conflicts

            start = datetime.fromisoformat(args[1]).replace(tzinfo=now().tzinfo)
            end = datetime.fromisoformat(args[2]).replace(tzinfo=now().tzinfo) + timedelta(days=1)
            free = [e.name for e in db.scalars(select(Environment).where(
                Environment.deleted_at.is_(None), func.lower(Environment.env_type) == args[0].lower(),
                Environment.status.in_(["Available", "In use"]))) if not find_conflicts(db, e.id, start, end, [])]
            return {"response_type": "in_channel",
                    "text": f"Free {args[0]} environments {args[1]} – {args[2]}: {', '.join(free) or 'none'}"}
        if cmd == "book" and len(args) >= 4:
            env = resolve_env(db, args[0])
            start = datetime.fromisoformat(args[1]).replace(tzinfo=now().tzinfo)
            end = datetime.fromisoformat(args[2]).replace(tzinfo=now().tzinfo) + timedelta(days=1)
            r = create_booking(BookingIn(environment_id=env.id, project=" ".join(args[3:]), start_at=start, end_at=end,
                                         purpose="Booked from chat"), user, db)
            b = r["bookings"][0]
            return {"response_type": "in_channel",
                    "text": f"Booked {env.name} for {b['project']} {args[1]} – {args[2]}: *{b['status']}* (#{b['id']})"}
    except HTTPException as e:
        detail = e.detail["message"] if isinstance(e.detail, dict) else e.detail
        return {"response_type": "ephemeral", "text": f"Sorry: {detail}"}
    except ValueError as e:
        return {"response_type": "ephemeral", "text": f"Sorry: {e}. {HELP}"}
    return {"response_type": "ephemeral", "text": HELP}


_ = (or_, env_out, status)
