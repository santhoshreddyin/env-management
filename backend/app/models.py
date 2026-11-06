"""Environment management platform data model.

System and integration *catalogue* rows live in ``app.flows.models`` and are replaced
wholesale on every flow import/edit, so tables here refer to them by id only (no
foreign keys): a catalogue edit must never cascade into environment topology.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Environment inventory (ENV-*) ----------------------------------------------------


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ENV-01 classification
    env_type: Mapped[str] = mapped_column(String(20), default="DEV", index=True)
    tier: Mapped[str | None] = mapped_column(String(50))
    purpose: Mapped[str | None] = mapped_column(Text)
    # ENV-02 ownership
    owner: Mapped[str | None] = mapped_column(String(200))
    delivery_manager: Mapped[str | None] = mapped_column(String(200))
    technical_contact: Mapped[str | None] = mapped_column(String(200))
    cost_centre: Mapped[str | None] = mapped_column(String(100))
    programme: Mapped[str | None] = mapped_column(String(200), index=True)
    support_group: Mapped[str | None] = mapped_column(String(200))
    # ENV-03 lifecycle
    status: Mapped[str] = mapped_column(String(30), default="Available", index=True)
    # ENV-04 hosting
    platform: Mapped[str | None] = mapped_column(String(100))
    hosting_location: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(100), index=True)
    network_zone: Mapped[str | None] = mapped_column(String(100))
    urls: Mapped[list | None] = mapped_column(JSON)  # [{label, url}]
    # ENV-05 hierarchy and grouping
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="SET NULL"))
    family: Mapped[str | None] = mapped_column(String(100))
    shared_infrastructure: Mapped[bool] = mapped_column(Boolean, default=False)
    # ENV-06 tags and custom attributes
    tags: Mapped[list | None] = mapped_column(JSON)
    attributes: Mapped[dict | None] = mapped_column(JSON)
    # ENV-12 cost
    run_cost: Mapped[float | None] = mapped_column(Float)  # per month
    chargeback_model: Mapped[str | None] = mapped_column(String(50))
    licence_notes: Mapped[str | None] = mapped_column(Text)
    # ENV-08 request workflow
    requested_by: Mapped[str | None] = mapped_column(String(200))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ENV-09 decommissioning
    retirement_date: Mapped[date | None] = mapped_column(Date)
    decommission_checklist: Mapped[list | None] = mapped_column(JSON)  # [{item, done, by, at}]
    # ENV-11 soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[str | None] = mapped_column(String(200))
    # HLT-01/02/04 health
    health_status: Mapped[str] = mapped_column(String(20), default="Unknown")
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_check_url: Mapped[str | None] = mapped_column(String(500))
    health_override_status: Mapped[str | None] = mapped_column(String(20))
    health_override_reason: Mapped[str | None] = mapped_column(Text)
    health_override_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # TDM-05 sensitive data
    sensitive_data: Mapped[bool] = mapped_column(Boolean, default=False)
    production_derived_data: Mapped[bool] = mapped_column(Boolean, default=False)
    data_controls: Mapped[str | None] = mapped_column(Text)
    # INT-02 CMDB link
    cmdb_id: Mapped[str | None] = mapped_column(String(100), index=True)
    # NFR-09 optimistic concurrency
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str | None] = mapped_column(String(200))

    # Environment-scoped variables only (instance-scoped ones also carry environment_id).
    variables: Mapped[list["Variable"]] = relationship(
        order_by="Variable.key", viewonly=True,
        primaryjoin="and_(Environment.id == Variable.environment_id, Variable.instance_id.is_(None))",
    )
    instances: Mapped[list["SystemInstance"]] = relationship(
        back_populates="environment", cascade="all, delete-orphan", order_by="SystemInstance.instance_name",
        foreign_keys="SystemInstance.environment_id",
    )


# --- Topology (TOP-*) -------------------------------------------------------------------


class SystemProfile(Base):
    """Catalogue attributes for a system (TOP-01) kept outside the versioned flow dataset."""

    __tablename__ = "system_profiles"

    system_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str | None] = mapped_column(String(32))  # application|middleware|database|api|mainframe|third_party
    criticality: Mapped[str | None] = mapped_column(String(20))  # critical|high|medium|low
    technology: Mapped[str | None] = mapped_column(String(200))
    owner: Mapped[str | None] = mapped_column(String(200))
    domain: Mapped[str | None] = mapped_column(String(200))


instance_shares = Table(
    "instance_shares",
    Base.metadata,
    Column("instance_id", ForeignKey("system_instances.id", ondelete="CASCADE"), primary_key=True),
    Column("environment_id", ForeignKey("environments.id", ondelete="CASCADE"), primary_key=True),
)


class SystemInstance(Base):
    """A catalogue system as it exists in one environment (TOP-02/04/09, DEP-01, HLT-01)."""

    __tablename__ = "system_instances"
    __table_args__ = (Index("ix_instance_env_system", "environment_id", "system_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    system_id: Mapped[str] = mapped_column(String(64), index=True)
    instance_name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(500))
    deployed_version: Mapped[str | None] = mapped_column(String(100))
    build: Mapped[str | None] = mapped_column(String(100))
    commit_sha: Mapped[str | None] = mapped_column(String(100))
    release: Mapped[str | None] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20), default="real")  # real|virtualised|stubbed|mocked|not_available
    virtualisation_ref: Mapped[str | None] = mapped_column(String(300))
    last_verified: Mapped[date | None] = mapped_column(Date)
    verified_by: Mapped[str | None] = mapped_column(String(200))
    health_status: Mapped[str] = mapped_column(String(20), default="Unknown")
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_check_url: Mapped[str | None] = mapped_column(String(500))
    health_override_status: Mapped[str | None] = mapped_column(String(20))
    health_override_reason: Mapped[str | None] = mapped_column(Text)
    health_override_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    environment: Mapped[Environment] = relationship(back_populates="instances", foreign_keys=[environment_id])
    shared_with: Mapped[list[Environment]] = relationship(secondary=instance_shares)


class EnvironmentIntegration(Base):
    """An integration between system instances in one environment (TOP-03)."""

    __tablename__ = "environment_integrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    integration_id: Mapped[str | None] = mapped_column(String(64), index=True)  # catalogue integration
    name: Mapped[str | None] = mapped_column(String(200))
    from_instance_id: Mapped[int | None] = mapped_column(ForeignKey("system_instances.id", ondelete="SET NULL"))
    to_instance_id: Mapped[int | None] = mapped_column(ForeignKey("system_instances.id", ondelete="SET NULL"))
    protocol: Mapped[str | None] = mapped_column(String(16))
    pattern: Mapped[str | None] = mapped_column(String(16))
    direction: Mapped[str | None] = mapped_column(String(20))  # one_way|two_way
    status: Mapped[str] = mapped_column(String(20), default="connected")  # connected|broken|not_connected|virtualised
    endpoint: Mapped[str | None] = mapped_column(String(500))
    last_verified: Mapped[date | None] = mapped_column(Date)
    verified_by: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)


# --- Deployments (DEP-*) ----------------------------------------------------------------


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (Index("ix_deploy_env_at", "environment_id", "deployed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("system_instances.id", ondelete="CASCADE"), index=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    system_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(100))
    build: Mapped[str | None] = mapped_column(String(100))
    commit_sha: Mapped[str | None] = mapped_column(String(100))
    release: Mapped[str | None] = mapped_column(String(100))
    deployed_by: Mapped[str] = mapped_column(String(200))
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    pipeline: Mapped[str | None] = mapped_column(String(200))
    pipeline_run_url: Mapped[str | None] = mapped_column(String(500))
    outcome: Mapped[str] = mapped_column(String(20), default="success")  # success|failed|rolled_back|in_progress
    rollback_of_id: Mapped[int | None] = mapped_column(ForeignKey("deployments.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual|ci
    tool: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)


class PromotionPath(Base):
    """Release train / promotion path, e.g. DEV -> SIT -> UAT -> PreProd (DEP-06)."""

    __tablename__ = "promotion_paths"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    stages: Mapped[list] = mapped_column(JSON)  # [{environment_id, gate_status, gate_note}]


# --- Bookings (BKG-*) -------------------------------------------------------------------

booking_instances = Table(
    "booking_instances",
    Base.metadata,
    Column("booking_id", ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True),
    Column("instance_id", ForeignKey("system_instances.id", ondelete="CASCADE"), primary_key=True),
)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (Index("ix_booking_env_range", "environment_id", "start_at", "end_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    project: Mapped[str] = mapped_column(String(200), index=True)
    team: Mapped[str | None] = mapped_column(String(200), index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="Requested", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="project")  # production_fix|release|project|training
    requested_by: Mapped[str] = mapped_column(String(200))
    approver: Mapped[str | None] = mapped_column(String(200))  # delegated approver
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    series_id: Mapped[str | None] = mapped_column(String(40), index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    expiry_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    environment: Mapped[Environment] = relationship()
    instances: Mapped[list[SystemInstance]] = relationship(secondary=booking_instances)


# --- Calendar: freezes, changes, outages, refreshes (DEP-07, CHG-04) -------------------


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # freeze|blackout|planned_change|release|outage|refresh|maintenance
    title: Mapped[str] = mapped_column(String(300))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enforce: Mapped[bool] = mapped_column(Boolean, default=False)
    external_ref: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(200))


# --- Issues and incidents (CHG-*) -------------------------------------------------------


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    instance_id: Mapped[int | None] = mapped_column(ForeignKey("system_instances.id", ondelete="SET NULL"))
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="issue")  # issue|incident
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # critical|high|medium|low
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|in_progress|resolved|closed
    owner: Mapped[str | None] = mapped_column(String(200))
    resolution: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50))  # root-cause category
    known_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    workaround: Mapped[str | None] = mapped_column(Text)
    external_system: Mapped[str | None] = mapped_column(String(30))  # servicenow|jira|azure_devops
    external_ref: Mapped[str | None] = mapped_column(String(100), index=True)
    external_url: Mapped[str | None] = mapped_column(String(500))
    hours_lost: Mapped[float | None] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(200))
    row_version: Mapped[int] = mapped_column(Integer, default=1)


# --- Configuration and secrets (CFG-*, SEC-*) -------------------------------------------


class Variable(Base):
    """A configuration variable.

    Scope: global default (no environment, no instance), environment, or system instance
    (instance_id set; environment_id holds the instance's environment). Resolution is
    global < environment < instance (CFG-02).
    """

    __tablename__ = "variables"
    __table_args__ = (Index("ix_variable_scope_key", "environment_id", "instance_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    instance_id: Mapped[int | None] = mapped_column(ForeignKey("system_instances.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(255))
    value: Mapped[str] = mapped_column(Text, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    # CFG-03 metadata
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(200))
    value_type: Mapped[str] = mapped_column(String(20), default="string")  # string|number|boolean|url|json
    sensitivity: Mapped[str] = mapped_column(String(20), default="internal")  # public|internal|confidential|restricted
    # SEC-01 / SEC-04
    vault_ref: Mapped[str | None] = mapped_column(String(500))
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotation_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotation_owner: Mapped[str | None] = mapped_column(String(200))
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str | None] = mapped_column(String(200))

    environment: Mapped[Environment | None] = relationship()


class VariableHistory(Base):
    """Per-variable change history (CFG-05). Secret values are never stored here."""

    __tablename__ = "variable_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    variable_id: Mapped[int] = mapped_column(Integer, index=True)  # no FK: history survives deletion
    environment_id: Mapped[int | None] = mapped_column(Integer, index=True)
    instance_id: Mapped[int | None] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(20))  # create|update|delete|restore|import|copy
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    user: Mapped[str] = mapped_column(String(200))
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict | None] = mapped_column(JSON)  # metadata field diffs


class ConfigTemplateKey(Base):
    """Required / default variables per environment type (CFG-08)."""

    __tablename__ = "config_template_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    env_type: Mapped[str] = mapped_column(String(20), index=True)  # or "*" for every type
    key: Mapped[str] = mapped_column(String(255))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


# --- Test data (TDM-*) ------------------------------------------------------------------


class TestDataSet(Base):
    __tablename__ = "test_data_sets"
    __test__ = False  # not a pytest class

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200))
    source_environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="SET NULL"))
    system_id: Mapped[str | None] = mapped_column(String(64))
    volume: Mapped[str | None] = mapped_column(String(100))
    refresh_date: Mapped[date | None] = mapped_column(Date)
    masking_status: Mapped[str] = mapped_column(String(20), default="masked")  # masked|unmasked|synthetic|partial
    production_derived: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[str | None] = mapped_column(String(200))
    reserved_for_booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"))
    reserved_by: Mapped[str | None] = mapped_column(String(200))
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataJob(Base):
    __tablename__ = "data_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("test_data_sets.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # refresh|mask|subset|synthesise
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled|running|succeeded|failed
    owner: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


# --- Health (HLT-*) ---------------------------------------------------------------------


class HealthResult(Base):
    __tablename__ = "health_results"
    __table_args__ = (Index("ix_health_env_at", "environment_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    instance_id: Mapped[int | None] = mapped_column(ForeignKey("system_instances.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    response_ms: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), default="check")  # check|monitor:<tool>|manual|rollup


# --- Notifications, subscriptions, webhooks (BKG-09, HLT-06, INT-06/07) -----------------


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_user_read", "recipient", "read"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    event: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped[str] = mapped_column(String(200), index=True)
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    events: Mapped[list] = mapped_column(JSON)  # ["health.changed", "booking.*", ...]
    channel: Mapped[str] = mapped_column(String(20), default="inapp")  # inapp|email
    email: Mapped[str | None] = mapped_column(String(300))


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(1000))
    kind: Mapped[str] = mapped_column(String(20), default="generic")  # generic|slack|teams
    events: Mapped[list] = mapped_column(JSON)
    secret: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(200))
    last_status: Mapped[str | None] = mapped_column(String(200))
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Governance (GOV-*) -----------------------------------------------------------------


class RoleAssignment(Base):
    """A role granted to a user or group (principal "group:<name>"), optionally scoped (GOV-01)."""

    __tablename__ = "role_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    principal: Mapped[str] = mapped_column(String(200), index=True)
    role: Mapped[str] = mapped_column(String(30))
    scope_type: Mapped[str] = mapped_column(String(20), default="global")  # global|environment|programme|region|family
    scope_value: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApiToken(Base):
    """Service tokens for pipelines and integrations (INT-01/03)."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    role: Mapped[str] = mapped_column(String(30))
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    """Admin-configurable lists of values, policies and templates (GOV-03/04/08, ENV-06)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list] = mapped_column(JSON)
    updated_by: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SavedView(Base):
    """Saved list filters / columns per user and page (RPT-02)."""

    __tablename__ = "saved_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped[str] = mapped_column(String(200), index=True)
    page: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)


class BulkOperation(Base):
    """A bulk change with before/after snapshots so it can be previewed and rolled back (GOV-05)."""

    __tablename__ = "bulk_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    user: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))  # environments|variables|topology
    summary: Mapped[str] = mapped_column(Text)
    changes: Mapped[list] = mapped_column(JSON)  # [{entity, id, before, after}]
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rolled_back_by: Mapped[str | None] = mapped_column(String(200))


class ApprovalRequest(Base):
    """A change waiting for approval, e.g. config copy into a protected environment (CFG-07, GOV-03)."""

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected
    requested_by: Mapped[str] = mapped_column(String(200))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
