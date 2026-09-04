"""Phase 1 orchestration: download (if needed) -> filter to the 3
departments in config.md -> validate -> write cleaned GeoParquet to
data/processed/ + the data quality report to data/outputs/ and logs/.

Run with: python -m src.pipeline_phase1
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src import acquisition, validation
from src.config import load_config
from src.export import run_data_quality_report
from src.logging_utils import get_logger

logger = get_logger("pipeline_phase1")


def _to_geodataframe(df: pd.DataFrame) -> gpd.GeoDataFrame:
    geometry = [
        Point(lon, lat) if valid else None
        for lon, lat, valid in zip(df["lon"], df["lat"], df["has_valid_coords"])
    ]
    return gpd.GeoDataFrame(df, geometry=geometry, crs=4326)


def run(force_download: bool = False) -> dict[str, pd.DataFrame]:
    cfg = load_config()
    dept_names_upper = {d.upper() for d in cfg.department_names}
    logger.info("Ejecutando Fase 1 para: %s", cfg.department_names)

    acquisition.run_all(force=force_download)

    districts = gpd.read_file(cfg.path("raw_dir") / cfg.sources["admin_boundaries"]["local_raw_name"])
    districts_scope = districts[districts["NOMBDEP"].str.upper().isin(dept_names_upper)].copy()
    logger.info("Distritos en alcance: %d", len(districts_scope))

    # --- RENIPRESS (oferta) ---
    _, encoding_report = validation.check_encoding(
        cfg.path("raw_dir") / cfg.sources["renipress"]["local_raw_name"]
    )
    renipress = validation.load_renipress_raw()
    renipress_scope = renipress[renipress["department"].str.upper().isin(dept_names_upper)].copy()
    logger.info("Establecimientos RENIPRESS en alcance (antes de validar): %d", len(renipress_scope))

    renipress_clean, renipress_report_rows = validation.run_all_checks(renipress_scope, districts_scope)
    for row in renipress_report_rows:
        row["source"] = "renipress"
    encoding_report["source"] = "renipress"

    # --- SIGMED (demanda) ---
    sigmed = validation.load_sigmed_raw()
    sigmed_scope = sigmed[sigmed["department"].str.upper().isin(dept_names_upper)].copy()
    logger.info("Centros poblados SIGMED en alcance (antes de validar): %d", len(sigmed_scope))

    sigmed_report_rows = []
    sigmed_scope, _, r = validation.check_missing_coordinates(sigmed_scope)
    sigmed_report_rows.append(r)
    sigmed_scope, _, r = validation.check_out_of_bbox(sigmed_scope)
    sigmed_report_rows.append(r)
    sigmed_scope, _, r = validation.check_swapped_lat_lon(sigmed_scope)
    sigmed_report_rows.append(r)
    sigmed_scope, _, r = validation.check_district_containment(sigmed_scope, districts_scope)
    sigmed_report_rows.append(r)
    sigmed_clean, _, r = validation.check_duplicate_codes(sigmed_scope)
    sigmed_report_rows.append(r)
    for row in sigmed_report_rows:
        row["source"] = "sigmed"

    # --- Población distrital (Censo 2017 INEI) ---
    # Extraída una sola vez de PDF por scripts/extract_population_by_district.py
    # (ver config.md sources.population_census2017) — no forma parte del
    # pipeline de descarga regular, solo se concatena y valida aquí.
    pop_frames = []
    for dept_key, local_name in cfg.raw["sources"]["population_census2017"]["local_raw_names"].items():
        pop_path = cfg.path("raw_dir") / local_name
        pop_frames.append(pd.read_csv(pop_path, encoding="utf-8-sig", dtype={"ubigeo": str}))
    population = pd.concat(pop_frames, ignore_index=True)
    n_missing_ubigeo = int((population["ubigeo"].isna() | (population["ubigeo"] == "")).sum())
    logger.info(
        "Población distrital 2017 cargada: %d distritos (%d sin ubigeo — creados tras el corte de límites)",
        len(population), n_missing_ubigeo,
    )
    population_report_row = {
        "rule": "population_district_extraction",
        "source": "population_census2017",
        "n_districts": int(len(population)),
        "n_flagged": n_missing_ubigeo,
        "action": "kept with warning — population figure is used, ubigeo left blank rather than guessed",
        "why": "a handful of districts (e.g. Inkawasi, Megantoni in Cusco; Rosa Panduro, Yaguas in Loreto) were created/recognized after limites_distritales.geojson's cutoff, so they have no matching polygon to join against",
    }

    all_report_rows = [encoding_report] + renipress_report_rows + sigmed_report_rows + [population_report_row]
    report_df = run_data_quality_report(all_report_rows)
    logger.info("Reporte de calidad de datos: %d reglas evaluadas", len(report_df))

    renipress_gdf = _to_geodataframe(renipress_clean)
    sigmed_gdf = _to_geodataframe(sigmed_clean)

    renipress_out = cfg.path("processed_dir") / "renipress_clean_3depts.parquet"
    sigmed_out = cfg.path("processed_dir") / "sigmed_demand_3depts.parquet"
    districts_out = cfg.path("processed_dir") / "districts_3depts.parquet"
    renipress_gdf.to_parquet(renipress_out)
    sigmed_gdf.to_parquet(sigmed_out)
    districts_scope.to_parquet(districts_out)
    logger.info("Escrito: %s (%d filas)", renipress_out, len(renipress_gdf))
    logger.info("Escrito: %s (%d filas)", sigmed_out, len(sigmed_gdf))
    logger.info("Escrito: %s (%d filas)", districts_out, len(districts_scope))

    population_out = cfg.path("processed_dir") / "population_by_district_3depts.parquet"
    population.to_parquet(population_out)
    logger.info("Escrito: %s (%d filas)", population_out, len(population))

    for dept in cfg.department_names:
        sub = renipress_gdf[renipress_gdf["department"].str.upper() == dept.upper()]
        n_resolutive = int(sub["is_resolutive"].sum())
        n_demand = len(sigmed_gdf[sigmed_gdf["department"].str.upper() == dept.upper()])
        logger.info(
            "%s: %d establecimientos (%d resolutivos) | %d centros poblados",
            dept, len(sub), n_resolutive, n_demand,
        )

    return {
        "renipress": renipress_gdf,
        "sigmed": sigmed_gdf,
        "districts": districts_scope,
        "population": population,
        "report": report_df,
    }


if __name__ == "__main__":
    run()
