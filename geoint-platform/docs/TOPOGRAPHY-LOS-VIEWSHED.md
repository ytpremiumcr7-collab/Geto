# LOS y Viewshed — precisión y límites

## Line of Sight (LOS)

**Algoritmo:** perfil densificado a `sample_distance_m` (default 5 m) y prueba de oclusión
por interpolación lineal de la línea de mira entre observador y objetivo.

| Parámetro | Default | Efecto |
|-----------|---------|--------|
| `observer_height_m` | 1.7 | Altura del sensor sobre el DEM |
| `target_height_m` | 0.0 | Altura del objetivo sobre el DEM |
| `sample_distance_m` | 5.0 | Paso entre muestras del perfil |

### Qué modela
- Oclusión por terreno muestreado a lo largo del gran círculo aproximado (perfil en CRS del raster).
- Endpoints con nodata → `visible=false` y nota explícita.

### Qué **no** modela (límites MVP)
- **Refracción atmosférica** (k-factor); el núcleo LOS no aplica curvatura de rayo.
- **Curvatura terrestre** explícita en LOS (sí opcional en viewshed vía `curvature_coeff`).
- **Vegetación / edificios** — solo superficie del DEM.
- **Fresnel / RF** — es LOS óptico geométrico, no radio.
- Precisión limitada por **resolución del DEM** y `sample_distance_m` (sub-muestreo puede omitir picos estrechos).

### Precisión esperada
| DEM | Resolución típica | Uso recomendado |
|-----|-------------------|-----------------|
| AWS Terrarium | ~30 m | Visual / rough LOS |
| SRTM/Copernicus GLO-30 | 30 m | Táctico aproximado |
| INEGI CE-M | 5–15 m (producto) | Mejor detalle regional MX |
| LiDAR/COG local | submétrico | Mejor; aún sin clutter |

**Regla práctica:** incertidumbre horizontal del orden del **pixel del DEM**; no usar para
certificación de seguridad de vuelo ni targeting militar sin validación independiente.

Respuesta API incluye `algorithm`, `assumptions`, `limits` (ver engine).

## Viewshed

**Algoritmo:** `gdal.ViewshedGenerate` (Wang et al., modo `GVM_Edge`).

| Parámetro | Default | Notas |
|-----------|---------|-------|
| `max_distance_m` | 5000 | Radio de análisis; en DEM geográfico se convierte ≈ m/111120 → grados |
| `curvature_coeff` | 0.85714 | Factor de refracción GDAL (≈ 4/7 tierra estándar) |
| `observer_height_m` / `target_height_m` | 1.7 / 0 | Sobre el DEM |

### Límites
- Coste CPU/memoria crece con radio y tamaño del raster; recortar DEM (clip) antes.
- En CRS geográficos la conversión m→grados es **aproximada** (no azimutal exacta).
- Valores de salida: visible=255, invisible=0, out-of-range=0, nodata=-1 (GDAL).
- Misma limitación de clutter (solo DEM).

### Buenas prácticas
1. Registrar COG en el catálogo del tenant (MinIO `dem/`).
2. Clip al AOI del workspace antes de viewshed > 10 km.
3. Documentar el DEM (`resolution_m`, datum vertical) en metadatos del producto derivado.
