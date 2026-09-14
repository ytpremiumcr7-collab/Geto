from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    altitude_m: float | None = None


class Observation(BaseModel):
    entity_id: str
    entity_type: str
    tenant_id: str = "default"

    source_id: str
    source_record_id: str | None = None

    observed_at: datetime
    received_at: datetime

    position: GeoPoint | None = None

    speed_mps: float | None = None
    heading_deg: float | None = Field(default=None, ge=0, lt=360)

    accuracy_m: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    raw_payload: dict[str, Any] | list[Any] | None = None


class SourceStatus(BaseModel):
    source_id: str
    enabled: bool
    authenticated: bool
    description: str


class Event(BaseModel):
    event_type: str
    entity_id: str | None
    observed_at: datetime
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"
    payload: dict[str, Any] = Field(default_factory=dict)
