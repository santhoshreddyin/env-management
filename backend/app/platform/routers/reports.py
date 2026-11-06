"""Search and reporting (RPT-01..10, BKG-07, CHG-05)."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import User, require_viewer
from app.database import get_db
from app.flows.models import Integration, System
from app.models import (
    Booking,
    CalendarEvent,
    Deployment,
    Environment,
    EnvironmentIntegration,
    HealthResult,
    Issue,
    SystemInstance,
    TestDataSet,
    Variable,
)
from app.platform.common import aware, now, tabular_response
from app.platform.routers.environments import get_env
from app.platform.services import (
    availability,
    credential_warnings,
    effective_health,
    refresh_bookings,
    stale,
    system_names,
)

router = APIRouter(tags=["reports"])
FMT = Literal["json", "csv", "xlsx"]
USED = ["Approved", "Active", "Completed"]


def _visible_envs(db: Session, user: User, include_retired: bool = False) -> list[Environment]:
    q = select(Environment).where(Environment.deleted_at.is_(None))
    if not include_retired:
        q = q.where(Environment.status != "Retired")
    return [e for e in db.scalars(q.order_by(Environment.name)) if user.can_see(e)]


def _maybe_export(rows: list[dict[str, Any]], format: str, name: str, payload: Any = None):
    if format == "json":
        return payload if payload is not None else rows
    return tabular_response(rows, format, name)


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _clip(s: datetime, e: datetime, start: datetime, end: datetime) -> tuple[datetime, datetime] | None:
    s, e = max(s, start), min(e, end)
    return (s, e) if e > s else None


def _range(start: datetime | None, end: datetime | None, default_days: int = 30) -> tuple[datetime, datetime]:
    end = aware(end) or now()
    start = aware(start) or end - timedelta(days=default_days)
    return start, end


# --- Search (RPT-01) --------------------------------------------------------------------


@router.get("/search")
def search(q: str = Query(min_length=1), limit: int = 10, user: User = Depends(require_viewer),
           db: Session = Depends(get_db)):
    like = f"%{q.lower()}%"
    envs = {e.id: e for e in _visible_envs(db, user, include_retired=True)}
    names = {k: v.name for k, v in envs.items()}
    out: dict[str, list[dict[str, Any]]] = {}
    out["environments"] = [
        {"id": e.id, "label": e.name, "detail": f"{e.env_type} · {e.status}", "link": f"/environments/{e.id}"}
        for e in envs.values()
        if q.lower() in " ".join(filter(None, [e.name, e.description, e.owner, e.programme, e.purpose,
                                              " ".join(e.tags or [])])).lower()][:limit]
    out["systems"] = [{"id": s.id, "label": s.name, "detail": f"{s.type} · {s.domain or ''}", "link": f"/catalogue?system={s.id}"}
                      for s in db.scalars(select(System).where(or_(func.lower(System.name).like(like),
                                                                   func.lower(System.id).like(like))).limit(limit))]
    out["instances"] = [{"id": i.id, "label": i.instance_name, "detail": f"{names[i.environment_id]} · {i.deployed_version or ''}",
                         "link": f"/environments/{i.environment_id}?tab=topology"}
                        for i in db.scalars(select(SystemInstance).where(or_(
                            func.lower(SystemInstance.instance_name).like(like), func.lower(SystemInstance.url).like(like))).limit(50))
                        if i.environment_id in envs][:limit]
    out["integrations"] = [{"id": i.id, "label": i.name, "detail": i.journey or "", "link": f"/flows?integration={i.id}"}
                           for i in db.scalars(select(Integration).where(or_(func.lower(Integration.name).like(like),
                                                                             func.lower(Integration.id).like(like))).limit(limit))]
    out["variables"] = [{"id": v.id, "label": v.key, "detail": names.get(v.environment_id, "global"),
                         "link": f"/environments/{v.environment_id}?tab=config" if v.environment_id else "/config"}
                        for v in db.scalars(select(Variable).where(or_(
                            func.lower(Variable.key).like(like), func.lower(Variable.description).like(like),
                            (Variable.is_secret.is_(False)) & func.lower(Variable.value).like(like))).limit(50))
                        if v.environment_id is None or v.environment_id in envs][:limit]
    out["bookings"] = [{"id": b.id, "label": b.project, "detail": f"{names[b.environment_id]} · {b.status}",
                        "link": f"/bookings?booking={b.id}"}
                       for b in db.scalars(select(Booking).where(or_(func.lower(Booking.project).like(like),
                                                                     func.lower(Booking.team).like(like),
                                                                     func.lower(Booking.purpose).like(like))).limit(50))
                       if b.environment_id in envs][:limit]
    out["issues"] = [{"id": i.id, "label": i.title, "detail": f"{names[i.environment_id]} · {i.severity} · {i.status}",
                      "link": f"/issues?issue={i.id}"}
                     for i in db.scalars(select(Issue).where(or_(func.lower(Issue.title).like(like),
                                                                 func.lower(Issue.external_ref).like(like))).limit(50))
                     if i.environment_id in envs][:limit]
    out["test_data"] = [{"id": d.id, "label": d.name, "detail": names[d.environment_id],
                         "link": f"/environments/{d.environment_id}?tab=data"}
                        for d in db.scalars(select(TestDataSet).where(func.lower(TestDataSet.name).like(like)).limit(50))
                        if d.environment_id in envs][:limit]
    return {"q": q, "results": out, "total": sum(len(v) for v in out.values())}


# --- Dashboard (RPT-03) -----------------------------------------------------------------


@router.get("/reports/dashboard")
def dashboard(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    refresh_bookings(db)
    envs = _visible_envs(db, user)
    ids = {e.id for e in envs}
    t = now()
    by_status: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    by_health: dict[str, int] = defaultdict(int)
    for e in envs:
        by_status[e.status] += 1
        by_type[e.env_type] += 1
        by_health[effective_health(e)] += 1
    month_start = t - timedelta(days=30)
    util = utilisation_rows(db, envs, month_start, t)
    avg_util = round(sum(r["utilisation_pct"] for r in util) / len(util), 1) if util else 0
    avail = [availability(db, e.id, month_start, t)["uptime_pct"] for e in envs]
    avail = [a for a in avail if a is not None]
    issues = [i for i in db.scalars(select(Issue).where(Issue.status.in_(["open", "in_progress"]))) if i.environment_id in ids]
    sev: dict[str, int] = defaultdict(int)
    for i in issues:
        sev[i.severity] += 1
    active = [b for b in db.scalars(select(Booking).options(selectinload(Booking.environment))
                                    .where(Booking.status == "Active")) if b.environment_id in ids]
    upcoming_changes = db.scalars(select(CalendarEvent).where(CalendarEvent.end_at > t,
                                                              CalendarEvent.start_at < t + timedelta(days=14))
                                  .order_by(CalendarEvent.start_at)).all()
    names = {e.id: e.name for e in envs}
    pending = db.scalar(select(func.count()).select_from(Booking).where(Booking.status == "Requested",
                                                                        Booking.environment_id.in_(ids))) or 0
    dq = data_quality_rows(db, user)
    return {
        "environments": len(envs), "by_status": by_status, "by_type": by_type, "by_health": by_health,
        "utilisation_30d_pct": avg_util,
        "availability_30d_pct": round(sum(avail) / len(avail), 2) if avail else None,
        "open_issues": len(issues), "open_issues_by_severity": sev,
        "sla_breached": sum(1 for i in issues if i.sla_due_at and aware(i.sla_due_at) < t),
        "active_bookings": [{"id": b.id, "environment": b.environment.name, "project": b.project, "team": b.team,
                             "end_at": aware(b.end_at)} for b in active],
        "pending_approvals": pending,
        "upcoming_changes": [{"id": c.id, "kind": c.kind, "title": c.title, "start_at": aware(c.start_at),
                              "end_at": aware(c.end_at), "environment": names.get(c.environment_id, "All")}
                             for c in upcoming_changes if c.environment_id is None or c.environment_id in ids][:10],
        "unhealthy": [{"id": e.id, "name": e.name, "health_status": effective_health(e)} for e in envs
                      if effective_health(e) in ("Down", "Degraded")],
        "data_quality": dq["summary"],
        "recent_deployments": [{"id": d.id, "environment": names.get(d.environment_id), "system_id": d.system_id,
                                "version": d.version, "outcome": d.outcome, "deployed_at": aware(d.deployed_at)}
                               for d in db.scalars(select(Deployment).order_by(Deployment.deployed_at.desc()).limit(30))
                               if d.environment_id in ids][:8],
    }


# --- Utilisation, contention, forecast (RPT-04/05, BKG-07) ------------------------------


def utilisation_rows(db: Session, envs: list[Environment], start: datetime, end: datetime) -> list[dict[str, Any]]:
    window_h = (end - start).total_seconds() / 3600
    by_env: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
    for b in db.scalars(select(Booking).where(Booking.status.in_(USED), Booking.start_at < end, Booking.end_at > start)):
        c = _clip(aware(b.start_at), aware(b.end_at), start, end)
        if c:
            by_env[b.environment_id].append(c)
    rows = []
    for e in envs:
        merged = _merge(by_env.get(e.id, []))
        booked = sum((x[1] - x[0]).total_seconds() for x in merged) / 3600
        rows.append({"environment_id": e.id, "environment": e.name, "env_type": e.env_type, "programme": e.programme,
                     "booked_hours": round(booked, 1), "idle_hours": round(window_h - booked, 1),
                     "utilisation_pct": round(100 * booked / window_h, 1) if window_h else 0,
                     "bookings": len(by_env.get(e.id, []))})
    return rows


@router.get("/reports/utilisation")
def utilisation(start: datetime | None = None, end: datetime | None = None,
                group_by: Literal["environment", "team", "project"] = "environment", format: FMT = "json",
                user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """RPT-04: booked versus idle time."""
    refresh_bookings(db)
    start, end = _range(start, end)
    envs = _visible_envs(db, user)
    if group_by == "environment":
        rows = utilisation_rows(db, envs, start, end)
    else:
        ids = {e.id for e in envs}
        acc: dict[str, dict[str, Any]] = {}
        for b in db.scalars(select(Booking).where(Booking.status.in_(USED), Booking.start_at < end, Booking.end_at > start)):
            if b.environment_id not in ids:
                continue
            c = _clip(aware(b.start_at), aware(b.end_at), start, end)
            if not c:
                continue
            key = (b.team if group_by == "team" else b.project) or "(none)"
            r = acc.setdefault(key, {group_by: key, "booked_hours": 0.0, "bookings": 0, "environments": set()})
            r["booked_hours"] += (c[1] - c[0]).total_seconds() / 3600
            r["bookings"] += 1
            r["environments"].add(b.environment_id)
        names = {e.id: e.name for e in envs}
        rows = [{**r, "booked_hours": round(r["booked_hours"], 1),
                 "environments": ", ".join(sorted(names[i] for i in r["environments"]))}
                for r in sorted(acc.values(), key=lambda r: -r["booked_hours"])]
    return _maybe_export(rows, format, f"utilisation-{group_by}",
                         {"start": start, "end": end, "group_by": group_by, "rows": rows})


def _weeks(start: datetime, weeks: int) -> list[tuple[datetime, datetime]]:
    monday = (start - timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return [(monday + timedelta(weeks=i), monday + timedelta(weeks=i + 1)) for i in range(weeks)]


@router.get("/reports/contention")
def contention(start: datetime | None = None, weeks: int = Query(12, le=52), format: FMT = "json",
               user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """RPT-05: over-subscribed environments and periods (demand includes requested and waitlisted bookings)."""
    start = aware(start) or now()
    envs = _visible_envs(db, user)
    ids = {e.id for e in envs}
    names = {e.id: e.name for e in envs}
    periods = _weeks(start, weeks)
    end = periods[-1][1]
    bookings = [b for b in db.scalars(select(Booking).where(
        Booking.status.in_(["Requested", "Approved", "Active", "Waitlisted"]), Booking.start_at < end,
        Booking.end_at > periods[0][0])) if b.environment_id in ids]
    rows = []
    for env_id in sorted(ids, key=lambda i: names[i]):
        for ps, pe in periods:
            mine = [b for b in bookings if b.environment_id == env_id and aware(b.start_at) < pe and aware(b.end_at) > ps]
            if not mine:
                continue
            demand = sum((_clip(aware(b.start_at), aware(b.end_at), ps, pe) or (ps, ps))[1].timestamp()
                         - (_clip(aware(b.start_at), aware(b.end_at), ps, pe) or (ps, ps))[0].timestamp() for b in mine) / 3600
            supply = (pe - ps).total_seconds() / 3600
            overlapping = sum(1 for i, a in enumerate(mine) for b in mine[i + 1:]
                              if aware(a.start_at) < aware(b.end_at) and aware(b.start_at) < aware(a.end_at)
                              and (not a.instances or not b.instances))
            rows.append({"environment_id": env_id, "environment": names[env_id], "week_start": ps.date().isoformat(),
                         "bookings": len(mine), "projects": ", ".join(sorted({b.project for b in mine})),
                         "demand_hours": round(demand, 1), "supply_hours": round(supply, 1),
                         "demand_pct": round(100 * demand / supply, 1), "overlaps": overlapping,
                         "waitlisted": sum(b.status == "Waitlisted" for b in mine),
                         "oversubscribed": demand > supply or overlapping > 0})
    rows.sort(key=lambda r: (-r["demand_pct"], r["week_start"]))
    return _maybe_export(rows, format, "contention", {"weeks": weeks, "rows": rows,
                                                      "oversubscribed": [r for r in rows if r["oversubscribed"]]})


@router.get("/reports/forecast")
def forecast(weeks: int = Query(12, le=52), format: FMT = "json", user: User = Depends(require_viewer),
             db: Session = Depends(get_db)):
    """BKG-07: demand versus supply per environment type and week."""
    envs = [e for e in _visible_envs(db, user) if e.status in ("Available", "In use", "Frozen", "Provisioning")]
    by_type: dict[str, list[int]] = defaultdict(list)
    for e in envs:
        by_type[e.env_type].append(e.id)
    periods = _weeks(now(), weeks)
    bookings = list(db.scalars(select(Booking).where(Booking.status.in_(["Requested", "Approved", "Active", "Waitlisted"]),
                                                     Booking.end_at > periods[0][0], Booking.start_at < periods[-1][1])))
    rows = []
    for t, ids in sorted(by_type.items()):
        for ps, pe in periods:
            demand = 0.0
            for b in bookings:
                if b.environment_id in ids:
                    c = _clip(aware(b.start_at), aware(b.end_at), ps, pe)
                    if c:
                        demand += (c[1] - c[0]).total_seconds() / 3600
            supply = len(ids) * (pe - ps).total_seconds() / 3600
            rows.append({"env_type": t, "week_start": ps.date().isoformat(), "environments": len(ids),
                         "demand_hours": round(demand, 1), "supply_hours": round(supply, 1),
                         "demand_pct": round(100 * demand / supply, 1) if supply else None,
                         "shortfall_environments": max(0, round(demand / ((pe - ps).total_seconds() / 3600) - len(ids), 1))})
    return _maybe_export(rows, format, "forecast", {"weeks": weeks, "rows": rows})


# --- Readiness (RPT-06) -----------------------------------------------------------------


@router.get("/reports/readiness/{env_id}")
def readiness(env_id: int, baseline_id: int | None = None, start: datetime | None = None,
              user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Is the environment ready for a test cycle? Versions, health, data, issues, freezes, bookings."""
    from app.platform.routers.bookings import known_issues as kissues
    from app.platform.routers.variables import template_check

    env = get_env(db, env_id, user)
    start = aware(start) or now()
    names = system_names(db)
    checks = []

    def add(area: str, status_: str, detail: str):
        checks.append({"area": area, "status": status_, "detail": detail})

    h = effective_health(env)
    add("Health", {"Healthy": "green", "Degraded": "amber", "Down": "red"}.get(h, "amber"),
        f"Environment is {h}" + (f" ({env.health_override_reason})" if env.health_override_status else ""))
    down = [i for i in env.instances if effective_health(i) in ("Down", "Degraded")]
    add("Components", "red" if any(effective_health(i) == "Down" for i in down) else ("amber" if down else "green"),
        ", ".join(f"{i.instance_name}: {effective_health(i)}" for i in down) or f"{len(env.instances)} instances OK")
    unavailable = [i for i in env.instances if i.mode == "not_available"]
    virtual = [i for i in env.instances if i.mode in ("virtualised", "stubbed", "mocked")]
    add("Topology", "amber" if unavailable else "green",
        f"{len(unavailable)} not available, {len(virtual)} virtualised/stubbed" if (unavailable or virtual)
        else "All systems real")
    stale_i = [i for i in env.instances if stale(i.last_verified)]
    add("Verification", "amber" if stale_i else "green",
        f"{len(stale_i)} instances not verified in 90 days" if stale_i else "All instances recently verified")
    if baseline_id:
        from app.platform.routers.deployments import drift

        d = drift(env.id, baseline_id, user, db)
        add("Versions", "amber" if d["versions"] else "green",
            f"{len(d['versions'])} systems differ from {d['baseline']['name']}" if d["versions"] else
            f"Versions match {d['baseline']['name']}")
    unversioned = [i for i in env.instances if not i.deployed_version and i.mode == "real"]
    if unversioned:
        add("Version records", "amber", f"No version recorded for {', '.join(i.instance_name for i in unversioned[:5])}")
    tc = template_check(db, env)
    add("Configuration", "red" if tc["missing"] else "green",
        f"Missing required keys: {', '.join(m['key'] for m in tc['missing'])}" if tc["missing"]
        else "Required configuration present")
    data = list(db.scalars(select(TestDataSet).where(TestDataSet.environment_id == env.id)))
    old = [d for d in data if not d.refresh_date or (now().date() - d.refresh_date).days > 90]
    unmasked = [d for d in data if d.production_derived and d.masking_status != "masked"]
    add("Test data", "red" if unmasked else ("amber" if (old or not data) else "green"),
        "; ".join(filter(None, [f"{len(unmasked)} unmasked production-derived" if unmasked else "",
                                f"{len(old)} not refreshed in 90 days" if old else "",
                                "No data sets catalogued" if not data else ""])) or f"{len(data)} data sets ready")
    issues = [i for i in db.scalars(select(Issue).where(Issue.environment_id == env.id,
                                                        Issue.status.in_(["open", "in_progress"])))]
    blocking = [i for i in issues if i.severity in ("critical", "high")]
    add("Issues", "red" if blocking else ("amber" if issues else "green"),
        f"{len(blocking)} critical/high, {len(issues)} open" if issues else "No open issues")
    freezes = [f for f in db.scalars(select(CalendarEvent).where(
        or_(CalendarEvent.environment_id == env.id, CalendarEvent.environment_id.is_(None)),
        CalendarEvent.end_at > start, CalendarEvent.start_at < start + timedelta(days=14)))]
    add("Calendar", "amber" if freezes else "green",
        "; ".join(f"{f.kind} '{f.title}' {aware(f.start_at):%d %b}" for f in freezes) or "No freezes or outages in 14 days")
    add("Lifecycle", "green" if env.status in ("Available", "In use") else "amber", f"Status is {env.status}")
    score = {"red": 0, "amber": 1, "green": 2}
    overall = min((c["status"] for c in checks), key=lambda s: score[s])
    return {"environment": {"id": env.id, "name": env.name, "env_type": env.env_type}, "overall": overall,
            "checks": checks, "known_issues": kissues(db, env.id),
            "versions": [{"system": names.get(i.system_id, i.system_id), "instance": i.instance_name,
                          "version": i.deployed_version, "mode": i.mode, "health": effective_health(i)}
                         for i in env.instances],
            "generated_at": now()}


# --- Cost (RPT-07) ----------------------------------------------------------------------


@router.get("/reports/cost")
def cost(group_by: Literal["environment", "programme", "cost_centre", "project"] = "programme",
         start: datetime | None = None, end: datetime | None = None, format: FMT = "json",
         user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Monthly run cost by environment / programme / cost centre; `project` allocates cost by booked hours."""
    start, end = _range(start, end)
    envs = _visible_envs(db, user)
    months = (end - start).total_seconds() / (30 * 86400)
    if group_by == "project":
        alloc: dict[str, float] = defaultdict(float)
        hours: dict[str, float] = defaultdict(float)
        window_h = (end - start).total_seconds() / 3600
        by_id = {e.id: e for e in envs}
        for b in db.scalars(select(Booking).where(Booking.status.in_(USED), Booking.start_at < end, Booking.end_at > start)):
            e = by_id.get(b.environment_id)
            c = _clip(aware(b.start_at), aware(b.end_at), start, end)
            if e is None or c is None:
                continue
            h = (c[1] - c[0]).total_seconds() / 3600
            hours[b.project] += h
            alloc[b.project] += (e.run_cost or 0) * months * h / window_h if window_h else 0
        rows = [{"project": p, "booked_hours": round(hours[p], 1), "allocated_cost": round(alloc[p], 2)}
                for p in sorted(alloc, key=lambda p: -alloc[p])]
    else:
        acc: dict[str, dict[str, Any]] = {}
        for e in envs:
            key = (e.name if group_by == "environment" else getattr(e, group_by)) or "(unassigned)"
            r = acc.setdefault(key, {group_by: key, "environments": 0, "monthly_cost": 0.0, "period_cost": 0.0})
            r["environments"] += 1
            r["monthly_cost"] += e.run_cost or 0
            r["period_cost"] += (e.run_cost or 0) * months
        rows = [{**r, "monthly_cost": round(r["monthly_cost"], 2), "period_cost": round(r["period_cost"], 2)}
                for r in sorted(acc.values(), key=lambda r: -r["monthly_cost"])]
    return _maybe_export(rows, format, f"cost-{group_by}", {"start": start, "end": end, "group_by": group_by,
                                                            "rows": rows})


# --- Data quality (RPT-09, TOP-09, SEC-04/05) -------------------------------------------


def data_quality_rows(db: Session, user: User) -> dict[str, Any]:
    envs = _visible_envs(db, user)
    ids = {e.id for e in envs}
    names = {e.id: e.name for e in envs}
    sys_names = system_names(db)
    findings: list[dict[str, Any]] = []

    def add(kind: str, entity: str, ref: Any, detail: str, link: str | None = None, severity: str = "warning"):
        findings.append({"kind": kind, "entity": entity, "ref": ref, "detail": detail, "link": link,
                         "severity": severity})

    for e in envs:
        for f in ("owner", "support_group"):
            if not getattr(e, f):
                add(f"missing_{f}", "environment", e.name, f"{e.name} has no {f.replace('_', ' ')}",
                    f"/environments/{e.id}")
        if e.status == "Requested" and e.sla_due_at and aware(e.sla_due_at) < now():
            add("request_sla_breached", "environment", e.name, f"Request for {e.name} is past its SLA",
                f"/environments/{e.id}", "error")
    for i in db.scalars(select(SystemInstance)):
        if i.environment_id not in ids:
            continue
        where = f"{i.instance_name} in {names[i.environment_id]}"
        if i.last_verified is None:
            add("unverified_instance", "instance", i.id, f"{where} has never been verified",
                f"/environments/{i.environment_id}?tab=topology")
        elif stale(i.last_verified):
            add("stale_instance", "instance", i.id, f"{where} last verified {i.last_verified}",
                f"/environments/{i.environment_id}?tab=topology")
        if i.system_id not in sys_names:
            add("unknown_system", "instance", i.id, f"{where} refers to '{i.system_id}', which is not in the catalogue",
                f"/environments/{i.environment_id}?tab=topology", "error")
        if i.mode in ("virtualised", "stubbed", "mocked") and not i.virtualisation_ref:
            add("missing_virtualisation_ref", "instance", i.id, f"{where} is {i.mode} without an asset reference",
                f"/environments/{i.environment_id}?tab=topology")
    for ei in db.scalars(select(EnvironmentIntegration)):
        if ei.environment_id in ids and ei.last_verified is None and ei.status == "connected":
            add("unverified_integration", "integration", ei.id,
                f"Integration {ei.integration_id or ei.name} in {names[ei.environment_id]} never verified",
                f"/environments/{ei.environment_id}?tab=topology", "info")
    for s in db.scalars(select(System)):
        if not s.owner:
            add("system_missing_owner", "system", s.id, f"System {s.name} has no owner", "/catalogue")
    for v in db.scalars(select(Variable)):
        if v.environment_id is not None and v.environment_id not in ids:
            continue
        where = f"{v.key} in {names.get(v.environment_id, 'global')}"
        link = f"/environments/{v.environment_id}?tab=config" if v.environment_id else "/config"
        if v.is_secret and not v.vault_ref:
            add("secret_without_vault_ref", "variable", v.id, f"{where} is stored as a value, not a vault reference",
                link, "error")
        if v.is_secret and v.rotation_due_at and aware(v.rotation_due_at) < now():
            add("rotation_overdue", "variable", v.id, f"{where} was due for rotation on {aware(v.rotation_due_at):%d %b %Y}",
                link, "error")
        for w in credential_warnings(v.key, v.value, v.is_secret):
            add("credential_in_plain_field", "variable", v.id, w, link, "error")
    for d in db.scalars(select(TestDataSet)):
        if d.environment_id in ids and d.production_derived and d.masking_status != "masked":
            add("unmasked_production_data", "test_data", d.id, f"{d.name} in {names[d.environment_id]} is production-"
                f"derived and {d.masking_status}", f"/environments/{d.environment_id}?tab=data", "error")
    by_kind: dict[str, int] = defaultdict(int)
    for f in findings:
        by_kind[f["kind"]] += 1
    total_checks = max(1, len(envs) * 2 + db.scalar(select(func.count()).select_from(SystemInstance)) + 1)
    score = max(0, round(100 - 100 * sum(1 for f in findings if f["severity"] != "info") / total_checks))
    return {"summary": {"score": score, "findings": len(findings), "by_kind": by_kind,
                        "errors": sum(f["severity"] == "error" for f in findings)},
            "findings": findings}


@router.get("/reports/data-quality")
def data_quality(format: FMT = "json", user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    r = data_quality_rows(db, user)
    return _maybe_export(r["findings"], format, "data-quality", r)


# --- Test impact (CHG-05) ---------------------------------------------------------------


@router.get("/reports/test-impact")
def test_impact(start: datetime | None = None, end: datetime | None = None, format: FMT = "json",
                user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Hours of booked test time lost to outages (Down health) and incidents, per booking."""
    start, end = _range(start, end, 90)
    envs = {e.id: e for e in _visible_envs(db, user)}
    rows = []
    for b in db.scalars(select(Booking).where(Booking.status.in_(USED), Booking.start_at < end, Booking.end_at > start)):
        if b.environment_id not in envs:
            continue
        bs, be = aware(b.start_at), aware(b.end_at)
        series = db.execute(select(HealthResult.checked_at, HealthResult.status).where(
            HealthResult.environment_id == b.environment_id, HealthResult.instance_id.is_(None),
            HealthResult.checked_at < be).order_by(HealthResult.checked_at)).all()
        down = []
        cur = None
        for at, st in series:
            at = aware(at)
            if st == "Down" and cur is None:
                cur = at
            elif st != "Down" and cur is not None:
                down.append((cur, at))
                cur = None
        if cur is not None:
            down.append((cur, be))
        outage_h = sum(((_clip(s, e, bs, be) or (bs, bs))[1] - (_clip(s, e, bs, be) or (bs, bs))[0]).total_seconds()
                       for s, e in down) / 3600
        incidents = [i for i in db.scalars(select(Issue).where(Issue.environment_id == b.environment_id,
                                                               Issue.opened_at < be,
                                                               or_(Issue.resolved_at.is_(None), Issue.resolved_at > bs)))]
        logged = sum(i.hours_lost or 0 for i in incidents if i.booking_id in (None, b.id))
        rows.append({"booking_id": b.id, "environment": envs[b.environment_id].name, "project": b.project,
                     "team": b.team, "start_at": bs, "end_at": be, "outage_hours": round(outage_h, 1),
                     "incident_hours_logged": round(logged, 1), "incidents": len(incidents),
                     "hours_lost": round(max(outage_h, logged), 1)})
    rows.sort(key=lambda r: -r["hours_lost"])
    return _maybe_export(rows, format, "test-impact", {"start": start, "end": end, "rows": rows,
                                                       "total_hours_lost": round(sum(r["hours_lost"] for r in rows), 1)})


@router.get("/reports/issues")
def issue_report(format: FMT = "json", user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """CHG-06: issue ageing, SLA breaches and root-cause categories."""
    envs = {e.id: e for e in _visible_envs(db, user, include_retired=True)}
    issues = [i for i in db.scalars(select(Issue)) if i.environment_id in envs]
    t = now()
    by_cat: dict[str, dict[str, Any]] = {}
    for i in issues:
        c = by_cat.setdefault(i.category or "(uncategorised)", {"category": i.category or "(uncategorised)",
                                                                 "total": 0, "open": 0, "sla_breached": 0,
                                                                 "hours_to_resolve": []})
        c["total"] += 1
        if i.status in ("open", "in_progress"):
            c["open"] += 1
        if i.sla_due_at and (aware(i.resolved_at) or t) > aware(i.sla_due_at):
            c["sla_breached"] += 1
        if i.resolved_at:
            c["hours_to_resolve"].append((aware(i.resolved_at) - aware(i.opened_at)).total_seconds() / 3600)
    rows = [{**{k: v for k, v in c.items() if k != "hours_to_resolve"},
             "mean_hours_to_resolve": round(sum(c["hours_to_resolve"]) / len(c["hours_to_resolve"]), 1)
             if c["hours_to_resolve"] else None} for c in sorted(by_cat.values(), key=lambda c: -c["total"])]
    ageing = {"<1d": 0, "1-3d": 0, "3-7d": 0, "7-30d": 0, ">30d": 0}
    for i in issues:
        if i.status not in ("open", "in_progress"):
            continue
        d = (t - aware(i.opened_at)).total_seconds() / 86400
        ageing["<1d" if d < 1 else "1-3d" if d < 3 else "3-7d" if d < 7 else "7-30d" if d < 30 else ">30d"] += 1
    return _maybe_export(rows, format, "issues", {"by_category": rows, "ageing": ageing})
