"""Issues and incidents (CHG-01..06), health and monitoring (HLT-01..07), test data (TDM-01..05)."""

from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import BOOKER, CONTRIBUTOR, User, check, require_viewer
from app.database import get_db
from app.models import Booking, DataJob, Environment, HealthResult, Issue, SystemInstance, TestDataSet
from app.platform.common import apply, audit, aware, bump, check_version, get_or_404, now
from app.platform.notify import emit
from app.platform.routers.environments import get_env, resolve_env
from app.platform.services import availability, effective_health, issue_sla, record_health, run_checks

router = APIRouter()

# --- Issues (CHG-01/02/03/05/06) --------------------------------------------------------

SEVERITY = Literal["critical", "high", "medium", "low"]
ISSUE_STATUS = Literal["open", "in_progress", "resolved", "closed"]


class IssueIn(BaseModel):
    environment_id: int
    instance_id: int | None = None
    booking_id: int | None = None
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    kind: Literal["issue", "incident"] = "issue"
    severity: SEVERITY = "medium"
    status: ISSUE_STATUS = "open"
    owner: str | None = None
    category: str | None = None
    known_issue: bool = False
    workaround: str | None = None
    external_system: Literal["servicenow", "jira", "azure_devops", "other"] | None = None
    external_ref: str | None = None
    external_url: str | None = None
    hours_lost: float | None = None
    opened_at: datetime | None = None


class IssuePatch(BaseModel):
    instance_id: int | None = None
    booking_id: int | None = None
    title: str | None = None
    description: str | None = None
    kind: Literal["issue", "incident"] | None = None
    severity: SEVERITY | None = None
    status: ISSUE_STATUS | None = None
    owner: str | None = None
    resolution: str | None = None
    category: str | None = None
    known_issue: bool | None = None
    workaround: str | None = None
    external_system: Literal["servicenow", "jira", "azure_devops", "other"] | None = None
    external_ref: str | None = None
    external_url: str | None = None
    hours_lost: float | None = None
    row_version: int | None = None


def issue_out(i: Issue, envs: dict[int, str] | None = None) -> dict[str, Any]:
    t = now()
    opened = aware(i.opened_at)
    end = aware(i.resolved_at) or t
    due = aware(i.sla_due_at)
    return {
        "id": i.id, "environment_id": i.environment_id, "environment": (envs or {}).get(i.environment_id),
        "instance_id": i.instance_id, "booking_id": i.booking_id, "title": i.title, "description": i.description,
        "kind": i.kind, "severity": i.severity, "status": i.status, "owner": i.owner, "resolution": i.resolution,
        "category": i.category, "known_issue": i.known_issue, "workaround": i.workaround,
        "external_system": i.external_system, "external_ref": i.external_ref, "external_url": i.external_url,
        "hours_lost": i.hours_lost, "opened_at": opened, "resolved_at": aware(i.resolved_at), "sla_due_at": due,
        "age_hours": round((end - opened).total_seconds() / 3600, 1),
        "sla_breached": bool(due and ((aware(i.resolved_at) or t) > due)), "created_by": i.created_by,
        "row_version": i.row_version,
    }


@router.get("/issues", tags=["issues"])
def list_issues(environment_id: int | None = None, status_: str | None = Query(None, alias="status"),
                severity: str | None = None, known: bool | None = None, q: str | None = None,
                external_ref: str | None = None, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    query = select(Issue).order_by(Issue.opened_at.desc())
    if environment_id:
        query = query.where(Issue.environment_id == environment_id)
    if status_:
        query = query.where(Issue.status.in_(status_.split(",")))
    if severity:
        query = query.where(Issue.severity.in_(severity.split(",")))
    if known is not None:
        query = query.where(Issue.known_issue.is_(known))
    if external_ref:
        query = query.where(Issue.external_ref == external_ref)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(Issue.title).like(like), func.lower(Issue.description).like(like)))
    envs = {e.id: e for e in db.scalars(select(Environment).where(Environment.deleted_at.is_(None)))}
    names = {k: v.name for k, v in envs.items()}
    return [issue_out(i, names) for i in db.scalars(query) if i.environment_id in envs and user.can_see(envs[i.environment_id])]


@router.post("/issues", status_code=status.HTTP_201_CREATED, tags=["issues"])
def create_issue(payload: IssueIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, payload.environment_id, user)
    check(user, BOOKER, env, "log issues")
    opened = aware(payload.opened_at) or now()
    i = Issue(**payload.model_dump(exclude={"opened_at"}), opened_at=opened, created_by=user.name,
              sla_due_at=issue_sla(db, payload.severity, opened))
    db.add(i)
    db.flush()
    audit(db, user, "create", "issue", i.id, {"environment": env.name, "title": i.title, "severity": i.severity})
    emit(db, "issue.created", f"[{i.severity}] {i.title} on {env.name}", i.description, environment=env,
         entity_type="issue", entity_id=i.id, recipients={env.owner or "", i.owner or ""},
         payload={"external_system": i.external_system, "external_ref": i.external_ref})
    db.commit()
    return issue_out(i, {env.id: env.name})


def _update_issue(db: Session, i: Issue, data: dict[str, Any], user: User | str) -> dict[str, Any]:
    if data.get("status") in ("resolved", "closed") and i.resolved_at is None:
        i.resolved_at = now()
    if data.get("status") in ("open", "in_progress"):
        i.resolved_at = None
    if "severity" in data and data["severity"] != i.severity:
        i.sla_due_at = issue_sla(db, data["severity"], aware(i.opened_at))
    diff = apply(i, data)
    if diff:
        bump(i)
        env = db.get(Environment, i.environment_id)
        audit(db, user, "update", "issue", i.id, {"changes": {k: [str(a), str(b)] for k, (a, b) in diff.items()}})
        emit(db, "issue.updated", f"{i.title}: {', '.join(diff)} changed", environment=env, entity_type="issue",
             entity_id=i.id, recipients={i.created_by or "", i.owner or ""},
             payload={"status": i.status, "external_system": i.external_system, "external_ref": i.external_ref})
    return diff


@router.patch("/issues/{issue_id}", tags=["issues"])
def update_issue(issue_id: int, payload: IssuePatch, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    i = get_or_404(db, Issue, issue_id, "Issue")
    env = get_env(db, i.environment_id, user)
    if i.created_by != user.name:
        check(user, CONTRIBUTOR, env, "update issues")
    check_version(i, payload.row_version)
    _update_issue(db, i, payload.model_dump(exclude_unset=True, exclude={"row_version"}), user)
    db.commit()
    return issue_out(i, {env.id: env.name})


@router.delete("/issues/{issue_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["issues"])
def delete_issue(issue_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    i = get_or_404(db, Issue, issue_id, "Issue")
    check(user, CONTRIBUTOR, get_env(db, i.environment_id, user), "delete issues")
    audit(db, user, "delete", "issue", i.id, {"title": i.title})
    db.delete(i)
    db.commit()


@router.get("/environments/{env_id}/known-issues", tags=["issues"])
def known_issues(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    return list_issues(env.id, "open,in_progress", None, True, None, None, user, db)


class TicketEvent(BaseModel):
    """Inbound status sync from ServiceNow / Jira / Azure DevOps (CHG-02, INT-04)."""

    external_system: Literal["servicenow", "jira", "azure_devops", "other"]
    external_ref: str
    status: str | None = None
    title: str | None = None
    description: str | None = None
    severity: str | None = None
    environment: str | None = Field(None, description="Environment name, to create the issue if it is new")
    external_url: str | None = None
    resolution: str | None = None


STATUS_MAP = {
    "new": "open", "open": "open", "to do": "open", "todo": "open", "backlog": "open",
    "in progress": "in_progress", "in_progress": "in_progress", "active": "in_progress", "work in progress": "in_progress",
    "on hold": "in_progress", "resolved": "resolved", "done": "resolved", "closed": "closed", "cancelled": "closed",
}
SEVERITY_MAP = {"1": "critical", "2": "high", "3": "medium", "4": "low", "p1": "critical", "p2": "high", "p3": "medium",
                "p4": "low", "highest": "critical", "high": "high", "medium": "medium", "low": "low", "lowest": "low",
                "critical": "critical"}


@router.post("/tickets/webhook", tags=["integrations"])
def ticket_webhook(ev: TicketEvent, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    issue = db.scalar(select(Issue).where(Issue.external_system == ev.external_system,
                                          Issue.external_ref == ev.external_ref))
    if issue is None:
        if not ev.environment:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"No issue linked to {ev.external_ref}; include `environment` to create one")
        env = resolve_env(db, ev.environment)
        check(user, CONTRIBUTOR, env, "sync tickets")
        issue = Issue(environment_id=env.id, title=ev.title or ev.external_ref, description=ev.description,
                      severity=SEVERITY_MAP.get((ev.severity or "").lower(), "medium"),
                      status=STATUS_MAP.get((ev.status or "").lower(), "open"), external_system=ev.external_system,
                      external_ref=ev.external_ref, external_url=ev.external_url, created_by=user.name, opened_at=now())
        issue.sla_due_at = issue_sla(db, issue.severity, issue.opened_at)
        db.add(issue)
        db.flush()
        audit(db, user, "ticket_sync_create", "issue", issue.id, ev.model_dump())
        db.commit()
        return {"action": "created", "issue_id": issue.id}
    check(user, CONTRIBUTOR, db.get(Environment, issue.environment_id), "sync tickets")
    data: dict[str, Any] = {}
    if ev.status and STATUS_MAP.get(ev.status.lower()):
        data["status"] = STATUS_MAP[ev.status.lower()]
    for f in ("title", "description", "external_url", "resolution"):
        if getattr(ev, f):
            data[f] = getattr(ev, f)
    if ev.severity and SEVERITY_MAP.get(ev.severity.lower()):
        data["severity"] = SEVERITY_MAP[ev.severity.lower()]
    diff = _update_issue(db, issue, data, user)
    db.commit()
    return {"action": "updated" if diff else "unchanged", "issue_id": issue.id, "changes": list(diff)}


# --- Health (HLT-01..07) ----------------------------------------------------------------


@router.get("/health/status", tags=["health"])
def status_page(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """HLT-07: status summary for delivery teams."""
    out = []
    for e in db.scalars(select(Environment).where(Environment.deleted_at.is_(None), Environment.status != "Retired")
                        .order_by(Environment.name)):
        if not user.can_see(e):
            continue
        out.append({"id": e.id, "name": e.name, "env_type": e.env_type, "lifecycle": e.status,
                    "health_status": effective_health(e), "checked_at": aware(e.health_checked_at),
                    "override": e.health_override_reason if e.health_override_status else None,
                    "instances": [{"id": i.id, "name": i.instance_name, "system_id": i.system_id,
                                   "health_status": effective_health(i), "checked_at": aware(i.health_checked_at)}
                                  for i in e.instances]})
    return out


@router.post("/environments/{env_id}/health/check", tags=["health"])
def check_now(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """HLT-02: run the configured HTTP / TCP checks now."""
    env = get_env(db, env_id, user)
    check(user, BOOKER, env, "run health checks")
    results = run_checks(db, env)
    db.commit()
    return {"environment": env.name, "health_status": effective_health(env), "results": results}


class HealthEventIn(BaseModel):
    environment: str
    instance: str | None = None
    status: Literal["Healthy", "Degraded", "Down", "Unknown"]
    message: str | None = None
    source: str = "monitor"
    response_ms: float | None = None


def _ingest(db: Session, ev: HealthEventIn, user: User) -> dict[str, Any]:
    env = resolve_env(db, ev.environment)
    check(user, CONTRIBUTOR, env, "report health")
    inst = None
    if ev.instance:
        inst = db.scalar(select(SystemInstance).where(SystemInstance.environment_id == env.id,
                                                      or_(SystemInstance.instance_name == ev.instance,
                                                          SystemInstance.system_id == ev.instance)))
        if inst is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Instance '{ev.instance}' not found in {env.name}")
    record_health(db, env, ev.status, instance=inst, source=f"monitor:{ev.source}", message=ev.message,
                  response_ms=ev.response_ms, user=user.name)
    return {"environment": env.name, "instance": inst.instance_name if inst else None, "status": ev.status}


@router.post("/health/events", tags=["health", "integrations"])
def ingest_health(events: list[HealthEventIn], user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """HLT-03: status from Dynatrace, Datadog, Splunk, AppDynamics or any tool (generic format)."""
    out = [_ingest(db, ev, user) for ev in events]
    db.commit()
    return {"accepted": len(out), "results": out}


@router.post("/health/alertmanager", tags=["health", "integrations"])
def ingest_alertmanager(body: dict[str, Any], user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """HLT-03: Prometheus Alertmanager webhook. Uses labels `environment` and optional `instance_name`/`system`,
    and `severity` (critical → Down, otherwise Degraded). Resolved alerts set Healthy."""
    out = []
    for a in body.get("alerts", []):
        labels = a.get("labels", {})
        env = labels.get("environment") or labels.get("env")
        if not env:
            continue
        st = "Healthy" if a.get("status") == "resolved" else ("Down" if labels.get("severity") == "critical" else "Degraded")
        out.append(_ingest(db, HealthEventIn(environment=env, instance=labels.get("instance_name") or labels.get("system"),
                                             status=st, message=a.get("annotations", {}).get("summary") or labels.get("alertname"),
                                             source="prometheus"), user))
    db.commit()
    return {"accepted": len(out), "results": out}


@router.get("/environments/{env_id}/health/history", tags=["health"])
def health_history(env_id: int, days: int = 30, instance_id: int | None = None, user: User = Depends(require_viewer),
                   db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    q = (select(HealthResult).where(HealthResult.environment_id == env.id,
                                    HealthResult.checked_at >= now() - timedelta(days=days))
         .order_by(HealthResult.checked_at.desc()).limit(1000))
    if instance_id:
        q = q.where(HealthResult.instance_id == instance_id)
    return [{"id": r.id, "instance_id": r.instance_id, "status": r.status, "checked_at": aware(r.checked_at),
             "response_ms": r.response_ms, "message": r.message, "source": r.source} for r in db.scalars(q)]


@router.get("/environments/{env_id}/health/metrics", tags=["health"])
def health_metrics(env_id: int, days: int = 30, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """HLT-05: uptime %, outage count and mean time to restore."""
    env = get_env(db, env_id, user)
    end = now()
    return {"environment": env.name, "days": days, **availability(db, env.id, end - timedelta(days=days), end)}


# --- Test data (TDM-01..05) -------------------------------------------------------------


class DataSetIn(BaseModel):
    environment_id: int
    name: str = Field(min_length=1)
    description: str | None = None
    source: str | None = None
    source_environment_id: int | None = None
    system_id: str | None = None
    volume: str | None = None
    refresh_date: date | None = None
    masking_status: Literal["masked", "unmasked", "synthetic", "partial"] = "masked"
    production_derived: bool = False
    owner: str | None = None


class DataSetPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    source: str | None = None
    source_environment_id: int | None = None
    system_id: str | None = None
    volume: str | None = None
    refresh_date: date | None = None
    masking_status: Literal["masked", "unmasked", "synthetic", "partial"] | None = None
    production_derived: bool | None = None
    owner: str | None = None


def ds_out(d: TestDataSet, envs: dict[int, str], jobs: list[DataJob] | None = None) -> dict[str, Any]:
    return {c.name: getattr(d, c.name) for c in TestDataSet.__table__.columns} | {
        "environment": envs.get(d.environment_id), "source_environment": envs.get(d.source_environment_id),
        "reserved_until": aware(d.reserved_until),
        "refresh_age_days": (now().date() - d.refresh_date).days if d.refresh_date else None,
        "risk": "high" if d.production_derived and d.masking_status in ("unmasked", "partial") else
                ("medium" if d.production_derived else "low"),
        "jobs": [job_out(j) for j in (jobs or [])],
    }


def job_out(j: DataJob) -> dict[str, Any]:
    return {"id": j.id, "dataset_id": j.dataset_id, "kind": j.kind, "status": j.status, "owner": j.owner,
            "started_at": aware(j.started_at), "finished_at": aware(j.finished_at), "notes": j.notes}


@router.get("/test-data", tags=["test data"])
def list_datasets(environment_id: int | None = None, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    q = select(TestDataSet).order_by(TestDataSet.name)
    if environment_id:
        q = q.where(TestDataSet.environment_id == environment_id)
    envs = {e.id: e for e in db.scalars(select(Environment).where(Environment.deleted_at.is_(None)))}
    names = {k: v.name for k, v in envs.items()}
    jobs: dict[int, list[DataJob]] = {}
    for j in db.scalars(select(DataJob).order_by(DataJob.id.desc())):
        jobs.setdefault(j.dataset_id, []).append(j)
    return [ds_out(d, names, jobs.get(d.id, [])[:10]) for d in db.scalars(q)
            if d.environment_id in envs and user.can_see(envs[d.environment_id])]


def _sync_env_flags(db: Session, env_id: int) -> None:
    """TDM-05: an environment holding production-derived data is flagged automatically."""
    env = db.get(Environment, env_id)
    if env is not None and db.scalar(select(func.count()).select_from(TestDataSet).where(
            TestDataSet.environment_id == env_id, TestDataSet.production_derived.is_(True))):
        env.production_derived_data = True
        env.sensitive_data = True


@router.post("/test-data", status_code=status.HTTP_201_CREATED, tags=["test data"])
def create_dataset(payload: DataSetIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, payload.environment_id, user)
    check(user, CONTRIBUTOR, env, "manage test data")
    d = TestDataSet(**payload.model_dump())
    db.add(d)
    db.flush()
    _sync_env_flags(db, env.id)
    audit(db, user, "create", "test_data", d.id, payload.model_dump(mode="json"))
    db.commit()
    return ds_out(d, {e.id: e.name for e in db.scalars(select(Environment))})


@router.patch("/test-data/{ds_id}", tags=["test data"])
def update_dataset(ds_id: int, payload: DataSetPatch, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    d = get_or_404(db, TestDataSet, ds_id, "Test data set")
    check(user, CONTRIBUTOR, get_env(db, d.environment_id, user), "manage test data")
    diff = apply(d, payload.model_dump(exclude_unset=True))
    _sync_env_flags(db, d.environment_id)
    audit(db, user, "update", "test_data", d.id, {"changes": {k: [str(a), str(b)] for k, (a, b) in diff.items()}})
    db.commit()
    return ds_out(d, {e.id: e.name for e in db.scalars(select(Environment))})


@router.delete("/test-data/{ds_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["test data"])
def delete_dataset(ds_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    d = get_or_404(db, TestDataSet, ds_id, "Test data set")
    check(user, CONTRIBUTOR, get_env(db, d.environment_id, user), "manage test data")
    audit(db, user, "delete", "test_data", d.id, {"name": d.name})
    db.delete(d)
    db.commit()


class ReserveIn(BaseModel):
    booking_id: int | None = None
    until: datetime | None = None


@router.post("/test-data/{ds_id}/reserve", tags=["test data"])
def reserve(ds_id: int, payload: ReserveIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """TDM-04: reserve a data set (or accounts) for a project/booking."""
    d = get_or_404(db, TestDataSet, ds_id, "Test data set")
    check(user, BOOKER, get_env(db, d.environment_id, user), "reserve test data")
    if d.reserved_by and (d.reserved_until is None or aware(d.reserved_until) > now()) and d.reserved_by != user.name:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Reserved by {d.reserved_by} until {aware(d.reserved_until)}")
    until = aware(payload.until)
    if payload.booking_id:
        b = get_or_404(db, Booking, payload.booking_id, "Booking")
        until = until or aware(b.end_at)
    d.reserved_for_booking_id, d.reserved_by, d.reserved_until = payload.booking_id, user.name, until
    audit(db, user, "reserve", "test_data", d.id, {"booking_id": payload.booking_id, "until": until})
    db.commit()
    return ds_out(d, {e.id: e.name for e in db.scalars(select(Environment))})


@router.post("/test-data/{ds_id}/release", tags=["test data"])
def release(ds_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    d = get_or_404(db, TestDataSet, ds_id, "Test data set")
    if d.reserved_by != user.name:
        check(user, CONTRIBUTOR, get_env(db, d.environment_id, user), "release other people's reservations")
    d.reserved_for_booking_id = d.reserved_by = d.reserved_until = None
    audit(db, user, "release", "test_data", d.id, {})
    db.commit()
    return ds_out(d, {e.id: e.name for e in db.scalars(select(Environment))})


class JobIn(BaseModel):
    kind: Literal["refresh", "mask", "subset", "synthesise"]
    status: Literal["scheduled", "running", "succeeded", "failed"] = "scheduled"
    owner: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    notes: str | None = None


@router.post("/test-data/{ds_id}/jobs", status_code=status.HTTP_201_CREATED, tags=["test data"])
def add_job(ds_id: int, payload: JobIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """TDM-02: record a refresh / masking job; a succeeded refresh updates the data set's refresh date."""
    d = get_or_404(db, TestDataSet, ds_id, "Test data set")
    check(user, CONTRIBUTOR, get_env(db, d.environment_id, user), "record data jobs")
    j = DataJob(dataset_id=d.id, **payload.model_dump())
    j.owner = j.owner or user.name
    db.add(j)
    if payload.status == "succeeded":
        if payload.kind == "refresh":
            d.refresh_date = (aware(payload.finished_at) or now()).date()
        if payload.kind == "mask":
            d.masking_status = "masked"
    db.flush()
    audit(db, user, "data_job", "test_data", d.id, payload.model_dump(mode="json"))
    db.commit()
    return job_out(j)


@router.patch("/data-jobs/{job_id}", tags=["test data"])
def update_job(job_id: int, payload: JobIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    j = get_or_404(db, DataJob, job_id, "Job")
    d = db.get(TestDataSet, j.dataset_id)
    check(user, CONTRIBUTOR, get_env(db, d.environment_id, user), "update data jobs")
    apply(j, payload.model_dump(exclude_unset=True))
    if j.status == "succeeded" and j.kind == "refresh":
        d.refresh_date = (aware(j.finished_at) or now()).date()
    if j.status == "succeeded" and j.kind == "mask":
        d.masking_status = "masked"
    audit(db, user, "data_job_update", "test_data", d.id, payload.model_dump(mode="json", exclude_unset=True))
    db.commit()
    return job_out(j)
