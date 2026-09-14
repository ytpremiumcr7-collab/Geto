import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_id", name="uq_entities_tenant_entity_id"),
        Index("ix_entities_entity_type", "entity_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(String(128), default="default")

    entity_id: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(64))

    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    properties: Mapped[dict | None] = mapped_column(JSON)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            "entity_id",
            "observed_at",
            name="uq_observations_tenant_source_entity_time",
        ),
        Index(
            "ix_observations_entity_time",
            "entity_id",
            "observed_at",
        ),
        Index(
            "ix_observations_source_time",
            "source_id",
            "observed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(String(128), default="default")

    entity_id: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(64))

    source_id: Mapped[str] = mapped_column(String(128))
    source_record_id: Mapped[str | None] = mapped_column(String(255))

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    geometry = mapped_column(
        Geometry(
            geometry_type="POINTZ",
            srid=4326,
            spatial_index=True,
        ),
        nullable=True,
    )

    altitude_m: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)

    attributes: Mapped[dict | None] = mapped_column(JSON)
    provenance: Mapped[dict | None] = mapped_column(JSON)

    raw_payload_uri: Mapped[str | None] = mapped_column(Text)


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(String(128), default="default", index=True)
    source_id: Mapped[str] = mapped_column(String(128), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(32))
    records_seen: Mapped[int] = mapped_column(default=0)
    records_normalized: Mapped[int] = mapped_column(default=0)

    error: Mapped[str | None] = mapped_column(Text)
