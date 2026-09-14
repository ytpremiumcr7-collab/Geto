from datetime import datetime, timezone

from app.domain.models import GeoPoint, Observation
from app.domain.quality import calculate_quality


def test_quality_without_position():
    observation = Observation(
        entity_id="test",
        entity_type="aircraft",
        source_id="test",
        observed_at=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
    )

    assert calculate_quality(observation) == 0.7


def test_quality_with_confidence():
    observation = Observation(
        entity_id="test",
        entity_type="aircraft",
        source_id="test",
        observed_at=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
        position=GeoPoint(
            lon=-98,
            lat=19,
        ),
        confidence=0.8,
    )

    assert calculate_quality(observation) == 0.8

