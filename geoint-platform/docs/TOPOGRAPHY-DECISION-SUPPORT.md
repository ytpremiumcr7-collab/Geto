# DEM / LOS — decision-support grade (not safety-of-life certification)

## Scope

This platform produces **decision-support** terrain products with explicit:

- horizontal / vertical uncertainty estimates
- confidence score (0–1)
- lineage (CRS, vertical datum, refraction model)
- **certification disclaimer** on every response `quality` object

It does **not** produce ICAO/FAA procedure design, IFR, or weapons-employment certified products.

## Grades

| Grade | Meaning |
|-------|---------|
| `exploratory` | Visual / rough planning; high uncertainty |
| `operational_support` | Suitable to *inform* operators who carry uncertainty forward |
| `not_for_safety_of_life` | Binding label in certification string; never override to “certified” |

## LOS engineering controls

1. Densified profile at `sample_distance_m`
2. Optional **effective-Earth** curvature with `refraction_k` (default **4/3**)
3. First obstruction distance + profile
4. `quality` block from `app/topography/quality.py` using DEM GSD class

## Operator checklist

1. Register survey-grade COG when available (not only Terrarium 30 m)
2. Record vertical datum in DEM asset metadata
3. Set `sample_distance_m` ≤ DEM GSD
4. Prefer `refraction_k=1.333` for operational_support grade
5. Do **not** strip the `quality.certification` field in downstream clients

## API

LOS/viewshed JSON includes `quality: { decision_grade, horizontal_uncertainty_m, vertical_uncertainty_m, confidence_0_1, ... }`.

## GSD and vertical datum (enforced)

- Registering a DEM **requires** non-empty `vertical_datum` and positive `resolution_m` (GSD).
- LOS `sample_distance_m` is **clamped to ≤ GSD**; responses include `sample_clamped_to_gsd`.
- Clients **must** display `quality.certification` (TopographyPanel does; do not remove).

