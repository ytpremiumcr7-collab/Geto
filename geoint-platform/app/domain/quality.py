from app.domain.models import Observation


def calculate_quality(observation: Observation) -> float:
    score = 1.0

    if observation.position is None:
        score -= 0.30

    if observation.accuracy_m is not None:
        if observation.accuracy_m > 1000:
            score -= 0.20
        elif observation.accuracy_m > 100:
            score -= 0.05

    if observation.confidence is not None:
        score *= observation.confidence

    return max(0.0, min(1.0, score))

