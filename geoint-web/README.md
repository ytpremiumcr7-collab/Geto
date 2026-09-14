# GEOINT Web

Frontend Vite + React + MapLibre para la GEOINT Platform.

## Stack

- Vite 5 + React 18 + TypeScript
- MapLibre GL (mapa base OSM)
- Auth JWT contra `/auth/token`
- WebSocket `/ws/events`
- Proxy dev → API `:8000`

## Arranque

```bash
# API (desde geoint-platform)
uvicorn app.main:app --reload --port 8000

# UI
cd geoint-web
npm install
npm run dev
```

Abre http://localhost:5173

Credenciales bootstrap (si el backend usa AUTH_BOOTSTRAP_*):

- `admin` / `admin`
- `operator` / `operator`
- `goodmode` / `goodmode`

## Build

```bash
npm run build
# dist/ → servir detrás de nginx o el mismo reverse proxy
```

## Terreno 3D (DEM)

MapLibre `setTerrain` + tiles Terrarium (AWS elevation open data).
Botones en mapa: **3D** (pitch) y **DEM** (relieve).

Deck.gl no se añadió como dependencia obligatoria: el relieve nativo de MapLibre
cubre la vista operativa sin otro runtime. Se puede superponer deck.gl después
si hace falta heatmap/arc layers.
