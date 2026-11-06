"""Notifications, subscriptions, e-mail and outbound webhooks (BKG-09, HLT-06, INT-06, INT-07).

`emit()` writes in-app notifications in the caller's transaction and queues external
deliveries (webhooks, e-mail), which are sent by a background thread only after the
transaction commits.
"""

import fnmatch
import hashlib
import hmac
import json
import logging
import queue
import smtplib
import threading
from email.message import EmailMessage
from typing import Any, Callable

import httpx
from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, Subscription, Webhook
from app.platform.common import now

log = logging.getLogger("envmgmt.notify")

EVENTS = [
    "environment.created", "environment.updated", "environment.status_changed", "environment.deleted",
    "environment.requested",
    "booking.created", "booking.decided", "booking.cancelled", "booking.conflict", "booking.expiring",
    "booking.escalated", "booking.released",
    "deployment.recorded", "health.changed", "issue.created", "issue.updated", "issue.sla_breached",
    "config.changed", "approval.requested", "approval.decided", "secret.rotation_due",
]


def _matches(patterns: list[str] | None, ev: str) -> bool:
    return any(fnmatch.fnmatch(ev, p) for p in (patterns or ["*"]))


def emit(db: Session, ev: str, title: str, body: str | None = None, *, environment: Any = None,
         entity_type: str | None = None, entity_id: Any = None, recipients: set[str] | None = None,
         payload: dict[str, Any] | None = None) -> None:
    env_id = getattr(environment, "id", None)
    targets = {r for r in (recipients or set()) if r}
    emails: set[str] = set()
    subs = db.scalars(select(Subscription).where(
        or_(Subscription.environment_id.is_(None), Subscription.environment_id == env_id))).all()
    for s in subs:
        if _matches(s.events, ev):
            if s.channel == "email" and s.email:
                emails.add(s.email)
            else:
                targets.add(s.user)
    for r in targets:
        db.add(Notification(recipient=r, event=ev, title=title, body=body, entity_type=entity_type,
                            entity_id=None if entity_id is None else str(entity_id)))

    message = {
        "event": ev, "title": title, "body": body, "at": now().isoformat(),
        "environment": getattr(environment, "name", None), "environment_id": env_id,
        "entity_type": entity_type, "entity_id": entity_id, "data": payload or {},
    }
    outbox = db.info.setdefault("outbox", [])
    for hook in db.scalars(select(Webhook).where(Webhook.active.is_(True))).all():
        if _matches(hook.events, ev):
            outbox.append(("webhook", {"id": hook.id, "url": hook.url, "kind": hook.kind, "secret": hook.secret},
                           message))
    for e in emails:
        outbox.append(("email", {"to": e}, message))


def webhook_body(kind: str, message: dict[str, Any]) -> dict[str, Any]:
    text = message["title"] + (f"\n{message['body']}" if message.get("body") else "")
    if kind == "slack":
        return {"text": text}
    if kind == "teams":
        return {"@type": "MessageCard", "@context": "https://schema.org/extensions", "summary": message["title"],
                "title": message["title"], "text": message.get("body") or message["title"]}
    return message


def deliver_webhook(target: dict[str, Any], message: dict[str, Any]) -> str:
    body = json.dumps(webhook_body(target["kind"], message), default=str).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "env-management-webhooks"}
    if target.get("secret"):
        headers["X-Signature-SHA256"] = hmac.new(target["secret"].encode(), body, hashlib.sha256).hexdigest()
    try:
        r = httpx.post(target["url"], content=body, headers=headers, timeout=5.0)
        return f"{r.status_code}"
    except httpx.HTTPError as e:
        return f"error: {e.__class__.__name__}"


def deliver_email(target: dict[str, Any], message: dict[str, Any]) -> str:
    if not settings.smtp_host:
        return "skipped: SMTP not configured"
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = target["to"]
    msg["Subject"] = f"[Env Management] {message['title']}"
    msg.set_content(message.get("body") or message["title"])
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return "sent"
    except Exception as e:  # pragma: no cover - network
        return f"error: {e.__class__.__name__}"


# Replaceable for tests.
transport: dict[str, Callable[[dict[str, Any], dict[str, Any]], str]] = {
    "webhook": deliver_webhook,
    "email": deliver_email,
}
_queue: "queue.Queue[tuple[str, dict, dict]]" = queue.Queue()
_worker: threading.Thread | None = None


def _run() -> None:
    while True:
        channel, target, message = _queue.get()
        try:
            result = transport[channel](target, message)
            log.info("delivered %s %s -> %s", channel, message["event"], result)
        except Exception:  # pragma: no cover
            log.exception("delivery failed")
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_run, name="notify-worker", daemon=True)
        _worker.start()


@event.listens_for(Session, "after_commit")
def _flush_outbox(session: Session) -> None:
    items = session.info.pop("outbox", [])
    if not items or not settings.webhooks_enabled:
        return
    _ensure_worker()
    for item in items:
        _queue.put(item)


@event.listens_for(Session, "after_rollback")
def _drop_outbox(session: Session) -> None:
    session.info.pop("outbox", None)


def drain(timeout: float = 5.0) -> None:
    """Wait for queued deliveries (tests)."""
    if _worker is not None:
        _queue.join()
