"""Read endpoints for the Integration Flow Explorer (FR-1 to FR-10)."""

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import User, get_current_user, require_viewer
from app.database import get_db
from app.flows.config import FlowConfig, get_flow_config
from app.flows.models import Hop, Integration, System
from app.flows.narrative import build_narrative
from app.flows.schemas import (
    ComponentDetailBase,
    GraphEdge,
    GraphOut,
    HopIn,
    HopOut,
    IntegrationIn,
    IntegrationOut,
    IntegrationSummary,
    PairOut,
    SystemIn,
    SystemOut,
    SystemType,
    UserOut,
)

router = APIRouter(tags=["flow explorer"], dependencies=[Depends(require_viewer)])


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(name=user.name, roles=sorted(user.roles))


@router.get("/flow-config", response_model=FlowConfig)
def flow_config():
    return get_flow_config()


def _system_out(s: System, cfg: FlowConfig) -> SystemOut:
    base = SystemIn.model_validate(s, from_attributes=True)
    return SystemOut(
        **base.model_dump(),
        display_layer=cfg.layer_for(s.type, s.layer),
        component_details=[ComponentDetailBase.model_validate(d, from_attributes=True) for d in s.component_details],
    )


def _names(db: Session) -> dict[str, str]:
    return dict(db.execute(select(System.id, System.name)).tuples().all())


def resolve_system(db: Session, ref: str) -> str:
    """Resolve a system id or (case-insensitive) name to its id; deep links use names."""
    if db.get(System, ref) is not None:
        return ref
    sid = db.scalar(select(System.id).where(func.lower(System.name) == ref.strip().lower()))
    if sid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown system '{ref}'")
    return sid


def _filtered_integrations(db: Session, upstream: str | None, downstream: str | None,
                           journey: str | None, pattern: str | None, protocol: str | None):
    q = select(Integration).options(selectinload(Integration.hops))
    if upstream:
        q = q.where(Integration.upstream_id == resolve_system(db, upstream))
    if downstream:
        q = q.where(Integration.downstream_id == resolve_system(db, downstream))
    if journey:
        q = q.where(func.lower(Integration.journey) == journey.strip().lower())
    if pattern:
        q = q.where(Integration.pattern == pattern.strip().lower())
    if protocol:
        p = protocol.strip().upper()
        q = q.where(or_(Integration.primary_protocol == p, Integration.hops.any(Hop.protocol == p)))
    return db.scalars(q.order_by(Integration.name, Integration.id)).all()


@router.get("/systems", response_model=list[SystemOut])
def list_systems(type: SystemType | None = None, db: Session = Depends(get_db)):
    cfg = get_flow_config()
    q = select(System).options(selectinload(System.component_details)).order_by(System.name)
    if type:
        q = q.where(System.type == type.value)
    return [_system_out(s, cfg) for s in db.scalars(q)]


@router.get("/systems/{system_ref}", response_model=SystemOut)
def get_system(system_ref: str, db: Session = Depends(get_db)):
    return _system_out(db.get(System, resolve_system(db, system_ref)), get_flow_config())


@router.get("/journeys", response_model=list[str])
def list_journeys(db: Session = Depends(get_db)):
    rows = db.scalars(select(Integration.journey).where(Integration.journey.is_not(None)).distinct())
    return sorted(rows)


@router.get("/pairs", response_model=list[PairOut])
def list_pairs(
    upstream: str | None = None,
    journey: str | None = None,
    pattern: str | None = None,
    protocol: str | None = None,
    db: Session = Depends(get_db),
):
    """Valid upstream/downstream pairs. With `upstream`, the valid downstream options (FR-1)."""
    names = _names(db)
    pairs: dict[tuple[str, str], list[Integration]] = defaultdict(list)
    for it in _filtered_integrations(db, upstream, None, journey, pattern, protocol):
        pairs[(it.upstream_id, it.downstream_id)].append(it)
    out = [
        PairOut(
            upstream_id=u, upstream_name=names.get(u, u),
            downstream_id=d, downstream_name=names.get(d, d),
            integration_count=len(items),
            journeys=sorted({i.journey for i in items if i.journey}),
        )
        for (u, d), items in pairs.items()
    ]
    return sorted(out, key=lambda p: (p.upstream_name.lower(), p.downstream_name.lower()))


def _integration_out(it: Integration, names: dict[str, str]) -> IntegrationOut:
    base = IntegrationIn.model_validate(it, from_attributes=True)
    hops = [HopIn.model_validate(h, from_attributes=True) for h in it.hops]
    return IntegrationOut(
        **base.model_dump(),
        upstream_name=names.get(it.upstream_id, it.upstream_id),
        downstream_name=names.get(it.downstream_id, it.downstream_id),
        hops=[
            HopOut(**h.model_dump(), from_name=names.get(h.from_system, h.from_system),
                   to_name=names.get(h.to_system, h.to_system))
            for h in hops
        ],
        narrative=build_narrative(base, hops, names),
    )


@router.get("/integrations", response_model=list[IntegrationOut])
def list_integrations(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    journey: str | None = None,
    pattern: str | None = None,
    protocol: str | None = None,
    db: Session = Depends(get_db),
):
    """Integrations matching the selection, each with ordered hops and a narrative (FR-3 to FR-8)."""
    names = _names(db)
    return [_integration_out(it, names) for it in _filtered_integrations(db, from_, to, journey, pattern, protocol)]


@router.get("/integrations/{integration_id}", response_model=IntegrationOut)
def get_integration(integration_id: str, db: Session = Depends(get_db)):
    it = db.get(Integration, integration_id)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Integration not found")
    return _integration_out(it, _names(db))


@router.get("/graph", response_model=GraphOut)
def graph(db: Session = Depends(get_db)):
    """Base architecture: every system, edges aggregated from all hops, and integration summaries."""
    cfg = get_flow_config()
    systems = db.scalars(select(System).options(selectinload(System.component_details)).order_by(System.name)).all()
    integrations = db.scalars(
        select(Integration).options(selectinload(Integration.hops)).order_by(Integration.name)
    ).all()

    edges: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    summaries = []
    for it in integrations:
        system_ids = {it.upstream_id, it.downstream_id}
        for h in it.hops:
            key = (h.from_system, h.to_system, h.protocol, h.direction)
            if it.id not in edges[key]:
                edges[key].append(it.id)
            system_ids |= {h.from_system, h.to_system}
        summaries.append(
            IntegrationSummary(
                id=it.id, name=it.name, journey=it.journey, pattern=it.pattern,
                primary_protocol=it.primary_protocol, status=it.status,
                upstream_id=it.upstream_id, downstream_id=it.downstream_id,
                system_ids=sorted(system_ids),
                protocols=list(dict.fromkeys(h.protocol for h in it.hops)),
            )
        )

    return GraphOut(
        nodes=[_system_out(s, cfg) for s in systems],
        edges=[
            GraphEdge(id=f"{s}>{t}:{p}:{d}", source=s, target=t, protocol=p, direction=d, integration_ids=ids)
            for (s, t, p, d), ids in edges.items()
        ],
        integrations=summaries,
    )
