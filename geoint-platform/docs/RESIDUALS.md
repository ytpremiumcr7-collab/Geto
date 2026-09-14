# Residuales cerrados / estado

## P0
- [x] SourceJob.tenant_id en ORM + seed
- [x] tenant en publish_job → worker → dispatcher

## P1
- [x] Entity unique (tenant_id, entity_id) — migración 0007
- [x] SourceRun.tenant_id — modelo + dispatcher + 0007
- [x] FIRMS seed `enabled=false` hasta FIRMS_MAP_KEY
- [x] MinIO healthcheck sin `mc ready`
- [x] Login UI banner DEV token issuer
- [x] workers/ingestion.py marcado DEPRECATED
- [ ] Rate limit fail-open: intencional (lean); prod high-sec → fail-closed

## NASA / open data
| Fuente | Key |
|--------|-----|
| GOES, Horizons, NEXRAD | No |
| FIRMS | Sí (MAP_KEY gratis) |

## P2 producto
Timeline / track line UI, OIDC IdP real, osm2pgsql — fuera de este cierre.
