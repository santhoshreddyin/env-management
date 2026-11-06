"""Load and replace the current integration dataset."""

import json
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.auth import User
from app.flows.models import AuditLog, ComponentDetail, DatasetVersion, Hop, Integration, System
from app.flows.schemas import (
    ComponentDetailIn,
    Dataset,
    HopIn,
    IntegrationIn,
    SystemIn,
)

_SYSTEM_COLS = list(SystemIn.model_fields)
_INTEGRATION_COLS = list(IntegrationIn.model_fields)
_HOP_COLS = list(HopIn.model_fields)
_DETAIL_COLS = list(ComponentDetailIn.model_fields)


def _row(obj: Any, cols: list[str]) -> dict[str, Any]:
    return {c: getattr(obj, c) for c in cols}


def load_dataset(db: Session) -> Dataset:
    return Dataset(
        systems=[SystemIn.model_validate(_row(s, _SYSTEM_COLS)) for s in db.scalars(select(System).order_by(System.id))],
        integrations=[
            IntegrationIn.model_validate(_row(i, _INTEGRATION_COLS))
            for i in db.scalars(select(Integration).order_by(Integration.id))
        ],
        hops=[
            HopIn.model_validate(_row(h, _HOP_COLS))
            for h in db.scalars(select(Hop).order_by(Hop.integration_id, Hop.sequence))
        ],
        component_details=[
            ComponentDetailIn.model_validate(_row(d, _DETAIL_COLS))
            for d in db.scalars(select(ComponentDetail).order_by(ComponentDetail.system_id, ComponentDetail.id))
        ],
    )


def replace_dataset(db: Session, ds: Dataset) -> None:
    """Replace all current integration data with `ds`. Caller commits."""
    for model in (Hop, ComponentDetail, Integration, System):
        db.execute(delete(model))
    for model, items in (
        (System, ds.systems),
        (Integration, ds.integrations),
        (Hop, ds.hops),
        (ComponentDetail, ds.component_details),
    ):
        if items:
            db.execute(insert(model), [item.model_dump() for item in items])
    db.expire_all()


def record_audit(
    db: Session,
    user: User,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user=user.name,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=json.dumps(details, default=str) if details else None,
        )
    )


def commit_dataset(
    db: Session,
    ds: Dataset,
    *,
    user: User,
    source: str,
    summary: str,
    filename: str | None = None,
    audit_action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> DatasetVersion:
    """Replace the dataset, snapshot it as a new version and write the audit log, atomically."""
    replace_dataset(db, ds)
    counts = ds.counts()
    version = DatasetVersion(
        created_by=user.name,
        source=source,
        filename=filename,
        summary=summary,
        system_count=counts["systems"],
        integration_count=counts["integrations"],
        hop_count=counts["hops"],
        snapshot=ds.model_dump_json(),
    )
    db.add(version)
    db.flush()
    record_audit(
        db, user, audit_action, entity_type, entity_id,
        {"version_id": version.id, "summary": summary, **(details or {})},
    )
    db.commit()
    return version


def current_version_id(db: Session) -> int | None:
    return db.scalar(select(DatasetVersion.id).order_by(DatasetVersion.id.desc()).limit(1))
