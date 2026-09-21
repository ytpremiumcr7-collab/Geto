from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.models import Observation


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    source_type: str
    description: str
    endpoint: str
    authentication: str = "none"
    license_name: str | None = None
    commercial_allowed: bool | None = None
    attribution_required: bool = False
    access_policy: str = "operator"  # open|operator|goodmode_only|internal|public_demo
    commercial_status: str = "unknown"  # allowed|restricted|unknown
    retention: str = "standard"  # transient|standard|long


class SourceAdapter(ABC):
    metadata: SourceMetadata

    @abstractmethod
    async def health(self) -> bool:
        pass

    @abstractmethod
    async def fetch(self, **kwargs) -> Any:
        pass

    @staticmethod
    def _reject_unexpected_fetch_kwargs(kwargs: dict[str, Any]) -> None:
        if kwargs:
            names = ", ".join(sorted(kwargs))
            raise TypeError(f"unexpected fetch keyword argument(s): {names}")

    @abstractmethod
    def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        raise NotImplementedError
