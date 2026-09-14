from app.domain.models import Event, Observation


class CorrelationEngine:
    def detect(
        self,
        observation: Observation,
    ) -> list[Event]:
        events = []

        if (
            observation.entity_type == "aircraft"
            and observation.speed_mps is not None
            and observation.speed_mps > 343
        ):
            events.append(
                Event(
                    event_type="high_velocity",
                    entity_id=observation.entity_id,
                    observed_at=observation.observed_at,
                    severity="medium",
                    payload={"speed_mps": observation.speed_mps},
                )
            )

        if observation.confidence is not None and observation.confidence < 0.5:
            events.append(
                Event(
                    event_type="low_confidence",
                    entity_id=observation.entity_id,
                    observed_at=observation.observed_at,
                    severity="low",
                    payload={"confidence": observation.confidence},
                )
            )

        if observation.entity_type == "earthquake":
            magnitude = observation.attributes.get("magnitude")

            try:
                magnitude = float(magnitude)
            except (
                TypeError,
                ValueError,
            ):
                magnitude = None

            if magnitude is not None and magnitude >= 5:
                events.append(
                    Event(
                        event_type="significant_earthquake",
                        entity_id=observation.entity_id,
                        observed_at=observation.observed_at,
                        severity="high",
                        payload={"magnitude": magnitude},
                    )
                )

        return events
