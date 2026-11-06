"""Background jobs: booking auto-release/escalation/expiry (BKG-05/09), scheduled health checks (HLT-02),
issue SLA breach (CHG-06) and secret rotation alerts (SEC-04)."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Environment, Issue, Notification, Variable
from app.platform.common import aware, now
from app.platform.notify import emit
from app.platform.services import refresh_bookings, run_checks

log = logging.getLogger("envmgmt.scheduler")


def tick() -> dict[str, int]:
    out = {"bookings": 0, "checks": 0, "sla": 0, "rotation": 0}
    with SessionLocal() as db:
        out["bookings"] = refresh_bookings(db)
        for env in db.scalars(select(Environment).where(Environment.deleted_at.is_(None),
                                                        Environment.status != "Retired")):
            if env.health_check_url or any(i.health_check_url for i in env.instances):
                run_checks(db, env)
                out["checks"] += 1
        t = now()
        for i in db.scalars(select(Issue).where(Issue.status.in_(["open", "in_progress"]), Issue.sla_notified.is_(False))):
            if i.sla_due_at and aware(i.sla_due_at) < t:
                i.sla_notified = True
                emit(db, "issue.sla_breached", f"SLA breached: {i.title}", f"Severity {i.severity}",
                     environment=db.get(Environment, i.environment_id), entity_type="issue", entity_id=i.id,
                     recipients={i.owner or "", i.created_by or ""})
                out["sla"] += 1
        for v in db.scalars(select(Variable).where(Variable.is_secret.is_(True), Variable.rotation_due_at.is_not(None))):
            due = aware(v.rotation_due_at)
            already = db.scalar(select(Notification.id).where(
                Notification.event == "secret.rotation_due", Notification.entity_id == str(v.id),
                Notification.at > t - timedelta(days=7)).limit(1))
            if due < t and not already:
                emit(db, "secret.rotation_due", f"Secret {v.key} is overdue for rotation", f"Due {due:%d %b %Y}",
                     environment=db.get(Environment, v.environment_id) if v.environment_id else None,
                     entity_type="variable", entity_id=v.id, recipients={v.rotation_owner or ""})
                out["rotation"] += 1
        db.commit()
    return out


async def run_forever() -> None:
    while True:
        try:
            result = await asyncio.to_thread(tick)
            log.info("scheduler tick %s", result)
        except Exception:  # pragma: no cover
            log.exception("scheduler tick failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)
