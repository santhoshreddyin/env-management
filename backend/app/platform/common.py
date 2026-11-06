"""Shared helpers: time, audit (hash-chained), concurrency, lookup, tabular export, settings."""

import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from typing import Any, Iterable

from fastapi import HTTPException, Response, status
from openpyxl import Workbook
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.auth import User
from app.flows.models import AuditLog
from app.models import AppSetting

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything is stored in UTC (NFR-12)."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- Audit (GOV-02) ---------------------------------------------------------------------


def audit(db: Session, user: User | str, action: str, entity_type: str | None = None,
          entity_id: Any = None, details: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(
        user=user if isinstance(user, str) else user.name, action=action, entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        details=json.dumps(details, default=str) if details else None,
    ))


def audit_hash(prev: str | None, row: AuditLog) -> str:
    at = aware(row.at)
    content = "|".join([prev or "", at.astimezone(timezone.utc).isoformat() if at else "", row.user or "", row.action or "",
                        row.entity_type or "", row.entity_id or "", row.details or ""])
    return hashlib.sha256(content.encode()).hexdigest()


@event.listens_for(Session, "before_flush")
def _chain_audit(session: Session, _ctx, _instances) -> None:
    new = [o for o in session.new if isinstance(o, AuditLog)]
    if not new:
        return
    with session.no_autoflush:
        prev = session.scalar(select(AuditLog.hash).where(AuditLog.hash.is_not(None))
                              .order_by(AuditLog.id.desc()).limit(1))
    for row in new:
        if row.at is None:
            row.at = now()
        row.prev_hash = prev
        row.hash = audit_hash(prev, row)
        prev = row.hash


def verify_audit_chain(db: Session) -> dict[str, Any]:
    prev = None
    checked = 0
    for row in db.scalars(select(AuditLog).where(AuditLog.hash.is_not(None)).order_by(AuditLog.id)):
        checked += 1
        if row.prev_hash != prev or audit_hash(prev, row) != row.hash:
            return {"valid": False, "checked": checked, "broken_at_id": row.id}
        prev = row.hash
    return {"valid": True, "checked": checked, "broken_at_id": None}


# --- Concurrency (NFR-09) ---------------------------------------------------------------


def check_version(obj: Any, expected: int | None) -> None:
    if expected is not None and expected != obj.row_version:
        who = getattr(obj, "updated_by", None)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This record was changed by {who or 'someone else'} after you opened it "
            f"(your version {expected}, current {obj.row_version}). Reload and reapply your change.",
        )


def bump(obj: Any, user: User | None = None) -> None:
    obj.row_version = (obj.row_version or 0) + 1
    if user is not None and hasattr(obj, "updated_by"):
        obj.updated_by = user.name


def get_or_404(db: Session, model: Any, id_: Any, label: str | None = None) -> Any:
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label or model.__name__} {id_} not found")
    return obj


def apply(obj: Any, data: dict[str, Any], skip: Iterable[str] = ("row_version",)) -> dict[str, Any]:
    """Set fields on obj, returning {field: [old, new]} for those that changed."""
    changes = {}
    for k, v in data.items():
        if k in skip:
            continue
        old = getattr(obj, k)
        if old != v:
            changes[k] = [old, v]
            setattr(obj, k, v)
    return changes


# --- Settings (GOV-04/08) ---------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, Any] = {
    "env_types": ["DEV", "SIT", "UAT", "PreProd", "Perf", "Training", "Sandbox"],
    "tiers": ["Tier 1", "Tier 2", "Tier 3"],
    "platforms": ["AWS", "Azure", "GCP", "On-premises", "Kubernetes", "Mainframe"],
    "system_categories": ["application", "middleware", "database", "api", "mainframe", "third_party"],
    "issue_categories": ["configuration", "data", "infrastructure", "code defect", "integration", "access", "capacity",
                         "third party", "unknown"],
    # ENV-06: custom attributes [{key, label, type: text|number|date|select, options, required_for: [types]}]
    "custom_attributes": [],
    # ENV-06 / GOV-04: mandatory fields per environment type ("*" = all)
    "mandatory_fields": {"*": [], "UAT": ["owner", "delivery_manager", "support_group"],
                         "PreProd": ["owner", "delivery_manager", "support_group", "cost_centre"]},
    # GOV-03/04 policies
    "policies": {
        "max_booking_days": 60,
        "booking_approval_types": ["UAT", "PreProd", "Perf"],  # bookings on these need approval
        "protected_types": ["PreProd"],  # config changes here need env_manager approval
        "booking_escalation_hours": 48,  # escalate requests not decided within this time
        "environment_request_sla_days": 10,
        "issue_sla_hours": {"critical": 4, "high": 24, "medium": 72, "low": 240},
        "booking_expiry_notice_hours": 48,
    },
    "decommission_checklist": [
        "Notify bookers and dependent teams",
        "Confirm no active or future bookings",
        "Remove or archive test data",
        "Revoke access and credentials",
        "Update CMDB record",
        "Release infrastructure and licences",
    ],
    "notification_templates": {
        "booking.created": "Booking {project} on {environment} from {start} to {end} ({status})",
        "booking.decided": "Booking {project} on {environment} was {status}",
        "health.changed": "{environment} is now {status}",
    },
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    if row is not None:
        value = row.value
        default = DEFAULT_SETTINGS.get(key)
        if isinstance(default, dict) and isinstance(value, dict):
            return {**default, **value}
        return value
    return DEFAULT_SETTINGS.get(key)


def policy(db: Session, key: str) -> Any:
    return get_setting(db, "policies").get(key, DEFAULT_SETTINGS["policies"].get(key))


# --- Tabular export (RPT-08, NFR-10) ----------------------------------------------------


def _cell(v: Any) -> Any:
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str)
    if isinstance(v, datetime):
        return aware(v).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def tabular_response(rows: list[dict[str, Any]], fmt: str, name: str, columns: list[str] | None = None) -> Response:
    columns = columns or (list(rows[0].keys()) if rows else [])
    stamp = now().strftime("%Y%m%d-%H%M%S")
    if fmt == "json":
        return Response(json.dumps(rows, default=str, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}-{stamp}.json"'})
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = name[:31]
        ws.append(columns)
        for r in rows:
            ws.append([_cell(r.get(c)) for c in columns])
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="{name}-{stamp}.xlsx"'})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([_cell(r.get(c)) for c in columns])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}-{stamp}.csv"'})


def parse_table(content: bytes, fmt: str) -> list[dict[str, Any]]:
    """Parse CSV / XLSX / JSON rows (first sheet / list of objects)."""
    if fmt == "json":
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict):
            data = data.get("items") or data.get("rows") or data.get("environments") or []
        if not isinstance(data, list):
            raise ValueError("Expected a JSON list of objects")
        return data
    if fmt == "xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(h).strip() if h is not None else "" for h in rows[0]]
        return [{header[i]: v for i, v in enumerate(r) if i < len(header) and header[i]}
                for r in rows[1:] if any(v not in (None, "") for v in r)]
    text = content.decode("utf-8-sig")
    return [dict(r) for r in csv.DictReader(io.StringIO(text))]


def fmt_of(filename: str | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    name = (filename or "").lower()
    for ext, fmt in ((".xlsx", "xlsx"), (".json", "json"), (".yaml", "yaml"), (".yml", "yaml"), (".env", "env"),
                     (".csv", "csv")):
        if name.endswith(ext):
            return fmt
    return "csv"
