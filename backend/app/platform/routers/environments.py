"""Environment inventory and lifecycle (ENV-01..12), bulk import/export (ENV-10, GOV-05)."""

from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import BOOKER, CONTRIBUTOR, ENV_MANAGER, User, check, require_admin, require_viewer
from app.database import get_db
from app.models import (
    Booking,
    BulkOperation,
    Environment,
    EnvironmentIntegration,
    SystemInstance,
    Variable,
)
from app.platform.common import (
    apply,
    audit,
    aware,
    bump,
    check_version,
    fmt_of,
    get_setting,
    now,
    parse_table,
    policy,
    tabular_response,
)
from app.platform.notify import emit
from app.platform.services import LIFECYCLE, TRANSITIONS, effective_health, open_issue_counts, transition

router = APIRouter(prefix="/environments", tags=["environments"])

EDITABLE = [
    "name", "description", "env_type", "tier", "purpose", "owner", "delivery_manager", "technical_contact",
    "cost_centre", "programme", "support_group", "platform", "hosting_location", "region", "network_zone", "urls",
    "parent_id", "family", "shared_infrastructure", "tags", "attributes", "run_cost", "chargeback_model",
    "licence_notes", "retirement_date", "health_check_url", "sensitive_data", "production_derived_data",
    "data_controls", "cmdb_id",
]
EXPORT_COLUMNS = ["id", "name", "description", "env_type", "tier", "status", "purpose", "owner", "delivery_manager",
                  "technical_contact", "cost_centre", "programme", "support_group", "platform", "hosting_location",
                  "region", "network_zone", "family", "parent", "tags", "run_cost", "chargeback_model", "cmdb_id",
                  "health_status", "retirement_date"]


class UrlItem(BaseModel):
    label: str = ""
    url: str


class EnvironmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    env_type: str = "DEV"
    tier: str | None = None
    purpose: str | None = None
    owner: str | None = None
    delivery_manager: str | None = None
    technical_contact: str | None = None
    cost_centre: str | None = None
    programme: str | None = None
    support_group: str | None = None
    platform: str | None = None
    hosting_location: str | None = None
    region: str | None = None
    network_zone: str | None = None
    urls: list[UrlItem] | None = None
    parent_id: int | None = None
    family: str | None = None
    shared_infrastructure: bool = False
    tags: list[str] | None = None
    attributes: dict[str, Any] | None = None
    run_cost: float | None = None
    chargeback_model: str | None = None
    licence_notes: str | None = None
    retirement_date: date | None = None
    health_check_url: str | None = None
    sensitive_data: bool = False
    production_derived_data: bool = False
    data_controls: str | None = None
    cmdb_id: str | None = None
    status: str | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class EnvironmentPatch(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    env_type: str | None = None
    tier: str | None = None
    purpose: str | None = None
    owner: str | None = None
    delivery_manager: str | None = None
    technical_contact: str | None = None
    cost_centre: str | None = None
    programme: str | None = None
    support_group: str | None = None
    platform: str | None = None
    hosting_location: str | None = None
    region: str | None = None
    network_zone: str | None = None
    urls: list[UrlItem] | None = None
    parent_id: int | None = None
    family: str | None = None
    shared_infrastructure: bool | None = None
    tags: list[str] | None = None
    attributes: dict[str, Any] | None = None
    run_cost: float | None = None
    chargeback_model: str | None = None
    licence_notes: str | None = None
    retirement_date: date | None = None
    health_check_url: str | None = None
    sensitive_data: bool | None = None
    production_derived_data: bool | None = None
    data_controls: str | None = None
    cmdb_id: str | None = None
    row_version: int | None = None


def env_out(env: Environment, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    d = {c: getattr(env, c) for c in EDITABLE}
    d.update({
        "id": env.id, "status": env.status, "allowed_transitions": TRANSITIONS.get(env.status, []),
        "health_status": effective_health(env), "health_checked_at": aware(env.health_checked_at),
        "health_override": ({"status": env.health_override_status, "reason": env.health_override_reason,
                             "until": aware(env.health_override_until)} if env.health_override_status else None),
        "requested_by": env.requested_by, "requested_at": aware(env.requested_at), "sla_due_at": aware(env.sla_due_at),
        "sla_breached": bool(env.status == "Requested" and env.sla_due_at and aware(env.sla_due_at) < now()),
        "decommission_checklist": env.decommission_checklist or [],
        "deleted_at": aware(env.deleted_at), "deleted_by": env.deleted_by,
        "row_version": env.row_version, "created_at": aware(env.created_at), "updated_at": aware(env.updated_at),
        "updated_by": env.updated_by, "urls": env.urls or [], "tags": env.tags or [], "attributes": env.attributes or {},
    })
    if extra:
        d.update(extra)
    else:
        d.update({"variable_count": len(env.variables), "instance_count": len(env.instances)})
    return d


def get_env(db: Session, env_id: int, user: User | None = None, include_deleted: bool = False) -> Environment:
    env = db.get(Environment, env_id)
    if env is None or (env.deleted_at is not None and not include_deleted):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment not found")
    if user is not None and not user.can_see(env):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment not found")
    return env


def resolve_env(db: Session, ref: str | int) -> Environment:
    """Find a live environment by id or (case-insensitive) name."""
    env = None
    if isinstance(ref, int) or str(ref).isdigit():
        env = db.get(Environment, int(ref))
    if env is None:
        env = db.scalar(select(Environment).where(func.lower(Environment.name) == str(ref).strip().lower()))
    if env is None or env.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Environment '{ref}' not found")
    return env


def validate_env_fields(db: Session, data: dict[str, Any], env_id: int | None = None) -> list[str]:
    """Return field errors (name the field and the fix: NFR-06)."""
    errors = []
    types = get_setting(db, "env_types")
    if data.get("env_type") and data["env_type"] not in types:
        errors.append(f"env_type: '{data['env_type']}' is not a valid type; use one of {', '.join(types)}")
    if data.get("name"):
        existing = db.scalar(select(Environment).where(func.lower(Environment.name) == data["name"].lower()))
        if existing is not None and existing.id != env_id:
            errors.append(f"name: an environment called '{data['name']}' already exists"
                          + (" (deleted; restore it instead)" if existing.deleted_at else ""))
    if data.get("parent_id") is not None:
        if env_id is not None and data["parent_id"] == env_id:
            errors.append("parent_id: an environment cannot be its own parent")
        elif db.get(Environment, data["parent_id"]) is None:
            errors.append(f"parent_id: environment {data['parent_id']} does not exist")
        elif env_id is not None:
            seen, cur = set(), db.get(Environment, data["parent_id"])
            while cur is not None and cur.id not in seen:
                if cur.id == env_id:
                    errors.append("parent_id: this would create a cycle in the hierarchy")
                    break
                seen.add(cur.id)
                cur = db.get(Environment, cur.parent_id) if cur.parent_id else None
    mandatory = get_setting(db, "mandatory_fields")
    env_type = data.get("env_type") or "DEV"
    for f in set(mandatory.get("*", [])) | set(mandatory.get(env_type, [])):
        if f in data and data[f] in (None, "", []):
            errors.append(f"{f}: required for {env_type} environments")
    attrs = data.get("attributes") or {}
    for spec in get_setting(db, "custom_attributes"):
        key = spec.get("key")
        if env_type in (spec.get("required_for") or []) and attrs.get(key) in (None, ""):
            errors.append(f"attributes.{key}: '{spec.get('label', key)}' is required for {env_type} environments")
        if spec.get("type") == "select" and attrs.get(key) not in (None, "") and attrs[key] not in spec.get("options", []):
            errors.append(f"attributes.{key}: choose one of {', '.join(spec.get('options', []))}")
        if spec.get("type") == "number" and attrs.get(key) not in (None, ""):
            try:
                float(attrs[key])
            except (TypeError, ValueError):
                errors.append(f"attributes.{key}: must be a number")
    return errors


def _raise_errors(errors: list[str]) -> None:
    if errors:
        dup = [e for e in errors if e.startswith("name: an environment called")]
        if dup:
            raise HTTPException(status.HTTP_409_CONFLICT, dup[0].removeprefix("name: ").capitalize())
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": errors[0], "errors": errors})


def _summaries(db: Session) -> dict[str, dict[int, Any]]:
    var_counts = dict(db.execute(select(Variable.environment_id, func.count()).where(Variable.instance_id.is_(None))
                                 .group_by(Variable.environment_id)).tuples().all())
    inst_counts = dict(db.execute(select(SystemInstance.environment_id, func.count())
                                  .group_by(SystemInstance.environment_id)).tuples().all())
    t = now()
    active = {}
    for b in db.scalars(select(Booking).where(Booking.status.in_(["Approved", "Active"]), Booking.start_at <= t,
                                              Booking.end_at > t)):
        active.setdefault(b.environment_id, []).append({"id": b.id, "project": b.project, "team": b.team,
                                                        "end_at": aware(b.end_at), "partial": None})
    return {"vars": var_counts, "instances": inst_counts, "active": active, "issues": open_issue_counts(db)}


def list_rows(db: Session, user: User, **filters: Any) -> list[dict[str, Any]]:
    q = select(Environment)
    if not filters.get("include_deleted"):
        q = q.where(Environment.deleted_at.is_(None))
    if filters.get("deleted_only"):
        q = q.where(Environment.deleted_at.is_not(None))
    for col in ("env_type", "status", "programme", "region", "family", "platform"):
        if filters.get(col):
            q = q.where(getattr(Environment, col) == filters[col])
    if filters.get("parent_id") is not None:
        q = q.where(Environment.parent_id == filters["parent_id"])
    if filters.get("q"):
        like = f"%{filters['q'].lower()}%"
        q = q.where(or_(func.lower(Environment.name).like(like), func.lower(Environment.description).like(like),
                        func.lower(Environment.owner).like(like), func.lower(Environment.programme).like(like)))
    envs = [e for e in db.scalars(q.order_by(Environment.name)) if user.can_see(e)]
    if filters.get("tag"):
        envs = [e for e in envs if filters["tag"] in (e.tags or [])]
    if filters.get("health"):
        envs = [e for e in envs if effective_health(e) == filters["health"]]
    s = _summaries(db)
    names = {e.id: e.name for e in db.scalars(select(Environment))}
    rows = [env_out(e, {
        "variable_count": s["vars"].get(e.id, 0), "instance_count": s["instances"].get(e.id, 0),
        "active_bookings": s["active"].get(e.id, []), "open_issues": s["issues"].get(e.id, 0),
        "parent": names.get(e.parent_id) if e.parent_id else None,
    }) for e in envs]
    sort = filters.get("sort") or "name"
    desc = sort.startswith("-")
    key = sort.lstrip("-")
    rows.sort(key=lambda r: (r.get(key) is None, str(r.get(key) or "").lower()), reverse=desc)
    return rows


@router.get("", dependencies=[Depends(require_viewer)])
def list_environments(
    q: str | None = None, env_type: str | None = None, status_: str | None = Query(None, alias="status"),
    programme: str | None = None, region: str | None = None, family: str | None = None, platform: str | None = None,
    tag: str | None = None, health: str | None = None, parent_id: int | None = None,
    include_deleted: bool = False, deleted_only: bool = False, sort: str | None = None,
    user: User = Depends(require_viewer), db: Session = Depends(get_db),
):
    return list_rows(db, user, q=q, env_type=env_type, status=status_, programme=programme, region=region,
                     family=family, platform=platform, tag=tag, health=health, parent_id=parent_id,
                     include_deleted=include_deleted or deleted_only, deleted_only=deleted_only, sort=sort)


@router.get("/meta")
def environment_meta(_: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """Lists of values the UI needs to build forms."""
    return {
        "env_types": get_setting(db, "env_types"), "tiers": get_setting(db, "tiers"),
        "platforms": get_setting(db, "platforms"), "lifecycle": LIFECYCLE, "transitions": TRANSITIONS,
        "custom_attributes": get_setting(db, "custom_attributes"),
        "mandatory_fields": get_setting(db, "mandatory_fields"), "policies": get_setting(db, "policies"),
        "system_categories": get_setting(db, "system_categories"),
        "issue_categories": get_setting(db, "issue_categories"),
        "programmes": sorted({p for p in db.scalars(select(Environment.programme)) if p}),
        "regions": sorted({p for p in db.scalars(select(Environment.region)) if p}),
        "families": sorted({p for p in db.scalars(select(Environment.family)) if p}),
        "tags": sorted({t for tags in db.scalars(select(Environment.tags)) for t in (tags or [])}),
    }


@router.get("/export")
def export_environments(format: Literal["csv", "xlsx", "json"] = "csv", user: User = Depends(require_viewer),
                        db: Session = Depends(get_db)):
    rows = list_rows(db, user)
    audit(db, user, "export", "environment", None, {"format": format, "rows": len(rows)})
    db.commit()
    if format == "json":
        return tabular_response(rows, "json", "environments")
    return tabular_response(rows, format, "environments", EXPORT_COLUMNS)


def _create(db: Session, data: dict[str, Any], user: User) -> Environment:
    data = dict(data)
    st = data.pop("status", None) or "Available"
    if st not in LIFECYCLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"status: use one of {', '.join(LIFECYCLE)}")
    env = Environment(**{k: v for k, v in data.items() if k in EDITABLE}, status=st, updated_by=user.name)
    db.add(env)
    db.flush()
    return env


@router.post("", status_code=status.HTTP_201_CREATED)
def create_environment(payload: EnvironmentIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    data = payload.model_dump(mode="json")
    data["retirement_date"] = payload.retirement_date
    check(user, ENV_MANAGER, payload, "create environments")
    _raise_errors(validate_env_fields(db, data))
    env = _create(db, data, user)
    audit(db, user, "create", "environment", env.id, {"name": env.name, "type": env.env_type})
    emit(db, "environment.created", f"Environment {env.name} created", environment=env,
         entity_type="environment", entity_id=env.id)
    db.commit()
    return env_out(env)


class EnvironmentRequestIn(EnvironmentIn):
    justification: str | None = None
    needed_by: date | None = None


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def request_environment(payload: EnvironmentRequestIn, user: User = Depends(require_viewer),
                        db: Session = Depends(get_db)):
    """ENV-08: request a new environment. It starts in Requested with an SLA due date."""
    check(user, BOOKER, payload, "request environments")
    data = payload.model_dump(mode="json", exclude={"justification", "needed_by", "status"})
    data["retirement_date"] = payload.retirement_date
    errors = [e for e in validate_env_fields(db, data) if not e.split(":")[0] in
              {"owner", "delivery_manager", "support_group", "cost_centre"}]
    _raise_errors(errors)
    env = _create(db, {**data, "status": "Requested"}, user)
    env.requested_by = user.name
    env.requested_at = now()
    env.sla_due_at = env.requested_at + timedelta(days=policy(db, "environment_request_sla_days"))
    env.purpose = env.purpose or payload.justification
    audit(db, user, "request", "environment", env.id, {"name": env.name, "justification": payload.justification,
                                                       "needed_by": payload.needed_by})
    emit(db, "environment.requested", f"{user.name} requested environment {env.name}", payload.justification,
         environment=env, entity_type="environment", entity_id=env.id)
    db.commit()
    return env_out(env)


@router.post("/import")
async def import_environments(file: UploadFile = File(...), dry_run: bool = True,
                              format: Literal["csv", "xlsx", "json"] | None = None,
                              user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """ENV-10 / GOV-05: bulk create or update by file. Rows match on `name` (or `id`). Preview with dry_run."""
    check(user, ENV_MANAGER, None, "import environments")
    content = await file.read()
    fmt = fmt_of(file.filename, format)
    try:
        rows = parse_table(content, fmt)
    except Exception as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not read the file: {e}")
    by_name = {e.name.lower(): e for e in db.scalars(select(Environment))}
    issues, plan = [], []
    names_seen = set()
    for idx, raw in enumerate(rows, start=2):
        row = {k.strip(): (v if v != "" else None) for k, v in raw.items() if k}
        if isinstance(row.get("tags"), str):
            row["tags"] = [t.strip() for t in row["tags"].split(",") if t.strip()]
        for b in ("shared_infrastructure", "sensitive_data", "production_derived_data"):
            if isinstance(row.get(b), str):
                row[b] = row[b].strip().lower() in ("true", "yes", "1", "y")
        if "parent" in row:
            parent = row.pop("parent")
            if parent:
                p = by_name.get(str(parent).lower())
                if p is None:
                    issues.append({"row": idx, "column": "parent", "message": f"Unknown parent '{parent}'"})
                    continue
                row["parent_id"] = p.id
        row.pop("id", None)
        for drop in ("health_status", "variable_count", "instance_count"):
            row.pop(drop, None)
        name = str(row.get("name") or "").strip()
        if not name:
            issues.append({"row": idx, "column": "name", "message": "name is required"})
            continue
        if name.lower() in names_seen:
            issues.append({"row": idx, "column": "name", "message": f"Duplicate name '{name}' in file"})
            continue
        names_seen.add(name.lower())
        existing = by_name.get(name.lower())
        try:
            model = EnvironmentPatch if existing else EnvironmentIn
            clean = model.model_validate({k: v for k, v in row.items() if k in model.model_fields})
        except ValidationError as e:
            for err in e.errors():
                issues.append({"row": idx, "column": ".".join(str(x) for x in err["loc"]), "message": err["msg"]})
            continue
        data = clean.model_dump(exclude_unset=True, mode="json")
        if "retirement_date" in data:
            data["retirement_date"] = getattr(clean, "retirement_date")
        merged = ({c: getattr(existing, c) for c in EDITABLE} | data) if existing else data
        errs = validate_env_fields(db, merged, existing.id if existing else None)
        if errs:
            issues += [{"row": idx, "column": e.split(":")[0], "message": e} for e in errs]
            continue
        if existing:
            diff = {k: [getattr(existing, k), v] for k, v in data.items() if k in EDITABLE and getattr(existing, k) != v}
            plan.append({"row": idx, "action": "update" if diff else "unchanged", "name": name, "changes": diff})
        else:
            plan.append({"row": idx, "action": "create", "name": name, "changes": data})
    report = {"dry_run": dry_run, "valid": not issues, "issues": issues, "plan": plan,
              "counts": {a: sum(p["action"] == a for p in plan) for a in ("create", "update", "unchanged")},
              "bulk_operation_id": None}
    if dry_run or issues:
        return report
    changes = []
    for p in plan:
        if p["action"] == "create":
            env = _create(db, p["changes"], user)
            changes.append({"entity": "environment", "id": env.id, "before": None, "after": p["changes"]})
        elif p["action"] == "update":
            env = by_name[p["name"].lower()]
            before = {k: v[0] for k, v in p["changes"].items()}
            apply(env, {k: v[1] for k, v in p["changes"].items()})
            bump(env, user)
            changes.append({"entity": "environment", "id": env.id, "before": before,
                            "after": {k: v[1] for k, v in p["changes"].items()}})
    op = BulkOperation(user=user.name, kind="environments", changes=changes,
                       summary=f"Imported {file.filename}: {report['counts']['create']} created, "
                               f"{report['counts']['update']} updated")
    db.add(op)
    db.flush()
    audit(db, user, "import", "environment", None, {"filename": file.filename, "bulk_operation_id": op.id,
                                                     **report["counts"]})
    db.commit()
    report["bulk_operation_id"] = op.id
    return report


class BulkUpdateIn(BaseModel):
    ids: list[int]
    changes: EnvironmentPatch


@router.patch("/bulk")
def bulk_update(payload: BulkUpdateIn, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    """ENV-10: apply the same change to many environments (rollback via bulk operations)."""
    data = payload.changes.model_dump(exclude_unset=True, exclude={"row_version", "name"}, mode="json")
    if "retirement_date" in data:
        data["retirement_date"] = payload.changes.retirement_date
    changes = []
    for env_id in payload.ids:
        env = get_env(db, env_id, user)
        check(user, ENV_MANAGER, env, "bulk update environments")
        _raise_errors(validate_env_fields(db, {c: getattr(env, c) for c in EDITABLE} | data, env.id))
        diff = apply(env, data)
        if diff:
            bump(env, user)
            changes.append({"entity": "environment", "id": env.id, "before": {k: v[0] for k, v in diff.items()},
                            "after": {k: v[1] for k, v in diff.items()}})
    op = BulkOperation(user=user.name, kind="environments", changes=changes,
                       summary=f"Bulk update of {len(changes)} environments: {', '.join(data)}")
    db.add(op)
    db.flush()
    audit(db, user, "bulk_update", "environment", None, {"ids": payload.ids, "fields": list(data),
                                                          "bulk_operation_id": op.id})
    db.commit()
    return {"updated": len(changes), "bulk_operation_id": op.id}


@router.get("/{env_id}")
def get_environment(env_id: int, include_deleted: bool = False, user: User = Depends(require_viewer),
                    db: Session = Depends(get_db)):
    env = get_env(db, env_id, user, include_deleted)
    s = _summaries(db)
    children = [{"id": c.id, "name": c.name, "env_type": c.env_type, "status": c.status}
                for c in db.scalars(select(Environment).where(Environment.parent_id == env.id,
                                                              Environment.deleted_at.is_(None)))]
    parent = db.get(Environment, env.parent_id) if env.parent_id else None
    return env_out(env, {
        "variable_count": s["vars"].get(env.id, 0), "instance_count": s["instances"].get(env.id, 0),
        "active_bookings": s["active"].get(env.id, []), "open_issues": s["issues"].get(env.id, 0),
        "children": children, "parent": parent.name if parent else None,
        "my_level": user.level_for(env),
    })


@router.patch("/{env_id}")
def update_environment(env_id: int, payload: EnvironmentPatch, user: User = Depends(require_viewer),
                       db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    check(user, ENV_MANAGER, env, "edit environments")
    check_version(env, payload.row_version)
    data = payload.model_dump(exclude_unset=True, exclude={"row_version"}, mode="json")
    if "retirement_date" in data:
        data["retirement_date"] = payload.retirement_date
    merged = {c: getattr(env, c) for c in EDITABLE} | data
    _raise_errors(validate_env_fields(db, merged, env.id))
    diff = apply(env, data)
    if diff:
        bump(env, user)
        audit(db, user, "update", "environment", env.id, {"changes": diff})
        emit(db, "environment.updated", f"{env.name} updated", ", ".join(diff), environment=env,
             entity_type="environment", entity_id=env.id)
    db.commit()
    return env_out(env)


class TransitionIn(BaseModel):
    to: str
    reason: str | None = None
    row_version: int | None = None


@router.post("/{env_id}/transition")
def change_status(env_id: int, payload: TransitionIn, user: User = Depends(require_viewer),
                  db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    check(user, ENV_MANAGER, env, "change the lifecycle status")
    check_version(env, payload.row_version)
    transition(db, env, payload.to, user, payload.reason)
    db.commit()
    return env_out(env)


class ChecklistIn(BaseModel):
    items: list[dict[str, Any]]


@router.put("/{env_id}/checklist")
def update_checklist(env_id: int, payload: ChecklistIn, user: User = Depends(require_viewer),
                     db: Session = Depends(get_db)):
    """ENV-09 decommissioning checklist: [{item, done}]."""
    env = get_env(db, env_id, user)
    check(user, ENV_MANAGER, env, "update the decommissioning checklist")
    old = {i["item"]: i for i in (env.decommission_checklist or [])}
    items = []
    for i in payload.items:
        prev = old.get(i["item"], {})
        done = bool(i.get("done"))
        items.append({"item": i["item"], "done": done,
                      "by": (user.name if done and not prev.get("done") else prev.get("by")) if done else None,
                      "at": (now().isoformat() if done and not prev.get("done") else prev.get("at")) if done else None})
    env.decommission_checklist = items
    bump(env, user)
    audit(db, user, "checklist", "environment", env.id, {"done": sum(i["done"] for i in items), "total": len(items)})
    db.commit()
    return env_out(env)


class CloneIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    include_topology: bool = True
    include_variables: bool = True
    status: str = "Provisioning"


@router.post("/{env_id}/clone", status_code=status.HTTP_201_CREATED)
def clone_environment(env_id: int, payload: CloneIn, user: User = Depends(require_viewer),
                      db: Session = Depends(get_db)):
    """ENV-07: copy the record, topology and configuration as a template for a new environment."""
    src = get_env(db, env_id, user)
    check(user, ENV_MANAGER, src, "clone environments")
    data = {c: getattr(src, c) for c in EDITABLE} | {"name": payload.name.strip(), "cmdb_id": None}
    _raise_errors(validate_env_fields(db, data))
    env = _create(db, data | {"status": payload.status}, user)
    inst_map: dict[int, int] = {}
    if payload.include_topology:
        for i in src.instances:
            clone = SystemInstance(environment_id=env.id, system_id=i.system_id, instance_name=i.instance_name,
                                   mode=i.mode, virtualisation_ref=i.virtualisation_ref, notes=i.notes)
            db.add(clone)
            db.flush()
            inst_map[i.id] = clone.id
        for ei in db.scalars(select(EnvironmentIntegration).where(EnvironmentIntegration.environment_id == src.id)):
            db.add(EnvironmentIntegration(
                environment_id=env.id, integration_id=ei.integration_id, name=ei.name,
                from_instance_id=inst_map.get(ei.from_instance_id), to_instance_id=inst_map.get(ei.to_instance_id),
                protocol=ei.protocol, pattern=ei.pattern, direction=ei.direction, status="not_connected",
                notes=ei.notes))
    if payload.include_variables:
        q = select(Variable).where(Variable.environment_id == src.id)
        for v in db.scalars(q):
            if v.instance_id is not None and v.instance_id not in inst_map:
                continue
            db.add(Variable(environment_id=env.id, instance_id=inst_map.get(v.instance_id) if v.instance_id else None,
                            key=v.key, value="" if v.is_secret else v.value, is_secret=v.is_secret,
                            vault_ref=None, description=v.description, owner=v.owner, value_type=v.value_type,
                            sensitivity=v.sensitivity, updated_by=user.name))
    audit(db, user, "clone", "environment", env.id, {"from": src.name, "topology": payload.include_topology,
                                                     "variables": payload.include_variables})
    db.commit()
    return env_out(env)


@router.delete("/{env_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_environment(env_id: int, purge: bool = False, user: User = Depends(require_viewer),
                       db: Session = Depends(get_db)):
    """ENV-11: soft delete (restorable). `purge=true` permanently deletes an already-deleted environment (admin)."""
    env = get_env(db, env_id, user, include_deleted=purge)
    if purge:
        require_admin(user)
        if env.deleted_at is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Delete the environment before purging it")
        audit(db, user, "purge", "environment", env.id, {"name": env.name})
        db.delete(env)
        db.commit()
        return
    check(user, ENV_MANAGER, env, "delete environments")
    env.deleted_at = now()
    env.deleted_by = user.name
    bump(env, user)
    audit(db, user, "delete", "environment", env.id, {"name": env.name})
    emit(db, "environment.deleted", f"Environment {env.name} deleted", environment=env,
         entity_type="environment", entity_id=env.id)
    db.commit()


@router.post("/{env_id}/restore")
def restore_environment(env_id: int, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    env = get_env(db, env_id, user, include_deleted=True)
    check(user, ENV_MANAGER, env, "restore environments")
    if env.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Environment is not deleted")
    env.deleted_at = None
    env.deleted_by = None
    bump(env, user)
    audit(db, user, "restore", "environment", env.id, {"name": env.name})
    db.commit()
    return env_out(env)


class OverrideIn(BaseModel):
    status: Literal["Healthy", "Degraded", "Down", "Unknown"]
    reason: str = Field(min_length=1)
    until: datetime | None = None
    instance_id: int | None = None


@router.post("/{env_id}/health/override")
def health_override(env_id: int, payload: OverrideIn, user: User = Depends(require_viewer),
                    db: Session = Depends(get_db)):
    """HLT-04: manual status override or planned outage with reason and expiry."""
    env = get_env(db, env_id, user)
    check(user, CONTRIBUTOR, env, "override health status")
    target: Any = env
    if payload.instance_id:
        target = db.get(SystemInstance, payload.instance_id)
        if target is None or target.environment_id != env.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Instance not found in this environment")
    target.health_override_status = payload.status
    target.health_override_reason = payload.reason
    target.health_override_until = payload.until
    audit(db, user, "health_override", "environment", env.id, payload.model_dump(mode="json"))
    emit(db, "health.changed", f"{env.name}: status set to {payload.status} by {user.name}", payload.reason,
         environment=env, entity_type="environment", entity_id=env.id)
    db.commit()
    return env_out(env)


@router.delete("/{env_id}/health/override")
def clear_override(env_id: int, instance_id: int | None = None, user: User = Depends(require_viewer),
                   db: Session = Depends(get_db)):
    env = get_env(db, env_id, user)
    check(user, CONTRIBUTOR, env, "clear a health override")
    target: Any = db.get(SystemInstance, instance_id) if instance_id else env
    target.health_override_status = target.health_override_reason = target.health_override_until = None
    audit(db, user, "health_override_cleared", "environment", env.id, {"instance_id": instance_id})
    db.commit()
    return env_out(env)


def env_instances(db: Session, env: Environment) -> list[SystemInstance]:
    return list(db.scalars(select(SystemInstance).options(selectinload(SystemInstance.shared_with))
                           .where(SystemInstance.environment_id == env.id)))
