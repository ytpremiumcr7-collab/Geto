"""Circuit breaker simple en memoria (por proceso / por source_id)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _successes: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)

    def before_call(self) -> None:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._successes = 0
            else:
                raise CircuitOpenError(f"circuit open: {self.name}")

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._successes += 1
            if self._successes >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failures = 0
        else:
            self._failures = 0
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        if self._state == CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()

    @property
    def state(self) -> CircuitState:
        return self._state


_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(source_id: str) -> CircuitBreaker:
    if source_id not in _breakers:
        _breakers[source_id] = CircuitBreaker(name=source_id)
    return _breakers[source_id]
