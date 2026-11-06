from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class System(Base):
    __tablename__ = "systems"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    layer: Mapped[str | None] = mapped_column(String(64))
    domain: Mapped[str | None] = mapped_column(String(200))
    owner: Mapped[str | None] = mapped_column(String(200))
    environment: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)

    component_details: Mapped[list["ComponentDetail"]] = relationship(
        cascade="all, delete-orphan", order_by="ComponentDetail.id"
    )


class ComponentDetail(Base):
    __tablename__ = "component_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[str] = mapped_column(ForeignKey("systems.id", ondelete="CASCADE"), index=True)
    gateway_tier: Mapped[str | None] = mapped_column(String(100))
    endpoint: Mapped[str | None] = mapped_column(Text)
    queue_references: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    journey: Mapped[str | None] = mapped_column(String(100), index=True)
    upstream_id: Mapped[str] = mapped_column(ForeignKey("systems.id"), index=True)
    downstream_id: Mapped[str] = mapped_column(ForeignKey("systems.id"), index=True)
    pattern: Mapped[str] = mapped_column(String(16))
    primary_protocol: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str | None] = mapped_column(String(50))
    verified_by: Mapped[str | None] = mapped_column(String(200))
    last_verified: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    hops: Mapped[list["Hop"]] = relationship(cascade="all, delete-orphan", order_by="Hop.sequence")


class Hop(Base):
    __tablename__ = "hops"
    __table_args__ = (UniqueConstraint("integration_id", "sequence", name="uq_hop_sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    integration_id: Mapped[str] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    from_system: Mapped[str] = mapped_column(ForeignKey("systems.id"), index=True)
    to_system: Mapped[str] = mapped_column(ForeignKey("systems.id"), index=True)
    protocol: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(16), default="request")
    queue_name: Mapped[str | None] = mapped_column(String(200))
    queue_manager: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)


class DatasetVersion(Base):
    """A full snapshot of the integration dataset, created on every import, edit or rollback."""

    __tablename__ = "dataset_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20))  # import | edit | rollback | seed
    filename: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    system_count: Mapped[int] = mapped_column(Integer, default=0)
    integration_count: Mapped[int] = mapped_column(Integer, default=0)
    hop_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[str] = mapped_column(Text)  # Dataset as JSON


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    user: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[str | None] = mapped_column(Text)  # JSON
    # GOV-02 tamper evidence: each row hashes its content plus the previous row's hash.
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str | None] = mapped_column(String(64))
