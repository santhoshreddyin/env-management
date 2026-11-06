"""Systems and integrations per environment (TOP-01..11)."""

import io
import json
from collections import defaultdict
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import CONTRIBUTOR, ENV_MANAGER, User, check, require_viewer
from app.database import get_db
from app.flows.models import Integration, System
from app.models import (
    Booking,
    BulkOperation,
    Environment,
    EnvironmentIntegration,
    Issue,
    SystemInstance,
    SystemProfile,
    instance_shares,
)
from app.platform.common import XLSX, apply, audit, aware, bump, check_version, get_or_404, get_setting, now
from app.platform.routers.environments import get_env, resolve_env
from app.platform.services import catalogue_integrations, effective_health, stale, system_names

router = APIRouter(tags=["topology"])

MODES = Literal["real", "virtualised", "stubbed", "mocked", "not_available"]
INT_STATUS = Literal["connected", "broken", "not_connected", "virtualised"]


# --- Catalogue (TOP-01) -----------------------------------------------------------------


class ProfileIn(BaseModel):
    category: str | None = None
    criticality: Literal["critical", "high", "medium", "low"] | None = None
    technology: str | None = None
    owner: str | None = None
    domain: str | None = None


@router.get("/catalogue/systems")
def catalogue(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    profiles = {p.system_id: p for p in db.scalars(select(SystemProfile))}
    counts: dict[str, list[str]] = defaultdict(list)
    envs = {e.id: e for e in db.scalars(select(Environment).where(Environment.deleted_at.is_(None)))}
    for sid, eid in db.execute(select(SystemInstance.system_id, SystemInstance.environment_id)):
        if eid in envs:
            counts[sid].append(envs[eid].name)
    out = []
    for s in db.scalars(select(System).order_by(System.name)):
        p = profiles.get(s.id)
        out.append({"id": s.id, "name": s.name, "type": s.type, "category": p.category if p else _guess_category(s.type),
                    "criticality": p.criticality if p else None, "technology": p.technology if p else None,
                    "owner": (p.owner if p and p.owner else s.owner), "domain": (p.domain if p and p.domain else s.domain),
                    "environments": sorted(counts.get(s.id, []))})
    return out


def _guess_category(t: str) -> str:
    return {"gateway": "middleware", "queue_manager": "middleware", "mainframe": "mainframe"}.get(t, "application")


@router.put("/catalogue/systems/{system_id}")
def update_profile(system_id: str, payload: ProfileIn, user: User = Depends(require_viewer),
                   db: Session = Depends(get_db)):
    check(user, ENV_MANAGER, None, "edit the system catalogue")
    if db.get(System, system_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"System '{system_id}' not found")
    cats = get_setting(db, "system_categories")
    if payload.category and payload.category not in cats:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"category: use one of {', '.join(cats)}")
    p = db.get(SystemProfile, system_id) or SystemProfile(system_id=system_id)
    apply(p, payload.model_dump(), skip=())
    db.add(p)
    audit(db, user, "update_profile", "system", system_id, payload.model_dump())
    db.commit()
    return {"system_id": system_id, **payload.model_dump()}


# --- Instances (TOP-02/04/09) -----------------------------------------------------------


class InstanceIn(BaseModel):
    system_id: str
    instance_name: str | None = Field(default=None, max_length=200)
    url: str | None = None
    deployed_version: str | None = None
    build: str | None = None
    commit_sha: str | None = None
    release: str | None = None
    mode: MODES = "real"
    virtualisation_ref: str | None = None
    last_verified: date | None = None
    verified_by: str | None = None
    health_check_url: str | None = None
    notes: str | None = None
    shared_with: list[int] = []


class InstancePatch(BaseModel):
    instance_name: str | None = None
    url: str | None = None
    deployed_version: str | None = None
    build: str | None = None
    commit_sha: str | None = None
    release: str | None = None
    mode: MODES | None = None
    virtualisation_ref: str | None = None
    last_verified: date | None = None
    verified_by: str | None = None
    health_check_url: str | None = None
    notes: str | None = None
    shared_with: list[int] | None = None
    row_version: int | None = None


def instance_out(i: SystemInstance, names: dict[str, str], env_names: dict[int, str] | None = None) -> dict[str, Any]:
    return {
        "id": i.id, "environment_id": i.environment_id, "system_id": i.system_id,
        "system_name": names.get(i.system_id), "in_catalogue": i.system_id in names, "instance_name": i.instance_name,
        "url": i.url, "deployed_version": i.deployed_version, "build": i.build, "commit_sha": i.commit_sha,
        "release": i.release, "mode": i.mode, "virtualisation_ref": i.virtualisation_ref,
        "last_verified": i.last_verified, "verified_by": i.verified_by, "stale": stale(i.last_verified),
        "health_status": effective_health(i), "health_checked_at": aware(i.health_checked_at),
        "health_check_url": i.health_check_url,
        "health_override": ({"status": i.health_override_status, "reason": i.health_override_reason,
                             "until": aware(i.health_override_until)} if i.health_override_status else None),
        "notes": i.notes, "row_version": i.row_version,
        "shared_with": [{"id": e.id, "name": e.name} for e in i.shared_with],
        "environment": (env_names or {}).get(i.environment_id),
    }


def _validate_mode(payload: Any) -> None:
    mode = getattr(payload, "mode", None)
    if mode in ("virtualised", "stubbed", "mocked") and not getattr(payload, "virtualisation_ref", None):
        pass  # recommended, reported in data quality rather than blocking


def _set_shares(db: Session, inst: SystemInstance, ids: list[int]) -> None:
    envs = []
    for i in ids:
        if i == inst.environment_id:
            continue
        e = db.get(Environment, i)
        if e is None or e.deleted_at is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"shared_with: environment {i} not found")
        envs.append(e)
    inst.shared_with = envs


@router.get("/environments/{env_id}/instances")
def list_instances(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    names = system_names(db)
    env_names = {e.id: e.name for e in db.scalars(select(Environment))}
    own = db.scalars(select(SystemInstance).options(selectinload(SystemInstance.shared_with))
                     .where(SystemInstance.environment_id == env.id).order_by(SystemInstance.instance_name)).all()
    shared_ids = db.scalars(select(instance_shares.c.instance_id).where(instance_shares.c.environment_id == env.id))
    shared = db.scalars(select(SystemInstance).options(selectinload(SystemInstance.shared_with))
                        .where(SystemInstance.id.in_(list(shared_ids)))).all()
    return ([instance_out(i, names, env_names) | {"shared_in": False} for i in own]
            + [instance_out(i, names, env_names) | {"shared_in": True} for i in shared])


@router.post("/environments/{env_id}/instances", status_code=status.HTTP_201_CREATED)
def create_instance(env_id: int, payload: InstanceIn, user: User = Depends(require_viewer),
                    db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    check(user, CONTRIBUTOR, env, "edit topology")
    inst = _create_instance(db, env, payload)
    audit(db, user, "create", "instance", inst.id, {"environment": env.name, "system_id": inst.system_id})
    db.commit()
    return instance_out(inst, system_names(db))


def _create_instance(db: Session, env: Environment, payload: InstanceIn) -> SystemInstance:
    names = system_names(db)
    if payload.system_id not in names:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"system_id: '{payload.system_id}' is not in the system catalogue")
    name = (payload.instance_name or f"{payload.system_id}-{env.name}").strip()
    dup = db.scalar(select(SystemInstance).where(SystemInstance.environment_id == env.id,
                                                 SystemInstance.instance_name == name))
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"instance_name: '{name}' already exists in {env.name}")
    inst = SystemInstance(environment_id=env.id, **payload.model_dump(exclude={"shared_with", "instance_name"}),
                          instance_name=name)
    db.add(inst)
    db.flush()
    _set_shares(db, inst, payload.shared_with)
    return inst


@router.patch("/instances/{instance_id}")
def update_instance(instance_id: int, payload: InstancePatch, user: User = Depends(require_viewer),
                    db: Session = Depends(get_db)):
    inst = get_or_404(db, SystemInstance, instance_id, "Instance")
    env = get_env(db, inst.environment_id, user)
    check(user, CONTRIBUTOR, env, "edit topology")
    check_version(inst, payload.row_version)
    data = payload.model_dump(exclude_unset=True, exclude={"row_version", "shared_with"})
    diff = apply(inst, data)
    if payload.shared_with is not None:
        _set_shares(db, inst, payload.shared_with)
        diff["shared_with"] = payload.shared_with
    if diff:
        bump(inst)
        audit(db, user, "update", "instance", inst.id, {"environment": env.name, "changes": diff})
    db.commit()
    return instance_out(inst, system_names(db))


@router.post("/instances/{instance_id}/verify")
def verify_instance(instance_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """TOP-09: confirm the instance record is accurate today."""
    inst = get_or_404(db, SystemInstance, instance_id, "Instance")
    env = get_env(db, inst.environment_id, user)
    check(user, CONTRIBUTOR, env, "verify topology")
    inst.last_verified = now().date()
    inst.verified_by = user.name
    bump(inst)
    audit(db, user, "verify", "instance", inst.id, {"environment": env.name})
    db.commit()
    return instance_out(inst, system_names(db))


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_instance(instance_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    inst = get_or_404(db, SystemInstance, instance_id, "Instance")
    env = get_env(db, inst.environment_id, user)
    check(user, CONTRIBUTOR, env, "edit topology")
    audit(db, user, "delete", "instance", inst.id, {"environment": env.name, "system_id": inst.system_id,
                                                    "instance_name": inst.instance_name})
    db.delete(inst)
    db.commit()


# --- Environment integrations (TOP-03) --------------------------------------------------


class EnvIntegrationIn(BaseModel):
    integration_id: str | None = None
    name: str | None = None
    from_instance_id: int | None = None
    to_instance_id: int | None = None
    protocol: str | None = None
    pattern: str | None = None
    direction: Literal["one_way", "two_way"] | None = None
    status: INT_STATUS = "connected"
    endpoint: str | None = None
    last_verified: date | None = None
    verified_by: str | None = None
    notes: str | None = None


def env_integration_out(ei: EnvironmentIntegration, cat: dict[str, Integration], insts: dict[int, SystemInstance],
                        names: dict[str, str]) -> dict[str, Any]:
    c = cat.get(ei.integration_id) if ei.integration_id else None
    fi, ti = insts.get(ei.from_instance_id), insts.get(ei.to_instance_id)
    hops = [{"sequence": h.sequence, "from": names.get(h.from_system, h.from_system),
             "to": names.get(h.to_system, h.to_system), "protocol": h.protocol, "direction": h.direction}
            for h in (c.hops if c else [])]
    return {
        "id": ei.id, "environment_id": ei.environment_id, "integration_id": ei.integration_id,
        "name": ei.name or (c.name if c else None), "journey": c.journey if c else None,
        "from_instance_id": ei.from_instance_id, "to_instance_id": ei.to_instance_id,
        "from_instance": fi.instance_name if fi else None, "to_instance": ti.instance_name if ti else None,
        "from_system": fi.system_id if fi else (c.upstream_id if c else None),
        "to_system": ti.system_id if ti else (c.downstream_id if c else None),
        "protocol": ei.protocol or (c.primary_protocol if c else None), "pattern": ei.pattern or (c.pattern if c else None),
        "direction": ei.direction, "status": ei.status, "endpoint": ei.endpoint, "hops": hops, "hop_count": len(hops),
        "last_verified": ei.last_verified, "verified_by": ei.verified_by, "stale": stale(ei.last_verified),
        "notes": ei.notes, "in_catalogue": c is not None,
    }


def _validate_ei(db: Session, env: Environment, payload: EnvIntegrationIn | dict) -> None:
    data = payload if isinstance(payload, dict) else payload.model_dump(exclude_unset=True)
    if data.get("integration_id") and db.get(Integration, data["integration_id"]) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"integration_id: '{data['integration_id']}' is not in the integration catalogue")
    for f in ("from_instance_id", "to_instance_id"):
        if data.get(f) is not None:
            i = db.get(SystemInstance, data[f])
            if i is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{f}: instance {data[f]} not found")
            if i.environment_id != env.id and env not in i.shared_with:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    f"{f}: instance {i.instance_name} is not in {env.name}")


@router.get("/environments/{env_id}/integrations")
def list_env_integrations(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    return _env_integrations(db, env)


def _env_integrations(db: Session, env: Environment) -> list[dict[str, Any]]:
    cat = catalogue_integrations(db)
    insts = {i.id: i for i in db.scalars(select(SystemInstance))}
    names = system_names(db)
    rows = db.scalars(select(EnvironmentIntegration).where(EnvironmentIntegration.environment_id == env.id)
                      .order_by(EnvironmentIntegration.id))
    return [env_integration_out(ei, cat, insts, names) for ei in rows]


@router.post("/environments/{env_id}/integrations", status_code=status.HTTP_201_CREATED)
def create_env_integration(env_id: int, payload: EnvIntegrationIn, user: User = Depends(require_viewer),
                           db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    check(user, CONTRIBUTOR, env, "edit topology")
    _validate_ei(db, env, payload)
    if not payload.integration_id and not payload.name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "name: required when no catalogue integration is set")
    ei = EnvironmentIntegration(environment_id=env.id, **payload.model_dump())
    db.add(ei)
    db.flush()
    audit(db, user, "create", "environment_integration", ei.id, {"environment": env.name, **payload.model_dump(mode="json")})
    db.commit()
    return env_integration_out(ei, catalogue_integrations(db), {i.id: i for i in db.scalars(select(SystemInstance))},
                               system_names(db))


@router.patch("/environment-integrations/{ei_id}")
def update_env_integration(ei_id: int, payload: EnvIntegrationIn, user: User = Depends(require_viewer),
                           db: Session = Depends(get_db)):
    ei = get_or_404(db, EnvironmentIntegration, ei_id, "Integration")
    env = get_env(db, ei.environment_id, user)
    check(user, CONTRIBUTOR, env, "edit topology")
    data = payload.model_dump(exclude_unset=True)
    _validate_ei(db, env, data)
    diff = apply(ei, data)
    audit(db, user, "update", "environment_integration", ei.id, {"environment": env.name, "changes": diff})
    db.commit()
    return env_integration_out(ei, catalogue_integrations(db), {i.id: i for i in db.scalars(select(SystemInstance))},
                               system_names(db))


@router.delete("/environment-integrations/{ei_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_env_integration(ei_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    ei = get_or_404(db, EnvironmentIntegration, ei_id, "Integration")
    env = get_env(db, ei.environment_id, user)
    check(user, CONTRIBUTOR, env, "edit topology")
    audit(db, user, "delete", "environment_integration", ei.id, {"environment": env.name})
    db.delete(ei)
    db.commit()


@router.post("/environments/{env_id}/topology/populate")
def populate_from_catalogue(env_id: int, system_ids: list[str] | None = None, user: User = Depends(require_viewer),
                            db: Session = Depends(get_db)):
    """Bootstrap: add an instance per catalogue system and an integration per catalogue integration."""
    env = get_env(db, env_id, user)
    check(user, CONTRIBUTOR, env, "edit topology")
    names = system_names(db)
    wanted = set(system_ids or names)
    by_system = {i.system_id: i for i in env.instances}
    added_i = added_e = 0
    for sid in sorted(wanted & set(names)):
        if sid not in by_system:
            by_system[sid] = _create_instance(db, env, InstanceIn(system_id=sid))
            added_i += 1
    existing = set(db.scalars(select(EnvironmentIntegration.integration_id)
                              .where(EnvironmentIntegration.environment_id == env.id)))
    for it in catalogue_integrations(db).values():
        if it.id in existing or it.upstream_id not in by_system or it.downstream_id not in by_system:
            continue
        db.add(EnvironmentIntegration(environment_id=env.id, integration_id=it.id,
                                      from_instance_id=by_system[it.upstream_id].id,
                                      to_instance_id=by_system[it.downstream_id].id, status="connected"))
        added_e += 1
    audit(db, user, "populate_topology", "environment", env.id, {"instances": added_i, "integrations": added_e})
    db.commit()
    return {"instances_added": added_i, "integrations_added": added_e}


@router.get("/environments/{env_id}/topology")
def topology(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Graph of system instances and their integrations in one environment (TOP-06)."""
    instances = list_instances(env_id, user, db)
    integrations = list_env_integrations(env_id, user, db)
    return {"instances": instances, "integrations": integrations}


# --- Compare, shared components, journeys, impact (TOP-05/07/08/10) ---------------------


@router.get("/topology/compare")
def compare(left: int, right: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    a, b = get_env(db, left, user), get_env(db, right, user)
    names = system_names(db)
    ia = {i.system_id: i for i in a.instances}
    ib = {i.system_id: i for i in b.instances}
    systems = []
    for sid in sorted(set(ia) | set(ib), key=lambda s: names.get(s, s)):
        x, y = ia.get(sid), ib.get(sid)
        diffs = []
        if x is None or y is None:
            diffs.append("missing")
        else:
            if (x.deployed_version or None) != (y.deployed_version or None):
                diffs.append("version")
            if x.mode != y.mode:
                diffs.append("mode")
        systems.append({"system_id": sid, "system_name": names.get(sid, sid),
                        "left": {"version": x.deployed_version, "mode": x.mode, "instance": x.instance_name} if x else None,
                        "right": {"version": y.deployed_version, "mode": y.mode, "instance": y.instance_name} if y else None,
                        "differences": diffs})
    ea = {(r["integration_id"] or r["name"]): r for r in _env_integrations(db, a)}
    eb = {(r["integration_id"] or r["name"]): r for r in _env_integrations(db, b)}
    integrations = []
    for k in sorted(set(ea) | set(eb), key=str):
        x, y = ea.get(k), eb.get(k)
        diffs = []
        if x is None or y is None:
            diffs.append("missing")
        else:
            for f in ("status", "protocol", "endpoint"):
                if x.get(f) != y.get(f):
                    diffs.append(f)
        integrations.append({"key": k, "name": (x or y)["name"],
                             "left": {f: x[f] for f in ("status", "protocol", "endpoint")} if x else None,
                             "right": {f: y[f] for f in ("status", "protocol", "endpoint")} if y else None,
                             "differences": diffs})
    return {"left": {"id": a.id, "name": a.name}, "right": {"id": b.id, "name": b.name},
            "systems": systems, "integrations": integrations,
            "summary": {"systems_different": sum(bool(s["differences"]) for s in systems),
                        "integrations_different": sum(bool(i["differences"]) for i in integrations)}}


@router.get("/topology/shared")
def shared_components(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """TOP-05: instances serving more than one environment."""
    names = system_names(db)
    out = []
    for i in db.scalars(select(SystemInstance).options(selectinload(SystemInstance.shared_with),
                                                       selectinload(SystemInstance.environment))):
        if not i.shared_with or i.environment.deleted_at is not None:
            continue
        envs = [i.environment] + [e for e in i.shared_with if e.deleted_at is None]
        if not any(user.can_see(e) for e in envs):
            continue
        out.append({"instance_id": i.id, "instance_name": i.instance_name, "system_id": i.system_id,
                    "system_name": names.get(i.system_id), "owner_environment": i.environment.name,
                    "environments": [e.name for e in envs], "health_status": effective_health(i)})
    return out


@router.get("/environments/{env_id}/journeys")
def journeys(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """TOP-08: per business journey, the systems and integrations it touches in this environment."""
    env = get_env(db, env_id, user)
    names = system_names(db)
    inst_by_system = {i.system_id: i for i in env.instances}
    for sid in db.scalars(select(SystemInstance.system_id).join(
            instance_shares, instance_shares.c.instance_id == SystemInstance.id)
            .where(instance_shares.c.environment_id == env.id)):
        inst_by_system.setdefault(sid, db.scalar(select(SystemInstance).where(SystemInstance.system_id == sid)))
    env_ints = {r["integration_id"]: r for r in _env_integrations(db, env) if r["integration_id"]}
    groups: dict[str, list[Integration]] = defaultdict(list)
    for it in catalogue_integrations(db).values():
        groups[it.journey or "(no journey)"].append(it)
    out = []
    for journey, items in sorted(groups.items()):
        systems: set[str] = set()
        rows = []
        for it in sorted(items, key=lambda i: i.name):
            touched = {it.upstream_id, it.downstream_id} | {h.from_system for h in it.hops} | {h.to_system for h in it.hops}
            systems |= touched
            ei = env_ints.get(it.id)
            missing = sorted(names.get(s, s) for s in touched if s not in inst_by_system)
            rows.append({"integration_id": it.id, "name": it.name, "status": ei["status"] if ei else "not_mapped",
                         "missing_systems": missing})
        sys_rows = [{"system_id": s, "system_name": names.get(s, s),
                     "instance": inst_by_system[s].instance_name if s in inst_by_system else None,
                     "mode": inst_by_system[s].mode if s in inst_by_system else "not_available",
                     "health_status": effective_health(inst_by_system[s]) if s in inst_by_system else "Unknown",
                     "version": inst_by_system[s].deployed_version if s in inst_by_system else None}
                    for s in sorted(systems, key=lambda s: names.get(s, s))]
        ready = all(r["mode"] != "not_available" for r in sys_rows) and all(r["status"] in ("connected", "virtualised")
                                                                          for r in rows)
        out.append({"journey": journey, "systems": sys_rows, "integrations": rows, "complete": ready})
    return out


@router.get("/impact")
def impact(system_id: str | None = None, instance_id: int | None = None, environment_id: int | None = None,
           user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """TOP-10: environments, journeys, bookings/projects and issues affected by an outage or change."""
    if not (system_id or instance_id or environment_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give system_id, instance_id or environment_id")
    names = system_names(db)
    q = select(SystemInstance).options(selectinload(SystemInstance.shared_with), selectinload(SystemInstance.environment))
    if instance_id:
        q = q.where(SystemInstance.id == instance_id)
    elif system_id:
        q = q.where(SystemInstance.system_id == system_id)
    else:
        q = q.where(SystemInstance.environment_id == environment_id)
    instances = [i for i in db.scalars(q) if i.environment.deleted_at is None]
    env_ids: set[int] = set()
    systems: set[str] = set()
    for i in instances:
        env_ids.add(i.environment_id)
        env_ids |= {e.id for e in i.shared_with}
        systems.add(i.system_id)
    if environment_id:
        env_ids.add(environment_id)
    cat = catalogue_integrations(db)
    affected_integrations = [it for it in cat.values()
                             if systems & ({it.upstream_id, it.downstream_id} | {h.from_system for h in it.hops}
                                           | {h.to_system for h in it.hops})]
    downstream = sorted({names.get(s, s) for it in affected_integrations
                         for s in [it.upstream_id, it.downstream_id] if s not in systems})
    t = now()
    bookings = db.scalars(select(Booking).options(selectinload(Booking.instances), selectinload(Booking.environment))
                          .where(Booking.environment_id.in_(env_ids), Booking.status.in_(["Requested", "Approved", "Active"]),
                                 Booking.end_at > t)).all()
    inst_ids = {i.id for i in instances}
    bk = [{"id": b.id, "environment": b.environment.name, "project": b.project, "team": b.team, "status": b.status,
           "start_at": aware(b.start_at), "end_at": aware(b.end_at), "requested_by": b.requested_by}
          for b in bookings if not b.instances or inst_ids & {i.id for i in b.instances} or not instance_id]
    issues = db.scalars(select(Issue).where(Issue.environment_id.in_(env_ids), Issue.status.in_(["open", "in_progress"])))
    envs = {e.id: e for e in db.scalars(select(Environment).where(Environment.id.in_(env_ids)))}
    return {
        "systems": [{"system_id": s, "system_name": names.get(s, s)} for s in sorted(systems)],
        "environments": [{"id": e.id, "name": e.name, "owner": e.owner, "support_group": e.support_group,
                          "status": e.status} for e in envs.values() if user.can_see(e)],
        "journeys": sorted({it.journey for it in affected_integrations if it.journey}),
        "integrations": [{"id": it.id, "name": it.name, "journey": it.journey} for it in affected_integrations],
        "dependent_systems": downstream,
        "bookings": bk, "projects": sorted({b["project"] for b in bk}),
        "open_issues": [{"id": i.id, "title": i.title, "severity": i.severity} for i in issues],
    }


# --- Import / export (TOP-11) -----------------------------------------------------------

INSTANCE_COLS = ["system_id", "instance_name", "url", "deployed_version", "build", "release", "mode",
                 "virtualisation_ref", "last_verified", "verified_by", "health_check_url", "notes"]
INT_COLS = ["integration_id", "name", "from_instance", "to_instance", "protocol", "pattern", "status", "endpoint",
            "last_verified", "verified_by", "notes"]


def _mermaid(env: Environment, instances: list[dict], integrations: list[dict]) -> str:
    def nid(name: str) -> str:
        return "n_" + "".join(c if c.isalnum() else "_" for c in name)

    lines = ["flowchart LR", f"  %% Topology of {env.name}"]
    for i in instances:
        label = f"{i['system_name'] or i['system_id']}<br/>{i['deployed_version'] or ''} {i['mode'] if i['mode'] != 'real' else ''}"
        lines.append(f'  {nid(i["instance_name"])}["{label.strip()}"]')
    for r in integrations:
        if r["from_instance"] and r["to_instance"]:
            arrow = "-.->" if r["status"] != "connected" else "-->"
            lines.append(f'  {nid(r["from_instance"])} {arrow}|{r["protocol"] or ""} {r["status"]}| {nid(r["to_instance"])}')
    return "\n".join(lines) + "\n"


@router.get("/environments/{env_id}/topology/export", response_class=Response)
def export_topology(env_id: int, format: Literal["json", "xlsx", "csv", "mermaid"] = "json",
                    user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    instances = [i for i in list_instances(env_id, user, db) if not i["shared_in"]]
    integrations = _env_integrations(db, env)
    fname = f"topology-{env.name}"
    audit(db, user, "export", "topology", env.id, {"format": format})
    db.commit()
    if format == "mermaid":
        return Response(_mermaid(env, instances, integrations), media_type="text/plain",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.mmd"'})
    inst_rows = [{c: i.get(c) for c in INSTANCE_COLS} for i in instances]
    int_rows = [{c: r.get(c) for c in INT_COLS} for r in integrations]
    if format == "json":
        body = {"environment": env.name, "exported_at": now().isoformat(), "instances": inst_rows,
                "integrations": int_rows}
        return Response(json.dumps(body, default=str, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.json"'})
    if format == "csv":
        from app.platform.common import tabular_response

        return tabular_response(inst_rows, "csv", fname, INSTANCE_COLS)
    wb = Workbook()
    ws = wb.active
    ws.title = "Instances"
    ws.append(INSTANCE_COLS)
    for r in inst_rows:
        ws.append([str(r[c]) if isinstance(r[c], date) else r[c] for c in INSTANCE_COLS])
    ws2 = wb.create_sheet("Integrations")
    ws2.append(INT_COLS)
    for r in int_rows:
        ws2.append([str(r[c]) if isinstance(r[c], date) else r[c] for c in INT_COLS])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})


def _sheet_rows(ws) -> list[dict[str, Any]]:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h).strip() if h else "" for h in rows[0]]
    return [{header[i]: v for i, v in enumerate(r) if i < len(header) and header[i]}
            for r in rows[1:] if any(v not in (None, "") for v in r)]


@router.post("/environments/{env_id}/topology/import")
async def import_topology(env_id: int, file: UploadFile = File(...), dry_run: bool = True,
                          user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """TOP-11: import instances (and integrations) from Excel, JSON or CSV with row-level errors.
    Rows upsert by instance_name."""
    from app.platform.common import fmt_of, parse_table

    env = get_env(db, env_id, user)
    check(user, CONTRIBUTOR, env, "import topology")
    content = await file.read()
    fmt = fmt_of(file.filename)
    try:
        if fmt == "xlsx":
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            inst_rows = _sheet_rows(wb["Instances"] if "Instances" in wb.sheetnames else wb.worksheets[0])
            int_rows = _sheet_rows(wb["Integrations"]) if "Integrations" in wb.sheetnames else []
        elif fmt == "json":
            data = json.loads(content)
            inst_rows, int_rows = data.get("instances", []), data.get("integrations", [])
        else:
            inst_rows, int_rows = parse_table(content, "csv"), []
    except Exception as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not read the file: {e}")
    names = system_names(db)
    existing = {i.instance_name: i for i in env.instances}
    issues, plan = [], []
    seen = set()
    for n, r in enumerate(inst_rows, start=2):
        r = {k: (None if v == "" else v) for k, v in r.items()}
        sid = str(r.get("system_id") or "").strip()
        if sid not in names:
            issues.append({"sheet": "Instances", "row": n, "column": "system_id",
                           "message": f"'{sid}' is not in the system catalogue"})
            continue
        r["system_id"] = sid
        r["instance_name"] = str(r.get("instance_name") or f"{sid}-{env.name}")
        if r["instance_name"] in seen:
            issues.append({"sheet": "Instances", "row": n, "column": "instance_name", "message": "Duplicate instance_name"})
            continue
        seen.add(r["instance_name"])
        for k in ("deployed_version", "build", "release"):
            if r.get(k) is not None:
                r[k] = str(r[k])
        try:
            clean = InstanceIn.model_validate({k: v for k, v in r.items() if k in InstanceIn.model_fields})
        except ValidationError as e:
            for err in e.errors():
                issues.append({"sheet": "Instances", "row": n, "column": str(err["loc"][0]), "message": err["msg"]})
            continue
        cur = existing.get(clean.instance_name or "")
        plan.append({"sheet": "Instances", "row": n, "action": "update" if cur else "create",
                     "instance_name": clean.instance_name, "_data": clean})
    known_names = set(existing) | seen
    for n, r in enumerate(int_rows, start=2):
        r = {k: (None if v == "" else v) for k, v in r.items()}
        for f in ("from_instance", "to_instance"):
            if r.get(f) and r[f] not in known_names:
                issues.append({"sheet": "Integrations", "row": n, "column": f,
                               "message": f"Unknown instance '{r[f]}'"})
        if r.get("integration_id") and db.get(Integration, r["integration_id"]) is None:
            issues.append({"sheet": "Integrations", "row": n, "column": "integration_id",
                           "message": f"'{r['integration_id']}' is not in the integration catalogue"})
        if r.get("status") and r["status"] not in ("connected", "broken", "not_connected", "virtualised"):
            issues.append({"sheet": "Integrations", "row": n, "column": "status",
                           "message": "use connected, broken, not_connected or virtualised"})
        plan.append({"sheet": "Integrations", "row": n, "action": "upsert",
                     "integration": r.get("integration_id") or r.get("name"), "_data": r})
    counts = {"instances": len(inst_rows), "integrations": len(int_rows)}
    public = [{k: v for k, v in p.items() if not k.startswith("_")} for p in plan]
    report = {"dry_run": dry_run, "valid": not issues, "issues": issues, "plan": public, "counts": counts,
              "bulk_operation_id": None}
    if dry_run or issues:
        return report
    changes = []
    for p in plan:
        if p["sheet"] != "Instances":
            continue
        clean: InstanceIn = p["_data"]
        cur = existing.get(clean.instance_name or "")
        if cur:
            before = {c: getattr(cur, c) for c in clean.model_fields_set if c != "shared_with"}
            apply(cur, {k: v for k, v in clean.model_dump(exclude_unset=True).items() if k != "shared_with"})
            bump(cur)
            changes.append({"entity": "instance", "id": cur.id, "before": json.loads(json.dumps(before, default=str)),
                            "after": None})
        else:
            inst = _create_instance(db, env, clean)
            existing[inst.instance_name] = inst
            changes.append({"entity": "instance", "id": inst.id, "before": None, "after": {"instance_name": inst.instance_name}})
    db.flush()
    for p in plan:
        if p["sheet"] != "Integrations":
            continue
        r = p["_data"]
        fi, ti = existing.get(r.get("from_instance")), existing.get(r.get("to_instance"))
        key_q = select(EnvironmentIntegration).where(EnvironmentIntegration.environment_id == env.id)
        key_q = (key_q.where(EnvironmentIntegration.integration_id == r["integration_id"]) if r.get("integration_id")
                 else key_q.where(EnvironmentIntegration.name == r.get("name")))
        ei = db.scalar(key_q) or EnvironmentIntegration(environment_id=env.id)
        is_new = ei.id is None
        ei.integration_id = r.get("integration_id")
        ei.name = r.get("name")
        ei.from_instance_id = fi.id if fi else None
        ei.to_instance_id = ti.id if ti else None
        for f in ("protocol", "pattern", "endpoint", "verified_by", "notes"):
            setattr(ei, f, r.get(f))
        ei.status = r.get("status") or "connected"
        lv = r.get("last_verified")
        ei.last_verified = date.fromisoformat(str(lv)[:10]) if lv else None
        db.add(ei)
        db.flush()
        if is_new:
            changes.append({"entity": "environment_integration", "id": ei.id, "before": None, "after": {}})
    op = BulkOperation(user=user.name, kind="topology", changes=changes,
                       summary=f"Topology import {file.filename} into {env.name}: {counts['instances']} instances, "
                               f"{counts['integrations']} integrations")
    db.add(op)
    db.flush()
    audit(db, user, "import", "topology", env.id, {"filename": file.filename, **counts, "bulk_operation_id": op.id})
    db.commit()
    report["bulk_operation_id"] = op.id
    return report


@router.get("/topology/environments")
def environments_for_system(system_id: str, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Where does a system exist? (TOP-02 reverse lookup)."""
    names = system_names(db)
    env_names = {e.id: e for e in db.scalars(select(Environment).where(Environment.deleted_at.is_(None)))}
    rows = db.scalars(select(SystemInstance).options(selectinload(SystemInstance.shared_with))
                      .where(SystemInstance.system_id == system_id))
    return [instance_out(i, names, {k: v.name for k, v in env_names.items()}) for i in rows
            if i.environment_id in env_names and user.can_see(env_names[i.environment_id])]


def resolve_instance(db: Session, env: Environment, ref: str | None, system: str | None) -> SystemInstance:
    q = select(SystemInstance).where(SystemInstance.environment_id == env.id)
    if ref:
        q = q.where(or_(SystemInstance.instance_name == ref, SystemInstance.system_id == ref))
    elif system:
        sid = db.scalar(select(System.id).where(or_(System.id == system, System.name == system)))
        q = q.where(SystemInstance.system_id == (sid or system))
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the instance or the system")
    inst = db.scalars(q).first()
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No instance of '{ref or system}' in {env.name}")
    return inst


__all__ = ["router", "resolve_instance", "resolve_env"]
