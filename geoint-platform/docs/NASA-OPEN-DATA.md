# NASA / NOAA open data en GEOINT

## Sin API key
| Recurso | Uso en plataforma |
|---------|-------------------|
| **NASA GIBS** tiles WMTS | Capas mapa: Blue Marble, VIIRS True Color (botones NASA / VIIRS) |
| **Terrarium DEM** (AWS) | Relieve 3D MapLibre (`setTerrain`) |
| **GOES** AWS Open Data | Adapter `goes` — índice productos ABI |
| **JPL Horizons** | Adapter `jpl_horizons` — efemérides |
| **NEXRAD** AWS | Adapter `nexrad` — índice Level-II |

## Con registro gratis
| Recurso | Env |
|---------|-----|
| **NASA FIRMS** | `FIRMS_MAP_KEY` — job seed **disabled** hasta configurar |

## Topografía
El relieve que viste es **DEM Terrarium** (elevación global open). GIBS aporta imagen satelital de fondo, no un segundo DEM.

## Más capas GIBS interesantes (extender UI)
- `MODIS_Terra_CorrectedReflectance_TrueColor`
- `Coastlines`
- `Reference_Features`
Ver: https://wiki.earthdata.nasa.gov/display/GIBS

FIRMS MAP_KEY: https://firms.modaps.eosdis.nasa.gov/api/map_key
