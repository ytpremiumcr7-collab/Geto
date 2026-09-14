# Instalación completa verificada (R5)

Este paquete **corrige** los P0/P1 de seguridad y trae **dependencias fijadas**.

> No se empaqueta el directorio `.venv` ni `node_modules` dentro del ZIP:
> son binarios de **Linux x86_64** del entorno de build y **rompen** en macOS/Windows
> o con otra glibc. Lo correcto es regenerarlos en tu máquina con los locks.

## Lo que sí está listo

| Artefacto | Estado |
|-----------|--------|
| Código con fixes P0/P1 auth, RLS, file_uri, workers | ✅ |
| `geoint-platform/requirements.lock.txt` (121 pinned packages; no host-local editable path) | ✅ |
| `geoint-web/package-lock.json` + `dist/` build | ✅ |
| Tests verificados en build original | ✅ 24 passed (historical evidence; must be re-run on host) |
| E2E topography | ✅ 10/10 |
| `npm run build` | ✅ |

## Backend (una sola vez)

```bash
cd geoint-platform
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.lock.txt
python -m pip install -e ".[dev]"

# Opcional GDAL Python (viewshed/slope gdaldem):
#   Ubuntu: sudo apt install gdal-bin libgdal-dev python3-gdal
#   pip install gdal==$(gdal-config --version)

cp .env.example .env
# OBLIGATORIO — secrets débiles se RECHAZAN al firmar y al verificar JWT:
python -c "import secrets; print('JWT_SECRET='+secrets.token_hex(32))" >> .env
# Edita .env: AUTH_DISABLED=false, passwords MinIO/Postgres

docker compose up -d
alembic upgrade head
pytest tests/unit/test_auth_security.py -v
PYTHONPATH=. python scripts/e2e_topography.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Atajo:
```bash
bash scripts/bootstrap_dev.sh
```

## Frontend

```bash
cd geoint-web
npm ci          # usa package-lock (reproducible de versiones)
npm run build   # o npm run dev
```

## Verificación mínima de seguridad

```bash
# Debe FALLAR (secret débil):
python -c "
from app.auth.jwt import JWTService
JWTService(secret='change-me-jwt').decode('x')
"
# RuntimeError: JWT_SECRET is missing or uses a forbidden default value
```

## Por qué no va el `.venv` en el ZIP

Incluir un venv “ya instalado” de otro sistema es una falsa comodidad:
falla por ABI, paths absolutos y plataforma. El **lockfile + estos comandos**
es la forma reproducible a nivel de versiones; para una reproducción hermética todavía habría que fijar hashes de artefactos y la plataforma/arquitectura objetivo.
