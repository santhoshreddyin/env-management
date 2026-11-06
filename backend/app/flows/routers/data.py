"""Data management: Excel import with validation, export, template, version history,
rollback and audit log (FR-11 to FR-13)."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import User, require_maintainer, require_viewer
from app.config import settings
from app.database import get_db
from app.flows.excel import build_workbook, parse_workbook
from app.flows.models import AuditLog, DatasetVersion
from app.flows.repository import commit_dataset, current_version_id, load_dataset, record_audit
from app.flows.schemas import AuditOut, Dataset, ImportReport, VersionOut
from app.flows.validation import has_errors, validate_dataset

router = APIRouter(tags=["flow data"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@router.post("/import", response_model=ImportReport)
async def import_workbook(
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Validate only; do not import"),
    user: User = Depends(require_maintainer),
    db: Session = Depends(get_db),
):
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")

    parsed = parse_workbook(content)
    issues = parsed.issues
    if not has_errors(issues):
        issues += validate_dataset(parsed.dataset, parsed.row_of)
    sheet_order = ["(workbook)", "Systems", "Integrations", "Hops", "ComponentDetails"]
    issues.sort(key=lambda i: (i.severity != "error", sheet_order.index(i.sheet) if i.sheet in sheet_order else 99,
                               i.row or 0))
    valid = not has_errors(issues)
    counts = parsed.dataset.counts()
    report = ImportReport(
        filename=file.filename, dry_run=dry_run, valid=valid, imported=False, counts=counts,
        error_count=sum(i.severity == "error" for i in issues),
        warning_count=sum(i.severity == "warning" for i in issues),
        issues=issues,
    )
    if dry_run:
        return report

    if not valid:
        record_audit(db, user, "import_rejected", "dataset", None,
                     {"filename": file.filename, "errors": report.error_count})
        db.commit()
        return report

    version = commit_dataset(
        db, parsed.dataset, user=user, source="import", filename=file.filename,
        summary=f"Imported {file.filename}: {counts['systems']} systems, "
                f"{counts['integrations']} integrations, {counts['hops']} hops",
        audit_action="import", entity_type="dataset",
        details={"filename": file.filename, "warnings": report.warning_count, **counts},
    )
    report.imported = True
    report.version_id = version.id
    return report


@router.get("/export", dependencies=[Depends(require_viewer)])
def export_dataset(format: str = Query("xlsx", pattern="^(xlsx|json)$"), db: Session = Depends(get_db)):
    ds = load_dataset(db)
    name = f"integration-flows-{_stamp()}"
    if format == "json":
        body = {"version_id": current_version_id(db), "exported_at": datetime.now(timezone.utc).isoformat(),
                **ds.model_dump(mode="json")}
        return Response(json.dumps(body, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    return Response(build_workbook(ds), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/template", dependencies=[Depends(require_viewer)])
def download_template():
    return Response(build_workbook(Dataset()), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="integration-flows-template.xlsx"'})


@router.get("/imports", response_model=list[VersionOut], dependencies=[Depends(require_viewer)])
def list_versions(db: Session = Depends(get_db)):
    versions = db.scalars(select(DatasetVersion).order_by(DatasetVersion.id.desc())).all()
    current = versions[0].id if versions else None
    return [VersionOut.model_validate(v).model_copy(update={"is_current": v.id == current}) for v in versions]


@router.post("/imports/{version_id}/rollback", response_model=VersionOut)
def rollback(version_id: int, user: User = Depends(require_maintainer), db: Session = Depends(get_db)):
    target = db.get(DatasetVersion, version_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    ds = Dataset.model_validate_json(target.snapshot)
    issues = validate_dataset(ds)
    if has_errors(issues):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Snapshot no longer passes validation", "issues": [i.model_dump() for i in issues]},
        )
    version = commit_dataset(
        db, ds, user=user, source="rollback", filename=target.filename,
        summary=f"Rolled back to version {target.id}",
        audit_action="rollback", entity_type="dataset", details={"restored_version": target.id},
    )
    return VersionOut.model_validate(version).model_copy(update={"is_current": True})


@router.get("/audit", response_model=list[AuditOut], dependencies=[Depends(require_maintainer)])
def audit_log(limit: int = Query(200, ge=1, le=2000), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return [
        AuditOut(id=r.id, at=r.at, user=r.user, action=r.action, entity_type=r.entity_type,
                 entity_id=r.entity_id, details=json.loads(r.details) if r.details else None)
        for r in rows
    ]
