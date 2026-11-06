"""Deployments and versions (DEP-01..07), CI/CD ingestion (DEP-03, INT-03)."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CONTRIBUTOR, ENV_MANAGER, User, check, require_viewer
from app.database import get_db
from app.flows.models import System
from app.models import Deployment, Environment, PromotionPath, SystemInstance
from app.platform.common import audit, aware, get_or_404, now
from app.platform.notify import emit
from app.platform.routers.environments import get_env, resolve_env
from app.platform.routers.topology import resolve_instance
from app.platform.services import effective_config, freeze_windows, system_names

router = APIRouter(tags=["deployments"])

OUTCOMES = Literal["success", "failed", "rolled_back", "in_progress"]


class DeploymentIn(BaseModel):
    instance_id: int | None = None
    environment: str | None = Field(None, description="Environment name or id (with system or instance)")
    system: str | None = Field(None, description="System id or name")
    instance: str | None = Field(None, description="Instance name")
    version: str = Field(min_length=1, max_length=100)
    build: str | None = None
    commit_sha: str | None = None
    release: str | None = None
    pipeline: str | None = None
    pipeline_run_url: str | None = None
    tool: Literal["jenkins", "azure_devops", "github_actions", "gitlab", "other"] | None = None
    outcome: OUTCOMES = "success"
    deployed_by: str | None = None
    deployed_at: datetime | None = None
    notes: str | None = None
    override_reason: str | None = Field(None, description="Required to deploy into an enforced freeze")


def dep_out(d: Deployment, names: dict[str, str], envs: dict[int, str], insts: dict[int, str]) -> dict[str, Any]:
    return {"id": d.id, "instance_id": d.instance_id, "instance": insts.get(d.instance_id),
            "environment_id": d.environment_id, "environment": envs.get(d.environment_id), "system_id": d.system_id,
            "system_name": names.get(d.system_id), "version": d.version, "build": d.build, "commit_sha": d.commit_sha,
            "release": d.release, "deployed_by": d.deployed_by, "deployed_at": aware(d.deployed_at),
            "pipeline": d.pipeline, "pipeline_run_url": d.pipeline_run_url, "outcome": d.outcome,
            "rollback_of_id": d.rollback_of_id, "source": d.source, "tool": d.tool, "notes": d.notes}


def _lookups(db: Session):
    return (system_names(db), {e.id: e.name for e in db.scalars(select(Environment))},
            dict(db.execute(select(SystemInstance.id, SystemInstance.instance_name)).tuples().all()))


def record_deployment(db: Session, user: User, payload: DeploymentIn, source: str) -> tuple[Deployment, list[str]]:
    if payload.instance_id:
        inst = get_or_404(db, SystemInstance, payload.instance_id, "Instance")
        env = get_env(db, inst.environment_id, user)
    else:
        if not payload.environment:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "environment: required without instance_id")
        env = resolve_env(db, payload.environment)
        inst = resolve_instance(db, env, payload.instance, payload.system)
    check(user, CONTRIBUTOR, env, "record deployments")
    at = payload.deployed_at or now()
    warnings = []
    for f in freeze_windows(db, env.id, at, at):
        msg = f"{f.kind.capitalize()} '{f.title}' is in force until {aware(f.end_at):%d %b %Y %H:%M} UTC"
        if f.enforce and not payload.override_reason and source == "manual" and not user.can(ENV_MANAGER, env):
            raise HTTPException(status.HTTP_409_CONFLICT, f"{msg}. Give an override reason or ask an environment manager.")
        warnings.append(msg)
    if env.status == "Frozen":
        warnings.append(f"{env.name} is Frozen")
    d = Deployment(instance_id=inst.id, environment_id=env.id, system_id=inst.system_id, version=payload.version,
                   build=payload.build, commit_sha=payload.commit_sha, release=payload.release,
                   deployed_by=payload.deployed_by or user.name, deployed_at=at, pipeline=payload.pipeline,
                   pipeline_run_url=payload.pipeline_run_url, outcome=payload.outcome, source=source,
                   tool=payload.tool, notes=payload.notes)
    db.add(d)
    if payload.outcome == "success":
        inst.deployed_version = payload.version
        inst.build = payload.build
        inst.commit_sha = payload.commit_sha
        inst.release = payload.release or inst.release
        inst.row_version += 1
    db.flush()
    audit(db, user, "deployment", "instance", inst.id,
          {"environment": env.name, "system_id": inst.system_id, "version": payload.version, "outcome": payload.outcome,
           "source": source, "warnings": warnings, "override_reason": payload.override_reason})
    emit(db, "deployment.recorded", f"{inst.system_id} {payload.version} → {env.name} ({payload.outcome})",
         "; ".join(warnings) or None, environment=env, entity_type="deployment", entity_id=d.id,
         payload={"system_id": inst.system_id, "version": payload.version, "outcome": payload.outcome})
    return d, warnings


@router.get("/deployments")
def list_deployments(environment_id: int | None = None, system_id: str | None = None, instance_id: int | None = None,
                     limit: int = Query(200, le=2000), user: User = Depends(require_viewer),
                     db: Session = Depends(get_db)):
    q = select(Deployment).order_by(Deployment.deployed_at.desc(), Deployment.id.desc()).limit(limit)
    if environment_id:
        q = q.where(Deployment.environment_id == environment_id)
    if system_id:
        q = q.where(Deployment.system_id == system_id)
    if instance_id:
        q = q.where(Deployment.instance_id == instance_id)
    names, envs, insts = _lookups(db)
    visible = {e.id for e in db.scalars(select(Environment)) if user.can_see(e)}
    return [dep_out(d, names, envs, insts) for d in db.scalars(q) if d.environment_id in visible]


@router.post("/deployments", status_code=status.HTTP_201_CREATED)
def create_deployment(payload: DeploymentIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    d, warnings = record_deployment(db, user, payload, "manual")
    db.commit()
    return dep_out(d, *_lookups(db)) | {"warnings": warnings}


@router.post("/ci/deployments", status_code=status.HTTP_201_CREATED, tags=["pipelines"])
def ci_deployment(payload: DeploymentIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """DEP-03 / INT-03: called by Jenkins, Azure DevOps, GitHub Actions or GitLab with an API token."""
    d, warnings = record_deployment(db, user, payload, "ci")
    db.commit()
    return dep_out(d, *_lookups(db)) | {"warnings": warnings}


@router.post("/deployments/{dep_id}/rollback", status_code=status.HTTP_201_CREATED)
def rollback_deployment(dep_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Record a rollback to the last successful version before this deployment."""
    d = get_or_404(db, Deployment, dep_id, "Deployment")
    prev = db.scalars(select(Deployment).where(Deployment.instance_id == d.instance_id, Deployment.outcome == "success",
                                               Deployment.deployed_at < d.deployed_at, Deployment.id != d.id)
                      .order_by(Deployment.deployed_at.desc())).first()
    if prev is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No earlier successful deployment to roll back to")
    nd, warnings = record_deployment(db, user, DeploymentIn(instance_id=d.instance_id, version=prev.version,
                                                            build=prev.build, commit_sha=prev.commit_sha,
                                                            release=prev.release, notes=f"Rollback of #{d.id}",
                                                            override_reason="rollback"), "manual")
    nd.rollback_of_id = d.id
    d.outcome = "rolled_back"
    db.commit()
    return dep_out(nd, *_lookups(db)) | {"warnings": warnings}


@router.get("/version-matrix")
def version_matrix(env_ids: str | None = None, env_type: str | None = None, domain: str | None = None,
                   differences_only: bool = False, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """DEP-04: rows are systems, columns are environments."""
    q = select(Environment).where(Environment.deleted_at.is_(None))
    if env_ids:
        q = q.where(Environment.id.in_([int(x) for x in env_ids.split(",") if x]))
    if env_type:
        q = q.where(Environment.env_type == env_type)
    order = {t: i for i, t in enumerate(["DEV", "SIT", "UAT", "PreProd", "Perf", "Training", "Sandbox"])}
    envs = sorted([e for e in db.scalars(q) if user.can_see(e)], key=lambda e: (order.get(e.env_type, 99), e.name))
    systems = {s.id: s for s in db.scalars(select(System))}
    cells: dict[str, dict[int, dict[str, Any]]] = {}
    for i in db.scalars(select(SystemInstance).where(SystemInstance.environment_id.in_([e.id for e in envs]))):
        cells.setdefault(i.system_id, {})[i.environment_id] = {
            "instance_id": i.id, "version": i.deployed_version, "build": i.build, "release": i.release, "mode": i.mode}
    rows = []
    for sid, by_env in sorted(cells.items(), key=lambda kv: systems[kv[0]].name if kv[0] in systems else kv[0]):
        s = systems.get(sid)
        if domain and (s is None or s.domain != domain):
            continue
        versions = {c["version"] for c in by_env.values() if c["version"]}
        row = {"system_id": sid, "system_name": s.name if s else sid, "domain": s.domain if s else None,
               "cells": {str(k): v for k, v in by_env.items()}, "distinct_versions": len(versions),
               "differs": len(versions) > 1 or len(by_env) < len(envs)}
        if differences_only and not row["differs"]:
            continue
        rows.append(row)
    return {"environments": [{"id": e.id, "name": e.name, "env_type": e.env_type} for e in envs], "rows": rows}


@router.get("/drift")
def drift(environment_id: int, baseline_id: int | None = None, user: User = Depends(require_viewer),
          db: Session = Depends(get_db)):
    """DEP-05: versions and configuration compared with a baseline (or the next environment on a promotion path)."""
    env = get_env(db, environment_id, user)
    if baseline_id is None:
        baseline_id = _next_on_path(db, env.id)
        if baseline_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "baseline_id: choose a baseline (no promotion path defines a higher environment)")
    base = get_env(db, baseline_id, user)
    names = system_names(db)
    mine = {i.system_id: i for i in env.instances}
    theirs = {i.system_id: i for i in base.instances}
    versions = []
    for sid in sorted(set(mine) | set(theirs)):
        a, b = mine.get(sid), theirs.get(sid)
        if a is None or b is None or (a.deployed_version or "") != (b.deployed_version or ""):
            versions.append({"system_id": sid, "system_name": names.get(sid, sid),
                             "version": a.deployed_version if a else None,
                             "baseline_version": b.deployed_version if b else None,
                             "kind": "missing" if a is None else ("extra" if b is None else "version")})
    ca = {r["variable"].key: r["variable"] for r in effective_config(db, env)}
    cb = {r["variable"].key: r["variable"] for r in effective_config(db, base)}
    config = []
    for k in sorted(set(ca) | set(cb)):
        a, b = ca.get(k), cb.get(k)
        if a is None or b is None:
            config.append({"key": k, "kind": "missing" if a is None else "extra"})
        elif a.is_secret != b.is_secret:
            config.append({"key": k, "kind": "secret_flag"})
        elif a.value_type != b.value_type:
            config.append({"key": k, "kind": "type", "value": a.value_type, "baseline_value": b.value_type})
        elif a.is_secret:
            if (a.vault_ref or a.value) != (b.vault_ref or b.value):
                config.append({"key": k, "kind": "secret_value"})
        elif a.value != b.value:
            config.append({"key": k, "kind": "value", "value": a.value, "baseline_value": b.value})
    structural = [c for c in config if c["kind"] not in ("value", "secret_value")]
    return {"environment": {"id": env.id, "name": env.name}, "baseline": {"id": base.id, "name": base.name},
            "versions": versions, "config": config, "drifted": bool(versions or structural),
            "structural_config_drift": len(structural)}


def _next_on_path(db: Session, env_id: int) -> int | None:
    for p in db.scalars(select(PromotionPath)):
        ids = [s["environment_id"] for s in p.stages]
        if env_id in ids and ids.index(env_id) + 1 < len(ids):
            return ids[ids.index(env_id) + 1]
    return None


# --- Promotion paths (DEP-06) -----------------------------------------------------------


class Stage(BaseModel):
    environment_id: int
    gate_status: Literal["open", "passed", "failed", "blocked"] = "open"
    gate_note: str | None = None


class PathIn(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    stages: list[Stage] = Field(min_length=2)


def _path_out(db: Session, p: PromotionPath) -> dict[str, Any]:
    envs = {e.id: e for e in db.scalars(select(Environment))}
    stage_ids = [s["environment_id"] for s in p.stages]
    insts: dict[int, dict[str, str | None]] = {i: {} for i in stage_ids}
    for i in db.scalars(select(SystemInstance).where(SystemInstance.environment_id.in_(stage_ids))):
        insts[i.environment_id][i.system_id] = i.deployed_version
    names = system_names(db)
    systems = sorted({s for d in insts.values() for s in d}, key=lambda s: names.get(s, s))
    pending = []
    for idx in range(len(stage_ids) - 1):
        lo, hi = stage_ids[idx], stage_ids[idx + 1]
        for s in systems:
            v_lo, v_hi = insts[lo].get(s), insts[hi].get(s)
            if v_lo and v_lo != v_hi:
                pending.append({"system_id": s, "system_name": names.get(s, s), "from": envs[lo].name,
                                "to": envs[hi].name, "version": v_lo, "current": v_hi,
                                "gate_status": p.stages[idx]["gate_status"]})
    return {"id": p.id, "name": p.name, "description": p.description,
            "stages": [{**s, "environment": envs[s["environment_id"]].name if s["environment_id"] in envs else None}
                       for s in p.stages],
            "versions": [{"system_id": s, "system_name": names.get(s, s),
                          "by_stage": {str(e): insts[e].get(s) for e in stage_ids}} for s in systems],
            "pending_promotions": pending}


@router.get("/promotion-paths")
def list_paths(_: User = Depends(require_viewer), db: Session = Depends(get_db)):
    return [_path_out(db, p) for p in db.scalars(select(PromotionPath).order_by(PromotionPath.name))]


@router.post("/promotion-paths", status_code=status.HTTP_201_CREATED)
def create_path(payload: PathIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    check(user, ENV_MANAGER, None, "define promotion paths")
    for s in payload.stages:
        get_env(db, s.environment_id, user)
    p = PromotionPath(name=payload.name, description=payload.description,
                      stages=[s.model_dump() for s in payload.stages])
    db.add(p)
    db.flush()
    audit(db, user, "create", "promotion_path", p.id, {"name": p.name})
    db.commit()
    return _path_out(db, p)


@router.put("/promotion-paths/{path_id}")
def update_path(path_id: int, payload: PathIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    check(user, ENV_MANAGER, None, "change promotion paths and gates")
    p = get_or_404(db, PromotionPath, path_id, "Promotion path")
    p.name, p.description, p.stages = payload.name, payload.description, [s.model_dump() for s in payload.stages]
    audit(db, user, "update", "promotion_path", p.id, {"stages": p.stages})
    db.commit()
    return _path_out(db, p)


@router.delete("/promotion-paths/{path_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_path(path_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    check(user, ENV_MANAGER, None, "delete promotion paths")
    p = get_or_404(db, PromotionPath, path_id, "Promotion path")
    audit(db, user, "delete", "promotion_path", p.id, {"name": p.name})
    db.delete(p)
    db.commit()

