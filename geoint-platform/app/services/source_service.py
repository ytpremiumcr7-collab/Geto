from __future__ import annotations

from app.auth.models import Principal
from app.policies.source_access import filter_sources_for_principal, get_policy
from app.sources.registry import create_adapters


class SourceService:
    def __init__(self):
        self.adapters = create_adapters()

    def list_raw(self):
        return [
            {
                "source_id": adapter.metadata.source_id,
                "source_type": adapter.metadata.source_type,
                "description": adapter.metadata.description,
                "endpoint": adapter.metadata.endpoint,
                "authentication": adapter.metadata.authentication,
                "license": adapter.metadata.license_name,
                "commercial_allowed": adapter.metadata.commercial_allowed,
                "attribution_required": adapter.metadata.attribution_required,
                "access_policy": getattr(adapter.metadata, "access_policy", "operator"),
                "commercial_status": getattr(adapter.metadata, "commercial_status", "unknown"),
                "retention": getattr(adapter.metadata, "retention", "standard"),
            }
            for adapter in self.adapters.values()
        ]

    def list_for(self, principal: Principal):
        return filter_sources_for_principal(principal, self.list_raw())

    def get(self, source_id: str):
        return self.adapters.get(source_id)

    def policy(self, source_id: str):
        return get_policy(source_id)
