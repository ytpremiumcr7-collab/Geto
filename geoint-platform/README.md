# GEOINT Platform v2

Plataforma de inteligencia geoespacial modular para:

- aeronaves
- satélites
- incendios
- terremotos
- meteorología aeronáutica
- datos EO/STAC
- tracking
- correlación
- replay
- observabilidad

## Arquitectura

\`\`\`
                         ┌──────────────────────┐
                         │       FastAPI        │
                         │ REST / WebSocket     │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┼────────────────┐
                    │               │                │
               PostgreSQL       ClickHouse        Redis
                 PostGIS        Analytics          Cache
                    │               │                │
                    └───────────────┼────────────────┘
                                    │
                              NATS JetStream
                                    │
                           Ingestion Pipeline
                                    │
              ┌─────────────────────┼─────────────────────┐
              │          │           │          │          │
            OpenSky   CelesTrak     USGS      FIRMS   AviationWx
              │          │           │          │          │
              └─────────────────────┴──────────┴──────────┘
                                    │
                              Normalization
                                    │
                              Deduplication
                                    │
                              Quality Score
                                    │
                         Tracking / Correlation
                                    │
                                  MinIO
                              raw payloads
\`\`\`

## Fuentes implementadas

- OpenSky
- CelesTrak
- USGS Earthquakes
- NASA FIRMS
- AviationWeather.gov
- Copernicus Data Space STAC

## Requisitos

- Docker
- Docker Compose
- Node.js 18+ para ejecutar el generador

## Generar

\`\`\`bash
node generate-geoint-platform-v2.js ./geoint-platform
cd geoint-platform
cp .env.example .env
\`\`\`

## Arrancar infraestructura

\`\`\`bash
docker compose up -d
\`\`\`

## Ejecutar API localmente

\`\`\`python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
\`\`\`

## Tests

\`\`\`bash
pytest
\`\`\`

## Endpoints

- GET /health/live
- GET /health/ready
- GET /api/v1/sources
- GET /api/v1/observations
- GET /api/v1/entities/{entity_id}
- GET /api/v1/entities/{entity_id}/track
- GET /api/v1/events

## Variables obligatorias para fuentes autenticadas

OpenSky:

- OPENSKY_CLIENT_ID
- OPENSKY_CLIENT_SECRET

NASA FIRMS:

- FIRMS_MAP_KEY

Las credenciales deben configurarse mediante .env/secrets y nunca incluirse en Git.

