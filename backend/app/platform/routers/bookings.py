"""Booking and scheduling (BKG-01..09), freeze/change calendar (DEP-07, CHG-04), ICS feed (INT-08)."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import BOOKER, ENV_MANAGER, User, check, require_viewer
from app.database import get_db
from app.models import Booking, CalendarEvent, Deployment, Environment, Issue, SystemInstance
from app.platform.common import audit, aware, bump, check_version, get_or_404, now, policy
from app.platform.notify import emit
from app.platform.routers.environments import get_env
from app.platform.services import (
    BOOKABLE,
    LIVE_BOOKING,
    find_conflicts,
    freeze_windows,
    promote_waitlist,
    refresh_bookings,
)

router = APIRouter(tags=["bookings"])

PRIORITIES = Literal["production_fix", "release", "project", "training"]
STATUSES = ["Requested", "Approved", "Active", "Completed", "Cancelled", "Rejected", "Waitlisted"]


class Recurrence(BaseModel):
    every_days: int = Field(7, ge=1, le=365)
    count: int = Field(2, ge=2, le=52)


class BookingIn(BaseModel):
    environment_id: int
    instance_ids: list[int] = []
    project: str = Field(min_length=1, max_length=200)
    team: str | None = None
    purpose: str | None = None
    start_at: datetime
    end_at: datetime
    priority: PRIORITIES = "project"
    approver: str | None = None
    recurrence: Recurrence | None = None
    waitlist: bool = Field(False, description="Join the waitlist instead of failing on a conflict")
    allow_conflict: bool = Field(False, description="Environment managers: book despite conflicts")
    test_data_ids: list[int] = []

    @model_validator(mode="after")
    def _range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at: the end must be after the start")
        return self


class BookingPatch(BaseModel):
    project: str | None = None
    team: str | None = None
    purpose: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    priority: PRIORITIES | None = None
    approver: str | None = None
    instance_ids: list[int] | None = None
    row_version: int | None = None


def _utc(dt: datetime) -> datetime:
    return aware(dt)


def booking_out(b: Booking) -> dict[str, Any]:
    return {
        "id": b.id, "environment_id": b.environment_id, "environment": b.environment.name if b.environment else None,
        "env_type": b.environment.env_type if b.environment else None,
        "instance_ids": [i.id for i in b.instances], "instances": [i.instance_name for i in b.instances],
        "scope": "partial" if b.instances else "whole", "project": b.project, "team": b.team, "purpose": b.purpose,
        "start_at": aware(b.start_at), "end_at": aware(b.end_at), "status": b.status, "priority": b.priority,
        "requested_by": b.requested_by, "approver": b.approver, "decided_by": b.decided_by,
        "decided_at": aware(b.decided_at), "decision_note": b.decision_note, "series_id": b.series_id,
        "escalated": b.escalated, "row_version": b.row_version, "created_at": aware(b.created_at),
        "duration_days": round((aware(b.end_at) - aware(b.start_at)).total_seconds() / 86400, 2),
    }


def _instances(db: Session, env: Environment, ids: list[int]) -> list[SystemInstance]:
    out = []
    for i in ids:
        inst = db.get(SystemInstance, i)
        if inst is None or (inst.environment_id != env.id and env not in inst.shared_with):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"instance_ids: {i} is not part of {env.name}")
        out.append(inst)
    return out


def _check_policy(db: Session, user: User, env: Environment, start: datetime, end: datetime) -> list[str]:
    warnings = []
    if env.status not in BOOKABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{env.name} is {env.status} and cannot be booked")
    max_days = policy(db, "max_booking_days")
    if max_days and (end - start) > timedelta(days=max_days):
        if not user.can(ENV_MANAGER, env):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"end_at: bookings are limited to {max_days} days; split it or ask an environment manager")
        warnings.append(f"Longer than the {max_days}-day limit (allowed for environment managers)")
    for f in freeze_windows(db, env.id, start, end):
        warnings.append(f"Overlaps {f.kind} '{f.title}' ({aware(f.start_at):%d %b} – {aware(f.end_at):%d %b})")
    if env.status == "Frozen":
        warnings.append(f"{env.name} is Frozen: no deployments")
    return warnings


def known_issues(db: Session, env_id: int) -> list[dict[str, Any]]:
    return [{"id": i.id, "title": i.title, "severity": i.severity, "workaround": i.workaround}
            for i in db.scalars(select(Issue).where(Issue.environment_id == env_id, Issue.known_issue.is_(True),
                                                    Issue.status.in_(["open", "in_progress"])))]


@router.get("/bookings")
def list_bookings(environment_id: int | None = None, project: str | None = None, team: str | None = None,
                  status_: str | None = Query(None, alias="status"), start: datetime | None = None,
                  end: datetime | None = None, mine: bool = False, user: User = Depends(require_viewer),
                  db: Session = Depends(get_db)):
    refresh_bookings(db)
    q = select(Booking).options(selectinload(Booking.instances), selectinload(Booking.environment)).order_by(Booking.start_at)
    if environment_id:
        q = q.where(Booking.environment_id == environment_id)
    if project:
        q = q.where(Booking.project == project)
    if team:
        q = q.where(Booking.team == team)
    if status_:
        q = q.where(Booking.status.in_(status_.split(",")))
    if start:
        q = q.where(Booking.end_at > start)
    if end:
        q = q.where(Booking.start_at < end)
    if mine:
        q = q.where(Booking.requested_by == user.name)
    return [booking_out(b) for b in db.scalars(q) if b.environment and b.environment.deleted_at is None
            and user.can_see(b.environment)]


class ConflictCheckIn(BaseModel):
    environment_id: int
    instance_ids: list[int] = []
    start_at: datetime
    end_at: datetime
    priority: PRIORITIES = "project"
    exclude_id: int | None = None


@router.post("/bookings/check")
def check_conflicts(payload: ConflictCheckIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """BKG-03: conflicts (including shared components), freeze warnings and known issues before booking."""
    env = get_env(db, payload.environment_id, user)
    _instances(db, env, payload.instance_ids)
    start, end = _utc(payload.start_at), _utc(payload.end_at)
    conflicts = find_conflicts(db, env.id, start, end, payload.instance_ids, payload.exclude_id, payload.priority)
    warnings = []
    try:
        warnings = _check_policy(db, user, env, start, end)
    except HTTPException as e:
        warnings = [str(e.detail)]
    return {"conflicts": conflicts, "warnings": warnings, "known_issues": known_issues(db, env.id),
            "requires_approval": env.env_type in policy(db, "booking_approval_types")}


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, payload.environment_id, user)
    check(user, BOOKER, env, "book environments")
    insts = _instances(db, env, payload.instance_ids)
    start, end = _utc(payload.start_at), _utc(payload.end_at)
    if end <= now():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end_at: the booking must end in the future")
    warnings = _check_policy(db, user, env, start, end)
    occurrences = [(start, end)]
    series_id = None
    if payload.recurrence:
        step = timedelta(days=payload.recurrence.every_days)
        occurrences = [(start + n * step, end + n * step) for n in range(payload.recurrence.count)]
        series_id = uuid.uuid4().hex[:12]
    needs_approval = env.env_type in policy(db, "booking_approval_types")
    created, all_conflicts = [], []
    for s, e in occurrences:
        conflicts = find_conflicts(db, env.id, s, e, payload.instance_ids, priority=payload.priority)
        st = "Requested" if needs_approval else "Approved"
        if conflicts:
            if payload.waitlist:
                st = "Waitlisted"
            elif not (payload.allow_conflict and user.can(ENV_MANAGER, env)):
                raise HTTPException(status.HTTP_409_CONFLICT, {
                    "message": f"{env.name} is already booked {s:%d %b}–{e:%d %b} "
                               f"({', '.join(sorted({c['project'] for c in conflicts}))}). "
                               f"Choose other dates, book specific components, or join the waitlist.",
                    "conflicts": [{**c, "start_at": str(c["start_at"]), "end_at": str(c["end_at"])} for c in conflicts]})
            all_conflicts += conflicts
        if st == "Approved" and s <= now():
            st = "Active"
        b = Booking(environment_id=env.id, project=payload.project, team=payload.team, purpose=payload.purpose,
                    start_at=s, end_at=e, status=st, priority=payload.priority, requested_by=user.name,
                    approver=payload.approver, series_id=series_id)
        if st in ("Approved", "Active"):
            b.decided_by, b.decided_at, b.decision_note = "policy", now(), "Auto-approved (no approval required)"
        b.instances = insts
        db.add(b)
        db.flush()
        created.append(b)
        if payload.test_data_ids:
            from app.models import TestDataSet

            for tid in payload.test_data_ids:
                ds = get_or_404(db, TestDataSet, tid, "Test data set")
                if ds.reserved_for_booking_id is None:
                    ds.reserved_for_booking_id, ds.reserved_by, ds.reserved_until = b.id, user.name, e
    audit(db, user, "booking_create", "booking", created[0].id,
          {"environment": env.name, "project": payload.project, "count": len(created), "status": created[0].status,
           "conflicts": len(all_conflicts)})
    recipients = {env.owner or "", env.delivery_manager or "", payload.approver or ""} if needs_approval else set()
    emit(db, "booking.created", f"{payload.project} booked {env.name} ({created[0].status})",
         f"{start:%d %b %Y} – {end:%d %b %Y}" + (f", {len(created)} occurrences" if len(created) > 1 else ""),
         environment=env, entity_type="booking", entity_id=created[0].id, recipients=recipients)
    if all_conflicts:
        emit(db, "booking.conflict", f"Booking conflict on {env.name}", f"{payload.project} overlaps "
             + ", ".join(sorted({c['project'] for c in all_conflicts})), environment=env, entity_type="booking",
             entity_id=created[0].id, recipients={env.owner or ""})
    db.commit()
    return {"bookings": [booking_out(b) for b in created], "warnings": warnings,
            "conflicts": all_conflicts, "known_issues": known_issues(db, env.id)}


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    b = get_or_404(db, Booking, booking_id, "Booking")
    get_env(db, b.environment_id, user)
    return booking_out(b) | {"conflicts": find_conflicts(db, b.environment_id, aware(b.start_at), aware(b.end_at),
                                                         [i.id for i in b.instances], b.id, b.priority)}


@router.patch("/bookings/{booking_id}")
def update_booking(booking_id: int, payload: BookingPatch, user: User = Depends(require_viewer),
                   db: Session = Depends(get_db)):
    b = get_or_404(db, Booking, booking_id, "Booking")
    env = get_env(db, b.environment_id, user)
    if b.requested_by != user.name:
        check(user, ENV_MANAGER, env, "change other people's bookings")
    check_version(b, payload.row_version)
    if b.status in ("Completed", "Cancelled", "Rejected"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A {b.status.lower()} booking cannot be changed")
    data = payload.model_dump(exclude_unset=True, exclude={"row_version", "instance_ids"})
    start = _utc(data.get("start_at", b.start_at))
    end = _utc(data.get("end_at", b.end_at))
    if end <= start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end_at: the end must be after the start")
    ids = payload.instance_ids if payload.instance_ids is not None else [i.id for i in b.instances]
    warnings = _check_policy(db, user, env, start, end)
    conflicts = find_conflicts(db, env.id, start, end, ids, exclude_id=b.id, priority=data.get("priority", b.priority))
    if conflicts and b.status != "Waitlisted":
        raise HTTPException(status.HTTP_409_CONFLICT, {"message": "The change conflicts with other bookings",
                                                       "conflicts": [{**c, "start_at": str(c["start_at"]),
                                                                      "end_at": str(c["end_at"])} for c in conflicts]})
    for k, v in data.items():
        setattr(b, k, _utc(v) if isinstance(v, datetime) else v)
    if payload.instance_ids is not None:
        b.instances = _instances(db, env, payload.instance_ids)
    bump(b)
    b.expiry_notified = False
    audit(db, user, "booking_update", "booking", b.id, {k: str(v) for k, v in data.items()})
    db.commit()
    return booking_out(b) | {"warnings": warnings}


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "cancel"]
    note: str | None = None
    apply_to_series: bool = False


@router.post("/bookings/{booking_id}/decision")
def decide(booking_id: int, payload: DecisionIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """BKG-04: approve or reject (env manager or the delegated approver); cancel (requester or manager)."""
    b = get_or_404(db, Booking, booking_id, "Booking")
    env = get_env(db, b.environment_id, user)
    targets = [b]
    if payload.apply_to_series and b.series_id:
        targets = list(db.scalars(select(Booking).where(Booking.series_id == b.series_id,
                                                        Booking.status.in_(LIVE_BOOKING + ["Waitlisted"]))))
    for t in targets:
        if payload.decision == "cancel":
            if t.requested_by != user.name:
                check(user, ENV_MANAGER, env, "cancel other people's bookings")
            if t.status not in LIVE_BOOKING + ["Waitlisted"]:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Booking is already {t.status}")
            t.status = "Cancelled"
        else:
            if not (user.can(ENV_MANAGER, env) or (t.approver and t.approver == user.name)):
                check(user, ENV_MANAGER, env, "approve bookings")
            if t.status not in ("Requested", "Waitlisted"):
                raise HTTPException(status.HTTP_409_CONFLICT, f"Only requested bookings can be decided (this one is {t.status})")
            if payload.decision == "approve":
                conflicts = [c for c in find_conflicts(db, t.environment_id, aware(t.start_at), aware(t.end_at),
                                                       [i.id for i in t.instances], t.id, t.priority)
                             if c["status"] in ("Approved", "Active")]
                if conflicts:
                    raise HTTPException(status.HTTP_409_CONFLICT,
                                        f"Cannot approve: overlaps approved booking(s) "
                                        f"{', '.join(c['project'] for c in conflicts)}")
                t.status = "Active" if aware(t.start_at) <= now() else "Approved"
            else:
                t.status = "Rejected"
        t.decided_by, t.decided_at, t.decision_note = user.name, now(), payload.note
        bump(t)
        audit(db, user, f"booking_{payload.decision}", "booking", t.id, {"note": payload.note})
        emit(db, "booking.cancelled" if payload.decision == "cancel" else "booking.decided",
             f"Booking {t.project} on {env.name} {t.status.lower()}", payload.note, environment=env,
             entity_type="booking", entity_id=t.id, recipients={t.requested_by})
    if payload.decision in ("cancel", "reject"):
        db.flush()
        promote_waitlist(db, env.id)
    db.commit()
    return [booking_out(t) for t in targets]


@router.get("/approvals/bookings")
def pending_booking_approvals(user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    refresh_bookings(db)
    rows = db.scalars(select(Booking).options(selectinload(Booking.environment), selectinload(Booking.instances))
                      .where(Booking.status == "Requested").order_by(Booking.created_at))
    return [booking_out(b) for b in rows if user.can(ENV_MANAGER, b.environment) or b.approver == user.name]


# --- Calendar events (DEP-07, CHG-04) ---------------------------------------------------


class EventIn(BaseModel):
    environment_id: int | None = None
    kind: Literal["freeze", "blackout", "planned_change", "release", "outage", "refresh", "maintenance"]
    title: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime
    enforce: bool = False
    external_ref: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at: the end must be after the start")
        return self


def event_out(e: CalendarEvent, envs: dict[int, str]) -> dict[str, Any]:
    return {"id": e.id, "environment_id": e.environment_id,
            "environment": envs.get(e.environment_id) if e.environment_id else "All environments",
            "kind": e.kind, "title": e.title, "start_at": aware(e.start_at), "end_at": aware(e.end_at),
            "enforce": e.enforce, "external_ref": e.external_ref, "notes": e.notes, "created_by": e.created_by}


@router.get("/calendar/events")
def list_events(environment_id: int | None = None, start: datetime | None = None, end: datetime | None = None,
                kind: str | None = None, _: User = Depends(require_viewer), db: Session = Depends(get_db)):
    q = select(CalendarEvent).order_by(CalendarEvent.start_at)
    if environment_id:
        q = q.where(or_(CalendarEvent.environment_id == environment_id, CalendarEvent.environment_id.is_(None)))
    if start:
        q = q.where(CalendarEvent.end_at > start)
    if end:
        q = q.where(CalendarEvent.start_at < end)
    if kind:
        q = q.where(CalendarEvent.kind.in_(kind.split(",")))
    envs = {e.id: e.name for e in db.scalars(select(Environment))}
    return [event_out(e, envs) for e in db.scalars(q)]


@router.post("/calendar/events", status_code=status.HTTP_201_CREATED)
def create_event(payload: EventIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, payload.environment_id, user) if payload.environment_id else None
    check(user, ENV_MANAGER, env, "add freezes and planned changes")
    e = CalendarEvent(**payload.model_dump() | {"start_at": _utc(payload.start_at), "end_at": _utc(payload.end_at)},
                      created_by=user.name)
    db.add(e)
    db.flush()
    audit(db, user, "create", "calendar_event", e.id, payload.model_dump(mode="json"))
    clashing = []
    if payload.kind in ("freeze", "blackout", "outage", "maintenance"):
        q = select(Booking).options(selectinload(Booking.environment)).where(
            Booking.status.in_(LIVE_BOOKING), Booking.start_at < e.end_at, Booking.end_at > e.start_at)
        if env:
            q = q.where(Booking.environment_id == env.id)
        for b in db.scalars(q):
            clashing.append(booking_out(b))
            emit(db, "booking.conflict", f"{payload.kind.capitalize()} '{payload.title}' overlaps your booking on "
                 f"{b.environment.name}", environment=b.environment, entity_type="booking", entity_id=b.id,
                 recipients={b.requested_by})
    db.commit()
    return event_out(e, {env.id: env.name} if env else {}) | {"affected_bookings": clashing}


@router.delete("/calendar/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    e = get_or_404(db, CalendarEvent, event_id, "Event")
    check(user, ENV_MANAGER, db.get(Environment, e.environment_id) if e.environment_id else None, "remove events")
    audit(db, user, "delete", "calendar_event", e.id, {"title": e.title})
    db.delete(e)
    db.commit()


@router.get("/calendar")
def change_calendar(start: datetime, end: datetime, environment_id: int | None = None,
                    user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """CHG-04: planned changes, releases, outages, refreshes, bookings and deployments in one view."""
    refresh_bookings(db)
    start, end = _utc(start), _utc(end)
    envs = {e.id: e for e in db.scalars(select(Environment).where(Environment.deleted_at.is_(None))) if user.can_see(e)}
    names = {k: v.name for k, v in envs.items()}
    items: list[dict[str, Any]] = []
    for e in list_events(environment_id, start, end, None, user, db):
        if e["environment_id"] is None or e["environment_id"] in envs:
            items.append({"type": "event", **e})
    for b in list_bookings(environment_id, None, None, ",".join(LIVE_BOOKING + ["Completed"]), start, end, False, user, db):
        items.append({"type": "booking", "id": b["id"], "kind": "booking", "environment_id": b["environment_id"],
                      "environment": b["environment"], "title": f"{b['project']} ({b['status']})",
                      "start_at": b["start_at"], "end_at": b["end_at"], "status": b["status"]})
    dq = select(Deployment).where(Deployment.deployed_at >= start, Deployment.deployed_at < end)
    if environment_id:
        dq = dq.where(Deployment.environment_id == environment_id)
    for d in db.scalars(dq):
        if d.environment_id in envs:
            items.append({"type": "deployment", "id": d.id, "kind": "deployment", "environment_id": d.environment_id,
                          "environment": names.get(d.environment_id), "title": f"{d.system_id} {d.version} ({d.outcome})",
                          "start_at": aware(d.deployed_at), "end_at": aware(d.deployed_at)})
    iq = select(Issue).where(Issue.kind == "incident", Issue.opened_at < end,
                             or_(Issue.resolved_at.is_(None), Issue.resolved_at > start))
    if environment_id:
        iq = iq.where(Issue.environment_id == environment_id)
    for i in db.scalars(iq):
        if i.environment_id in envs:
            items.append({"type": "incident", "id": i.id, "kind": "incident", "environment_id": i.environment_id,
                          "environment": names.get(i.environment_id), "title": f"{i.title} ({i.severity})",
                          "start_at": aware(i.opened_at), "end_at": aware(i.resolved_at) or now()})
    items.sort(key=lambda x: x["start_at"])
    return items


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@router.get("/calendar.ics", response_class=Response, tags=["integrations"])
def ics_feed(environment_id: int | None = None, days: int = 120, user: User = Depends(require_viewer),
             db: Session = Depends(get_db)):
    """INT-08: subscribe from Outlook or Google Calendar to bookings and freezes."""
    t = now()
    items = change_calendar(t - timedelta(days=30), t + timedelta(days=days), environment_id, user, db)
    fmt = "%Y%m%dT%H%M%SZ"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Env Management//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Environment calendar"]
    for it in items:
        if it["type"] not in ("event", "booking"):
            continue
        lines += ["BEGIN:VEVENT", f"UID:{it['type']}-{it['id']}@env-management", f"DTSTAMP:{t.strftime(fmt)}",
                  f"DTSTART:{aware(it['start_at']).astimezone(timezone.utc).strftime(fmt)}",
                  f"DTEND:{aware(it['end_at']).astimezone(timezone.utc).strftime(fmt)}",
                  f"SUMMARY:{_ics_escape(f'[{it['environment']}] {it['title']}')}",
                  f"CATEGORIES:{it['kind']}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="environments.ics"'})
