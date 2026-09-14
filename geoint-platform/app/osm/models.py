from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class OsmFeature(Base):
    """Features OSM materializadas para consulta local y vector tiles."""

    __tablename__ = "osm_features"
    __table_args__ = (
        Index("ix_osm_features_geometry_gist", "geometry", postgresql_using="gist"),
        Index("ix_osm_features_tenant_class", "tenant_id", "feature_class"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    osm_id: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_class: Mapped[str] = mapped_column(String(64), nullable=False)
    # highway, building, aeroway, waterway, power, amenity, ...
    name: Mapped[str | None] = mapped_column(String(255))
    geometry = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    tags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="overpass")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
