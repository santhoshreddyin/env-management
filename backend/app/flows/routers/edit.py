"""In-app editing of systems and integrations (FR-14).

Every edit is validated against the whole dataset, stored as a new version (so it can
be rolled back) and written to the audit log.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import User, require_maintainer
from app.database import get_db
from app.flows.repository import commit_dataset, load_dataset
from app.flows.schemas import (
    ComponentDetailIn,
    Dataset,
    HopIn,
    IntegrationEdit,
    IntegrationIn,
    SystemEdit,
    SystemIn,
    ValidationIssue,
)
from app.flows.validation import has_errors, validate_dataset

router = APIRouter(tags=["flow editing"])


def _save(db: Session, ds: Dataset, user: User, action: str, entity_type: str, entity_id: str) -> list[ValidationIssue]:
    issues = validate_dataset(ds)
    if has_errors(issues):
        errors = [i.model_dump() for i in issues if i.severity == "error"]
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": f"Change rejected: {errors[0]['message']}", "issues": errors},
        )
    commit_dataset(
        db, ds, user=user, source="edit", summary=f"{action.replace('_', ' ').capitalize()} '{entity_id}'",
        audit_action=action, entity_type=entity_type, entity_id=entity_id,
    )
    return [i for i in issues if i.severity == "warning"]


def _find(items: list, id_: str, label: str) -> int:
    for i, item in enumerate(items):
        if item.id == id_:
            return i
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} '{id_}' not found")


def _check_path_id(path_id: str, body_id: str) -> None:
    if path_id != body_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Changing the id is not supported")


# ---- Systems ---------------------------------------------------------------------------


def _apply_system(ds: Dataset, payload: SystemEdit) -> None:
    ds.component_details = [d for d in ds.component_details if d.system_id != payload.id] + [
        ComponentDetailIn(system_id=payload.id, **d.model_dump()) for d in payload.component_details
    ]


@router.post("/systems", status_code=status.HTTP_201_CREATED)
def create_system(payload: SystemEdit, user: User = Depends(require_maintainer), db: Session = Depends(get_db)):
    ds = load_dataset(db)
    if any(s.id == payload.id for s in ds.systems):
        raise HTTPException(status.HTTP_409_CONFLICT, f"System '{payload.id}' already exists")
    ds.systems.append(SystemIn(**payload.model_dump(exclude={"component_details"})))
    _apply_system(ds, payload)
    warnings = _save(db, ds, user, "create_system", "system", payload.id)
    return {"id": payload.id, "warnings": warnings}


@router.put("/systems/{system_id}")
def update_system(system_id: str, payload: SystemEdit, user: User = Depends(require_maintainer),
                  db: Session = Depends(get_db)):
    _check_path_id(system_id, payload.id)
    ds = load_dataset(db)
    ds.systems[_find(ds.systems, system_id, "System")] = SystemIn(**payload.model_dump(exclude={"component_details"}))
    _apply_system(ds, payload)
    warnings = _save(db, ds, user, "update_system", "system", system_id)
    return {"id": system_id, "warnings": warnings}


@router.delete("/systems/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system(system_id: str, user: User = Depends(require_maintainer), db: Session = Depends(get_db)):
    ds = load_dataset(db)
    ds.systems.pop(_find(ds.systems, system_id, "System"))
    ds.component_details = [d for d in ds.component_details if d.system_id != system_id]
    _save(db, ds, user, "delete_system", "system", system_id)


# ---- Integrations ----------------------------------------------------------------------


def _apply_integration(ds: Dataset, payload: IntegrationEdit) -> None:
    ds.hops = [h for h in ds.hops if h.integration_id != payload.id] + [
        HopIn(integration_id=payload.id, **h.model_dump()) for h in sorted(payload.hops, key=lambda h: h.sequence)
    ]


@router.post("/integrations", status_code=status.HTTP_201_CREATED)
def create_integration(payload: IntegrationEdit, user: User = Depends(require_maintainer),
                       db: Session = Depends(get_db)):
    ds = load_dataset(db)
    if any(i.id == payload.id for i in ds.integrations):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Integration '{payload.id}' already exists")
    ds.integrations.append(IntegrationIn(**payload.model_dump(exclude={"hops"})))
    _apply_integration(ds, payload)
    warnings = _save(db, ds, user, "create_integration", "integration", payload.id)
    return {"id": payload.id, "warnings": warnings}


@router.put("/integrations/{integration_id}")
def update_integration(integration_id: str, payload: IntegrationEdit, user: User = Depends(require_maintainer),
                       db: Session = Depends(get_db)):
    _check_path_id(integration_id, payload.id)
    ds = load_dataset(db)
    ds.integrations[_find(ds.integrations, integration_id, "Integration")] = IntegrationIn(
        **payload.model_dump(exclude={"hops"})
    )
    _apply_integration(ds, payload)
    warnings = _save(db, ds, user, "update_integration", "integration", integration_id)
    return {"id": integration_id, "warnings": warnings}


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(integration_id: str, user: User = Depends(require_maintainer), db: Session = Depends(get_db)):
    ds = load_dataset(db)
    ds.integrations.pop(_find(ds.integrations, integration_id, "Integration"))
    ds.hops = [h for h in ds.hops if h.integration_id != integration_id]
    _save(db, ds, user, "delete_integration", "integration", integration_id)
