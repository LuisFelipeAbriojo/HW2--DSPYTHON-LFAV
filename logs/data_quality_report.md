# Reporte de calidad de datos — Fase 1

## encoding

- **file**: C:\Users\labri\Documents\GitHub\HW2 DS-2026-II-LFAV\data\raw\renipress_raw.csv
- **candidates_tried**: ['utf-8', 'latin-1', 'cp1252']
- **encoding_used**: utf-8
- **failed_candidates**: []
- **action**: used first working encoding
- **source**: renipress

## missing_or_zero_coordinates

- **n_flagged**: 1175
- **pct_flagged**: 32.36
- **action**: kept in registry, excluded from nearest-facility geospatial computation
- **why**: a facility with no GPS fix cannot be routed to; dropping it would silently shrink the supply count instead of documenting the gap
- **source**: renipress

## out_of_peru_bbox

- **bbox**: {'lon_min': -81.4, 'lon_max': -68.6, 'lat_min': -18.4, 'lat_max': -0.04}
- **n_flagged**: 0
- **action**: kept in registry, excluded from nearest-facility geospatial computation
- **why**: a coordinate outside Peru is a data-entry error (typo, wrong CRS); no safe automatic correction exists
- **source**: renipress

## swapped_lat_lon

- **n_flagged**: 0
- **action**: none found — no correction applied
- **why**: lat/lon transposition is a common manual-entry error and is safely reversible: the swap is only applied when it moves the point INTO Peru's bbox
- **source**: renipress

## district_containment

- **n_checkable**: 2397
- **n_flagged**: 314
- **tolerance_m**: 500
- **n_districts_with_null_geometry_in_source**: 0
- **action**: kept with warning — the declared UBIGEO is trusted for filtering, the point is flagged as geometrically inconsistent
- **why**: RENIPRESS lets facilities self-report UBIGEO independently of their coordinates; a mismatch usually means one of the two was mistyped, and we cannot tell which without manual review. Separately, the admin-boundaries source itself has null geometry for a small number of districts nationally (data-quality issue in that source, not RENIPRESS) — their facilities are excluded from n_checkable.
- **source**: renipress

## duplicate_facility_codes

- **n_flagged**: 0
- **n_involved_rows**: 0
- **action**: dropped (kept first occurrence) — the only rule in this pipeline that removes rows
- **why**: a duplicated facility_code is definitionally the same IPRESS registered twice; counting it twice would inflate resolutive supply density
- **source**: renipress

## unclassified_category

- **n_flagged**: 1113
- **pct_flagged**: 30.65
- **action**: kept in registry, treated as non-resolutive (excluded from nearest-facility computation, same as I-1..I-4)
- **why**: RENIPRESS uses the literal string '0' for establishments SUSALUD has not yet classified; absent a real category we cannot assume resolutive capacity
- **source**: renipress

## missing_or_zero_coordinates

- **n_flagged**: 0
- **pct_flagged**: 0.0
- **action**: kept in registry, excluded from nearest-facility geospatial computation
- **why**: a facility with no GPS fix cannot be routed to; dropping it would silently shrink the supply count instead of documenting the gap
- **source**: sigmed

## out_of_peru_bbox

- **bbox**: {'lon_min': -81.4, 'lon_max': -68.6, 'lat_min': -18.4, 'lat_max': -0.04}
- **n_flagged**: 0
- **action**: kept in registry, excluded from nearest-facility geospatial computation
- **why**: a coordinate outside Peru is a data-entry error (typo, wrong CRS); no safe automatic correction exists
- **source**: sigmed

## swapped_lat_lon

- **n_flagged**: 0
- **action**: none found — no correction applied
- **why**: lat/lon transposition is a common manual-entry error and is safely reversible: the swap is only applied when it moves the point INTO Peru's bbox
- **source**: sigmed

## district_containment

- **n_checkable**: 20697
- **n_flagged**: 355
- **tolerance_m**: 500
- **n_districts_with_null_geometry_in_source**: 0
- **action**: kept with warning — the declared UBIGEO is trusted for filtering, the point is flagged as geometrically inconsistent
- **why**: RENIPRESS lets facilities self-report UBIGEO independently of their coordinates; a mismatch usually means one of the two was mistyped, and we cannot tell which without manual review. Separately, the admin-boundaries source itself has null geometry for a small number of districts nationally (data-quality issue in that source, not RENIPRESS) — their facilities are excluded from n_checkable.
- **source**: sigmed

## duplicate_facility_codes

- **n_flagged**: 0
- **n_involved_rows**: 0
- **action**: dropped (kept first occurrence) — the only rule in this pipeline that removes rows
- **why**: a duplicated facility_code is definitionally the same IPRESS registered twice; counting it twice would inflate resolutive supply density
- **source**: sigmed
