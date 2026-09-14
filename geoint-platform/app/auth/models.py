from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    tenant_id: str
    roles: frozenset[str]

    def has_role(self, role: str) -> bool:
        """Rol exacto. Admin NO implica goodmode ni todos los permisos de lectura."""
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))
