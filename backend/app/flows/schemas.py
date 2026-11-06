from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SystemType(str, Enum):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    GATEWAY = "gateway"
    QUEUE_MANAGER = "queue_manager"
    MAINFRAME = "mainframe"


class Pattern(str, Enum):
    SYNC = "sync"
    ASYNC = "async"


class Protocol(str, Enum):
    REST = "REST"
    SOAP = "SOAP"
    MQ = "MQ"
    FILE = "FILE"
    MFT = "MFT"


class Direction(str, Enum):
    REQUEST = "request"
    REPLY = "reply"


def _blank(v: Any) -> Any:
    return None if isinstance(v, str) and not v.strip() else v


def _key(v: Any) -> Any:
    """Normalise enum-like input: 'Queue Manager' -> 'queue_manager'."""
    v = _blank(v)
    return v.strip().lower().replace(" ", "_").replace("-", "_") if isinstance(v, str) else v


def _upper(v: Any) -> Any:
    v = _blank(v)
    return v.strip().upper() if isinstance(v, str) else v


class _Row(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        coerce_numbers_to_str=True,
        use_enum_values=True,
        extra="ignore",
    )

    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        return _blank(v)


# ---- Input rows (Excel rows / edit payloads) -----------------------------------------


class SystemIn(_Row):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    type: SystemType
    layer: str | None = Field(default=None, max_length=64)
    domain: str | None = None
    owner: str | None = None
    environment: str | None = None
    notes: str | None = None

    @field_validator("type", "layer", mode="before")
    @classmethod
    def _norm(cls, v: Any) -> Any:
        return _key(v)


class ComponentDetailBase(_Row):
    gateway_tier: str | None = None
    endpoint: str | None = None
    queue_references: str | None = None
    notes: str | None = None


class ComponentDetailIn(ComponentDetailBase):
    system_id: str = Field(min_length=1)


class IntegrationIn(_Row):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    journey: str | None = None
    upstream_id: str = Field(min_length=1)
    downstream_id: str = Field(min_length=1)
    pattern: Pattern
    primary_protocol: Protocol | None = None
    status: str | None = None
    verified_by: str | None = None
    last_verified: date | None = None
    notes: str | None = None

    @field_validator("journey", "pattern", mode="before")
    @classmethod
    def _norm(cls, v: Any) -> Any:
        v = _blank(v)
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("primary_protocol", mode="before")
    @classmethod
    def _proto(cls, v: Any) -> Any:
        return _upper(v)


class HopBase(_Row):
    sequence: int = Field(ge=1)
    from_system: str = Field(min_length=1)
    to_system: str = Field(min_length=1)
    protocol: Protocol
    direction: Direction = Direction.REQUEST
    queue_name: str | None = None
    queue_manager: str | None = None
    notes: str | None = None

    @field_validator("protocol", mode="before")
    @classmethod
    def _proto(cls, v: Any) -> Any:
        return _upper(v)

    @field_validator("direction", mode="before")
    @classmethod
    def _dir(cls, v: Any) -> Any:
        return _key(v) or Direction.REQUEST.value


class HopIn(HopBase):
    integration_id: str = Field(min_length=1)


class Dataset(BaseModel):
    systems: list[SystemIn] = []
    integrations: list[IntegrationIn] = []
    hops: list[HopIn] = []
    component_details: list[ComponentDetailIn] = []

    def counts(self) -> dict[str, int]:
        return {
            "systems": len(self.systems),
            "integrations": len(self.integrations),
            "hops": len(self.hops),
            "component_details": len(self.component_details),
        }


# ---- Edit payloads (FR-14) ------------------------------------------------------------


class SystemEdit(SystemIn):
    component_details: list[ComponentDetailBase] = []


class IntegrationEdit(IntegrationIn):
    hops: list[HopBase] = []


# ---- Validation -----------------------------------------------------------------------


class ValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    sheet: str
    row: int | None = None
    column: str | None = None
    ref: str | None = None
    message: str


class ImportReport(BaseModel):
    filename: str | None
    dry_run: bool
    valid: bool
    imported: bool
    version_id: int | None = None
    counts: dict[str, int]
    error_count: int
    warning_count: int
    issues: list[ValidationIssue]


# ---- Read models ------------------------------------------------------------------------


class SystemOut(SystemIn):
    display_layer: str
    component_details: list[ComponentDetailBase] = []


class HopOut(HopIn):
    from_name: str
    to_name: str


class IntegrationOut(IntegrationIn):
    upstream_name: str
    downstream_name: str
    hops: list[HopOut]
    narrative: list[str]


class IntegrationSummary(BaseModel):
    id: str
    name: str
    journey: str | None
    pattern: str
    primary_protocol: str | None
    status: str | None
    upstream_id: str
    downstream_id: str
    system_ids: list[str]
    protocols: list[str]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    protocol: str
    direction: str
    integration_ids: list[str]


class GraphOut(BaseModel):
    nodes: list[SystemOut]
    edges: list[GraphEdge]
    integrations: list[IntegrationSummary]


class PairOut(BaseModel):
    upstream_id: str
    upstream_name: str
    downstream_id: str
    downstream_name: str
    integration_count: int
    journeys: list[str]


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    created_by: str
    source: str
    filename: str | None
    summary: str | None
    system_count: int
    integration_count: int
    hop_count: int
    is_current: bool = False


class AuditOut(BaseModel):
    id: int
    at: datetime
    user: str
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict[str, Any] | None


class UserOut(BaseModel):
    name: str
    roles: list[str]
