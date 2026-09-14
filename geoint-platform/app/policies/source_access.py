"""Control de acceso a fuentes: la UI no es la frontera de seguridad.

OpenSky queda encapsulado como GOODMODE_ONLY:
  - goodmode: puede leer datos
  - admin: puede configurar/health/credenciales, NO leer observaciones por defecto
  - operator / public: no leen OpenSky
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import HTTPException, status

from app.auth.models import Principal


class AccessPolicy(StrEnum):
    OPEN = "open"  # cualquier autenticado con rol operator+
    OPERATOR = "operator"  # operator, admin, goodmode
    GOODMODE_ONLY = "goodmode_only"  # solo permiso explícito de lectura
    ADMIN_CONFIG = "admin_config"  # solo administración, no datos
    INTERNAL = "internal"  # fuentes self-hosted / dropzone
    PUBLIC_DEMO = "public_demo"  # datasets sanitizados


@dataclass(frozen=True)
class SourceAccessPolicy:
    source_id: str
    access_policy: AccessPolicy
    commercial_status: str  # allowed | restricted | unknown
    retention: str  # transient | standard | long
    # Permisos finos (no roles genéricos)
    read_permission: str | None = None
    admin_permission: str | None = None
    enabled: bool = True


# Políticas canónicas por fuente (backend source of truth)
SOURCE_POLICIES: dict[str, SourceAccessPolicy] = {
    "opensky": SourceAccessPolicy(
        source_id="opensky",
        access_policy=AccessPolicy.GOODMODE_ONLY,
        commercial_status="restricted",
        retention="transient",
        read_permission="geoint.source.opensky.read",
        admin_permission="geoint.source.opensky.admin",
        enabled=True,
    ),
    "celestrak": SourceAccessPolicy(
        source_id="celestrak",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="standard",
        read_permission="geoint.source.celestrak.read",
        admin_permission="geoint.source.celestrak.admin",
    ),
    "usgs_earthquake": SourceAccessPolicy(
        source_id="usgs_earthquake",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="long",
        read_permission="geoint.source.usgs.read",
        admin_permission="geoint.source.usgs.admin",
    ),
    "nasa_firms": SourceAccessPolicy(
        source_id="nasa_firms",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="standard",
        read_permission="geoint.source.firms.read",
        admin_permission="geoint.source.firms.admin",
    ),
    "aviation_weather": SourceAccessPolicy(
        source_id="aviation_weather",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="transient",
        read_permission="geoint.source.aviation_weather.read",
        admin_permission="geoint.source.aviation_weather.admin",
    ),
    "copernicus": SourceAccessPolicy(
        source_id="copernicus",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="standard",
        read_permission="geoint.source.copernicus.read",
        admin_permission="geoint.source.copernicus.admin",
    ),
    "minio_dropzone": SourceAccessPolicy(
        source_id="minio_dropzone",
        access_policy=AccessPolicy.INTERNAL,
        commercial_status="allowed",
        retention="standard",
        read_permission="geoint.source.dropzone.read",
        admin_permission="geoint.source.dropzone.admin",
    ),
    "readsb_local": SourceAccessPolicy(
        source_id="readsb_local",
        access_policy=AccessPolicy.INTERNAL,
        commercial_status="allowed",
        retention="standard",
        read_permission="geoint.source.readsb.read",
        admin_permission="geoint.source.readsb.admin",
    ),
    "ais_file": SourceAccessPolicy(
        source_id="ais_file",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="long",
        read_permission="geoint.source.ais.read",
        admin_permission="geoint.source.ais.admin",
    ),
    "jpl_horizons": SourceAccessPolicy(
        source_id="jpl_horizons",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="standard",
        read_permission="geoint.source.horizons.read",
        admin_permission="geoint.source.horizons.admin",
    ),
    "nexrad": SourceAccessPolicy(
        source_id="nexrad",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="transient",
        read_permission="geoint.source.nexrad.read",
        admin_permission="geoint.source.nexrad.admin",
    ),
    "goes": SourceAccessPolicy(
        source_id="goes",
        access_policy=AccessPolicy.OPERATOR,
        commercial_status="allowed",
        retention="transient",
        read_permission="geoint.source.goes.read",
        admin_permission="geoint.source.goes.admin",
    ),
}


# Mapeo rol → permisos (sin que admin herede lectura de OpenSky)
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "goodmode": frozenset(
        {
            "geoint.source.opensky.read",
            # goodmode también puede leer fuentes abiertas típicas de investigación
            "geoint.source.celestrak.read",
            "geoint.source.usgs.read",
            "geoint.source.firms.read",
            "geoint.source.aviation_weather.read",
            "geoint.source.copernicus.read",
        }
    ),
    "operator": frozenset(
        {
            "geoint.source.celestrak.read",
            "geoint.source.usgs.read",
            "geoint.source.firms.read",
            "geoint.source.aviation_weather.read",
            "geoint.source.copernicus.read",
            "geoint.source.dropzone.read",
            "geoint.source.readsb.read",
            "geoint.source.ais.read",
            "geoint.source.horizons.read",
        }
    ),
    "admin": frozenset(
        {
            # Admin configura, no consume OpenSky por defecto
            "geoint.source.opensky.admin",
            "geoint.source.celestrak.admin",
            "geoint.source.celestrak.read",
            "geoint.source.usgs.admin",
            "geoint.source.usgs.read",
            "geoint.source.firms.admin",
            "geoint.source.firms.read",
            "geoint.source.aviation_weather.admin",
            "geoint.source.aviation_weather.read",
            "geoint.source.copernicus.admin",
            "geoint.source.copernicus.read",
            "geoint.source.dropzone.admin",
            "geoint.source.dropzone.read",
            "geoint.source.readsb.read",
            "geoint.source.readsb.admin",
            "geoint.source.ais.read",
            "geoint.source.ais.admin",
            "geoint.source.horizons.read",
            "geoint.source.horizons.admin",
            "geoint.admin.jobs",
            "geoint.admin.dlq",
            "geoint.admin.tenants",
        }
    ),
    "public": frozenset(),
    "demo": frozenset(),
}


def permissions_for(principal: Principal) -> frozenset[str]:
    perms: set[str] = set()
    for role in principal.roles:
        perms |= ROLE_PERMISSIONS.get(role, frozenset())
    # Permisos explícitos en el token (claim opcional vía roles especiales perm:xxx)
    for role in principal.roles:
        if role.startswith("perm:"):
            perms.add(role[5:])
    return frozenset(perms)


def get_policy(source_id: str) -> SourceAccessPolicy | None:
    return SOURCE_POLICIES.get(source_id)


def can_read_source(principal: Principal, source_id: str) -> bool:
    policy = SOURCE_POLICIES.get(source_id)
    if policy is None or not policy.enabled:
        return False
    perms = permissions_for(principal)
    if policy.read_permission and policy.read_permission in perms:
        return True
    # OPEN policy: cualquier autenticado no-public
    if policy.access_policy == AccessPolicy.OPEN and principal.roles - {"public", "demo"}:
        return True
    return False


def can_admin_source(principal: Principal, source_id: str) -> bool:
    policy = SOURCE_POLICIES.get(source_id)
    if policy is None:
        return False
    perms = permissions_for(principal)
    if policy.admin_permission and policy.admin_permission in perms:
        return True
    return "geoint.admin.jobs" in perms


def assert_can_read_source(principal: Principal, source_id: str) -> None:
    if not can_read_source(principal, source_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "source_access_denied",
                "source_id": source_id,
                "message": (
                    f"Read access to '{source_id}' is not allowed for this principal. "
                    "Restricted sources require explicit permission (e.g. goodmode)."
                ),
            },
        )


def assert_can_admin_source(principal: Principal, source_id: str) -> None:
    if not can_admin_source(principal, source_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "source_admin_denied",
                "source_id": source_id,
            },
        )


def filter_sources_for_principal(
    principal: Principal,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enriquece y filtra: available según lectura; admin ve config sin available read."""
    result = []
    for src in sources:
        sid = src["source_id"]
        policy = SOURCE_POLICIES.get(sid)
        readable = can_read_source(principal, sid)
        adminable = can_admin_source(principal, sid)

        # Ocultar por completo a public/demo si no hay lectura
        if not readable and not adminable:
            if "public" in principal.roles or "demo" in principal.roles:
                continue
            # operator/admin ven la fuente como no disponible para datos
            if "admin" not in principal.roles and "operator" not in principal.roles:
                continue

        entry = {
            **src,
            "available": readable,
            "can_read": readable,
            "can_admin": adminable,
            "access_policy": policy.access_policy.value if policy else "open",
            "commercial_status": policy.commercial_status if policy else "unknown",
            "retention": policy.retention if policy else "standard",
            "scope": (
                "goodmode"
                if policy and policy.access_policy == AccessPolicy.GOODMODE_ONLY
                else "standard"
            ),
        }
        result.append(entry)
    return result


def assert_ingestion_allowed(source_id: str) -> None:
    """Ingestión worker: OpenSky solo si el job está marcado experimental y flag global."""
    from app.core.config import settings

    policy = SOURCE_POLICIES.get(source_id)
    if policy is None:
        return
    if policy.access_policy == AccessPolicy.GOODMODE_ONLY:
        if not getattr(settings, "opensky_ingestion_enabled", False):
            raise PermissionError(
                f"Ingestion for restricted source '{source_id}' is disabled "
                "(set OPENSKY_INGESTION_ENABLED=true only for authorized research use)"
            )
