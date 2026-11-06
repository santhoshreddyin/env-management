"""Domain logic shared by routers and the scheduler."""

import re
import socket
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import User
from app.config import settings
from app.flows.models import Integration, System
from app.models import (
    Booking,
    CalendarEvent,
    Environment,
    HealthResult,
    Issue,
    SystemInstance,
    Variable,
    instance_shares,
)
from app.platform.common import audit, aware, now, policy
from app.platform.notify import emit

# --- Lifecycle (ENV-03) -----------------------------------------------------------------

LIFECYCLE = ["Requested", "Provisioning", "Available", "In use", "Frozen", "Under maintenance",
             "Decommissioning", "Retired"]
TRANSITIONS: dict[str, list[str]] = {
    "Requested": ["Provisioning", "Retired"],
    "Provisioning": ["Available", "Retired"],
    "Available": ["In use", "Frozen", "Under maintenance", "Decommissioning"],
    "In use": ["Available", "Frozen", "Under maintenance", "Decommissioning"],
    "Frozen": ["Available", "In use", "Under maintenance"],
    "Under maintenance": ["Available", "In use", "Frozen"],
    "Decommissioning": ["Retired", "Available"],
    "Retired": [],
}
BOOKABLE = {"Available", "In use", "Frozen"}


def transition(db: Session, env: Environment, to: str, user: User, reason: str | None = None) -> None:
    if to not in LIFECYCLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown status '{to}'")
    if to == env.status:
        return
    if to not in TRANSITIONS[env.status]:
        allowed = ", ".join(TRANSITIONS[env.status]) or "none"
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Cannot move {env.name} from {env.status} to {to}. Allowed: {allowed}")
    if to == "Retired" and env.status == "Decommissioning":
        open_items = [i["item"] for i in (env.decommission_checklist or []) if not i.get("done")]
        if open_items:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Complete the decommissioning checklist first: {', '.join(open_items)}")
        active = db.scalar(select(Booking.id).where(Booking.environment_id == env.id,
                                                    Booking.status.in_(["Requested", "Approved", "Active"]),
                                                    Booking.end_at > now()).limit(1))
        if active:
            raise HTTPException(status.HTTP_409_CONFLICT, "Cancel or complete current and future bookings first")
        env.retirement_date = env.retirement_date or now().date()
    if to == "Decommissioning" and not env.decommission_checklist:
        from app.platform.common import get_setting

        env.decommission_checklist = [{"item": i, "done": False} for i in get_setting(db, "decommission_checklist")]
    old = env.status
    env.status = to
    env.row_version += 1
    env.updated_by = user.name
    audit(db, user, "environment_transition", "environment", env.id, {"from": old, "to": to, "reason": reason})
    emit(db, "environment.status_changed", f"{env.name}: {old} → {to}", reason, environment=env,
         entity_type="environment", entity_id=env.id, recipients={env.owner or ""}, payload={"from": old, "to": to})


# --- Bookings (BKG-03/05/08) ------------------------------------------------------------

LIVE_BOOKING = ["Requested", "Approved", "Active"]
PRIORITY_RANK = {"production_fix": 1, "release": 2, "project": 3, "training": 4}


def env_footprint(db: Session, env_id: int) -> set[int]:
    """All system instances a whole-environment booking touches: own plus shared-in instances."""
    own = set(db.scalars(select(SystemInstance.id).where(SystemInstance.environment_id == env_id)))
    shared = set(db.scalars(select(instance_shares.c.instance_id).where(instance_shares.c.environment_id == env_id)))
    return own | shared


def booking_footprint(db: Session, b: Booking, cache: dict[int, set[int]] | None = None) -> set[int]:
    if b.instances:
        return {i.id for i in b.instances}
    cache = cache if cache is not None else {}
    if b.environment_id not in cache:
        cache[b.environment_id] = env_footprint(db, b.environment_id)
    return cache[b.environment_id]


def find_conflicts(db: Session, env_id: int, start: datetime, end: datetime, instance_ids: list[int],
                   exclude_id: int | None = None, priority: str = "project") -> list[dict[str, Any]]:
    cache: dict[int, set[int]] = {}
    mine_whole = not instance_ids
    mine = set(instance_ids) if instance_ids else env_footprint(db, env_id)
    cache[env_id] = env_footprint(db, env_id)
    q = (select(Booking).options(selectinload(Booking.instances), selectinload(Booking.environment))
         .where(Booking.status.in_(LIVE_BOOKING), Booking.start_at < end, Booking.end_at > start))
    if exclude_id:
        q = q.where(Booking.id != exclude_id)
    out = []
    names = {}
    for other in db.scalars(q):
        theirs = booking_footprint(db, other, cache)
        overlap = mine & theirs
        if other.environment_id == env_id and (mine_whole or not other.instances or overlap):
            kind = "environment" if (mine_whole or not other.instances) else "component"
        elif overlap:
            kind = "shared_component"
        else:
            continue
        if overlap and not names:
            names = dict(db.execute(select(SystemInstance.id, SystemInstance.instance_name)).tuples().all())
        out.append({
            "booking_id": other.id, "environment_id": other.environment_id,
            "environment": other.environment.name if other.environment else None,
            "project": other.project, "team": other.team, "status": other.status, "priority": other.priority,
            "start_at": aware(other.start_at), "end_at": aware(other.end_at), "type": kind,
            "shared_components": sorted(names.get(i, str(i)) for i in overlap) if kind != "environment" else [],
            "outranked": PRIORITY_RANK.get(priority, 9) < PRIORITY_RANK.get(other.priority, 9),
        })
    return out


def freeze_windows(db: Session, env_id: int | None, start: datetime, end: datetime,
                   kinds: tuple[str, ...] = ("freeze", "blackout")) -> list[CalendarEvent]:
    q = select(CalendarEvent).where(CalendarEvent.kind.in_(kinds), CalendarEvent.start_at < end,
                                    CalendarEvent.end_at > start)
    q = q.where(or_(CalendarEvent.environment_id.is_(None), CalendarEvent.environment_id == env_id))
    return list(db.scalars(q))


def refresh_bookings(db: Session) -> int:
    """Advance booking statuses by time: start, auto-release at end (BKG-05), escalate, notify expiry."""
    t = now()
    changed = 0
    rows = db.scalars(select(Booking).options(selectinload(Booking.environment))
                      .where(Booking.status.in_(LIVE_BOOKING))).all()
    escalate_h = policy(db, "booking_escalation_hours")
    notice_h = policy(db, "booking_expiry_notice_hours")
    for b in rows:
        start, end = aware(b.start_at), aware(b.end_at)
        env_name = b.environment.name if b.environment else "?"
        if b.status == "Approved" and start <= t < end:
            b.status = "Active"
            changed += 1
        if b.status in ("Approved", "Active") and end <= t:
            b.status = "Completed"
            changed += 1
            audit(db, "system", "booking_auto_released", "booking", b.id, {"end_at": end})
            emit(db, "booking.released", f"Booking {b.project} on {env_name} ended and was released",
                 environment=b.environment, entity_type="booking", entity_id=b.id, recipients={b.requested_by})
            promote_waitlist(db, b.environment_id)
        elif b.status == "Requested" and end <= t:
            b.status = "Cancelled"
            b.decision_note = "Expired before approval"
            changed += 1
        elif b.status == "Requested" and not b.escalated and aware(b.created_at) + timedelta(hours=escalate_h) <= t:
            b.escalated = True
            changed += 1
            emit(db, "booking.escalated", f"Booking request {b.project} on {env_name} awaits a decision",
                 f"Requested by {b.requested_by} more than {escalate_h} hours ago", environment=b.environment,
                 entity_type="booking", entity_id=b.id,
                 recipients={b.environment.delivery_manager or "", b.environment.owner or ""} if b.environment else set())
        if b.status == "Active" and not b.expiry_notified and end - timedelta(hours=notice_h) <= t:
            b.expiry_notified = True
            changed += 1
            emit(db, "booking.expiring", f"Booking {b.project} on {env_name} ends {end:%d %b %H:%M} UTC",
                 environment=b.environment, entity_type="booking", entity_id=b.id, recipients={b.requested_by})
    if changed:
        db.commit()
    return changed


def promote_waitlist(db: Session, env_id: int) -> None:
    """BKG-08: when capacity frees up, offer it to waitlisted bookings in priority order."""
    waiting = db.scalars(select(Booking).options(selectinload(Booking.instances))
                         .where(Booking.environment_id == env_id, Booking.status == "Waitlisted",
                                Booking.end_at > now())).all()
    waiting = sorted(waiting, key=lambda b: (PRIORITY_RANK.get(b.priority, 9), b.created_at))
    for b in waiting:
        if not find_conflicts(db, env_id, aware(b.start_at), aware(b.end_at), [i.id for i in b.instances],
                              exclude_id=b.id):
            b.status = "Requested"
            emit(db, "booking.decided", f"Waitlisted booking {b.project} can now go ahead (awaiting approval)",
                 entity_type="booking", entity_id=b.id, recipients={b.requested_by})
            db.flush()


# --- Health (HLT-*) ---------------------------------------------------------------------

HEALTH = ["Healthy", "Degraded", "Down", "Unknown"]


def effective_health(obj: Any) -> str:
    until = aware(obj.health_override_until)
    if obj.health_override_status and (until is None or until > now()):
        return obj.health_override_status
    return obj.health_status or "Unknown"


def probe(url: str) -> tuple[str, float | None, str]:
    """Run one check: http(s)://… (GET) or tcp://host:port (connect)."""
    start = time.perf_counter()
    parsed = urlparse(url)
    try:
        if parsed.scheme == "tcp":
            with socket.create_connection((parsed.hostname, parsed.port or 80),
                                          timeout=settings.health_check_timeout_seconds):
                pass
            ms = (time.perf_counter() - start) * 1000
            return ("Healthy" if ms < settings.health_degraded_ms else "Degraded"), ms, "TCP connect ok"
        r = httpx.get(url, timeout=settings.health_check_timeout_seconds, follow_redirects=True)
        ms = (time.perf_counter() - start) * 1000
        if r.status_code >= 500:
            return "Down", ms, f"HTTP {r.status_code}"
        if r.status_code >= 400 or ms >= settings.health_degraded_ms:
            return "Degraded", ms, f"HTTP {r.status_code}"
        return "Healthy", ms, f"HTTP {r.status_code}"
    except Exception as e:
        return "Down", None, f"{e.__class__.__name__}: {e}"[:300]


def rollup(statuses: list[str]) -> str:
    known = [s for s in statuses if s != "Unknown"]
    if not known:
        return "Unknown"
    if all(s == "Down" for s in known):
        return "Down"
    if any(s in ("Down", "Degraded") for s in known):
        return "Degraded"
    return "Healthy"


def record_health(db: Session, env: Environment, status_: str, *, instance: SystemInstance | None = None,
                  source: str = "check", message: str | None = None, response_ms: float | None = None,
                  user: str = "system") -> None:
    """Store a result, update current status, recompute the environment roll-up and notify on change."""
    if status_ not in HEALTH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Status must be one of {', '.join(HEALTH)}")
    t = now()
    db.add(HealthResult(environment_id=env.id, instance_id=instance.id if instance else None, status=status_,
                        checked_at=t, response_ms=response_ms, message=message, source=source))
    before = effective_health(env)
    if instance is not None:
        instance.health_status = status_
        instance.health_checked_at = t
        if not env.health_check_url:
            env.health_status = rollup([effective_health(i) for i in env.instances])
            env.health_checked_at = t
    else:
        env.health_status = status_
        env.health_checked_at = t
    after = effective_health(env)
    if before != after:
        if instance is not None:  # keep an environment-level series for availability metrics
            db.add(HealthResult(environment_id=env.id, status=after, checked_at=t, source="rollup",
                                message=f"{instance.instance_name}: {status_}"))
        audit(db, user, "health_changed", "environment", env.id, {"from": before, "to": after, "source": source})
        emit(db, "health.changed", f"{env.name} is now {after}", message, environment=env,
             entity_type="environment", entity_id=env.id, recipients={env.owner or ""} | active_bookers(db, env.id),
             payload={"from": before, "to": after})


def active_bookers(db: Session, env_id: int) -> set[str]:
    t = now()
    return set(db.scalars(select(Booking.requested_by).where(
        Booking.environment_id == env_id, Booking.status.in_(["Approved", "Active"]),
        Booking.start_at <= t + timedelta(days=7), Booking.end_at > t)))


def run_checks(db: Session, env: Environment) -> list[dict[str, Any]]:
    results = []
    for inst in env.instances:
        if inst.health_check_url:
            s, ms, msg = probe(inst.health_check_url)
            record_health(db, env, s, instance=inst, message=msg, response_ms=ms)
            results.append({"instance_id": inst.id, "instance": inst.instance_name, "status": s, "response_ms": ms,
                            "message": msg})
    if env.health_check_url:
        s, ms, msg = probe(env.health_check_url)
        record_health(db, env, s, message=msg, response_ms=ms)
        results.append({"instance_id": None, "instance": None, "status": s, "response_ms": ms, "message": msg})
    return results


def availability(db: Session, env_id: int, start: datetime, end: datetime) -> dict[str, Any]:
    """Uptime %, outage count and mean time to restore from the environment-level series (HLT-05)."""
    rows = db.execute(select(HealthResult.checked_at, HealthResult.status)
                      .where(HealthResult.environment_id == env_id, HealthResult.instance_id.is_(None),
                             HealthResult.checked_at < end)
                      .order_by(HealthResult.checked_at)).all()
    # status in force at `start`
    series: list[tuple[datetime, str]] = []
    prior = None
    for at, st in rows:
        at = aware(at)
        if at <= start:
            prior = st
        else:
            series.append((at, st))
    if prior is not None:
        series.insert(0, (start, prior))
    up = down = known = 0.0
    outages: list[float] = []
    current_outage: datetime | None = None
    for idx, (at, st) in enumerate(series):
        nxt = series[idx + 1][0] if idx + 1 < len(series) else min(end, now())
        dur = max((nxt - at).total_seconds(), 0)
        if st != "Unknown":
            known += dur
        if st in ("Healthy", "Degraded"):
            up += dur
        if st == "Down":
            down += dur
            if current_outage is None:
                current_outage = at
        elif current_outage is not None:
            outages.append((at - current_outage).total_seconds())
            current_outage = None
    outage_count = len(outages) + (1 if current_outage else 0)
    return {
        "uptime_pct": round(100 * up / known, 2) if known else None,
        "downtime_hours": round(down / 3600, 2),
        "outage_count": outage_count,
        "mttr_hours": round(sum(outages) / len(outages) / 3600, 2) if outages else None,
        "observed_hours": round(known / 3600, 2),
    }


# --- Configuration (CFG-02, SEC-05) -----------------------------------------------------

SECRET_KEY_RE = re.compile(r"(PASS(?:WORD|WD)?(?![A-Z])|PWD|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIAL|ACCESS_KEY)", re.I)
SECRET_VALUE_RES = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "an AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "a JWT"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "a GitHub token"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"://[^/\s:@]+:[^/\s@]+@"), "a URL with an embedded password"),
]


def credential_warnings(key: str, value: str | None, is_secret: bool) -> list[str]:
    """SEC-05: flag values that look like credentials in a non-secret variable."""
    if is_secret:
        return []
    out = []
    if SECRET_KEY_RE.search(key) and value:
        out.append(f"{key} looks like a credential but is not marked secret")
    for rx, label in SECRET_VALUE_RES:
        if value and rx.search(value):
            out.append(f"The value of {key} looks like {label}; mark it secret and store a vault reference")
    return out


def effective_config(db: Session, env: Environment, instance_id: int | None = None) -> list[dict[str, Any]]:
    """Resolve global < environment < instance (CFG-02). Each item records its source and what it overrides."""
    layers: list[tuple[str, list[Variable]]] = [
        ("global", list(db.scalars(select(Variable).where(Variable.environment_id.is_(None),
                                                          Variable.instance_id.is_(None))))),
        ("environment", list(db.scalars(select(Variable).where(Variable.environment_id == env.id,
                                                               Variable.instance_id.is_(None))))),
    ]
    if instance_id is not None:
        layers.append(("instance", list(db.scalars(select(Variable).where(Variable.instance_id == instance_id)))))
    resolved: dict[str, dict[str, Any]] = {}
    for source, items in layers:
        for v in items:
            prev = resolved.get(v.key)
            resolved[v.key] = {"variable": v, "source": source,
                               "overrides": (prev["overrides"] + [prev["source"]]) if prev else []}
    return [resolved[k] for k in sorted(resolved)]


# --- Topology helpers -------------------------------------------------------------------


def system_names(db: Session) -> dict[str, str]:
    return dict(db.execute(select(System.id, System.name)).tuples().all())


def stale(d: Any) -> bool:
    if d is None:
        return True
    return (now().date() - d).days > settings.stale_after_days


def catalogue_integrations(db: Session) -> dict[str, Integration]:
    return {i.id: i for i in db.scalars(select(Integration).options(selectinload(Integration.hops)))}


@dataclass
class Footprint:
    systems: set[str] = field(default_factory=set)
    by_env: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))


def issue_sla(db: Session, severity: str, opened: datetime) -> datetime:
    hours = policy(db, "issue_sla_hours").get(severity, 72)
    return opened + timedelta(hours=hours)


def open_issue_counts(db: Session) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for env_id in db.scalars(select(Issue.environment_id).where(Issue.status.in_(["open", "in_progress"]))):
        counts[env_id] += 1
    return counts
