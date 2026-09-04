"""Phase 2 orchestration: build OSMnx graphs (car/foot/bike) per department,
snap demand + supply points, compute the full car x resolutive-facility
matrix (needed by Phase 4's scenario simulator) and nearest-only
foot/bike distances for the cross-mode comparison.

Run with: python -m src.pipeline_phase2
"""

from __future__ import annotations

import json
import time

import geopandas as gpd
import pandas as pd

from src import routing, sampling
from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("pipeline_phase2")


def _load_phase1_outputs():
    cfg = load_config()
    renipress = gpd.read_parquet(cfg.path("processed_dir") / "renipress_clean_3depts.parquet")
    sigmed = gpd.read_parquet(cfg.path("processed_dir") / "sigmed_demand_3depts.parquet")
    districts = gpd.read_parquet(cfg.path("processed_dir") / "districts_3depts.parquet")
    population = pd.read_parquet(cfg.path("processed_dir") / "population_by_district_3depts.parquet")
    return renipress, sigmed, districts, population


def prepare_demand_points(sigmed: gpd.GeoDataFrame, population: pd.DataFrame) -> gpd.GeoDataFrame:
    cfg = load_config()
    valid = sigmed[sigmed["has_valid_coords"]].copy()
    apportioned, n_missing = sampling.apportion_population_to_points(valid, population)
    apportioned = sampling.classify_urban(apportioned)
    logger.info(
        "Puntos de demanda con coordenadas válidas: %d (%d sin población distrital asignable)",
        len(apportioned), n_missing,
    )
    sampled = sampling.sample_demand_points(apportioned, cfg.routing["max_demand_points"], cfg.random_seed)
    logger.info(
        "Muestreo poblacional: %d/%d puntos de demanda retenidos (tope config.md routing.max_demand_points=%d)",
        len(sampled), len(apportioned), cfg.routing["max_demand_points"],
    )
    return sampled


def run_department(
    department: str,
    renipress: gpd.GeoDataFrame,
    demand_sampled: gpd.GeoDataFrame,
    districts: gpd.GeoDataFrame,
    snap_reports: list[dict],
    failures: list[dict],
) -> None:
    cfg = load_config()
    t_dept0 = time.time()
    logger.info("=" * 60)
    logger.info("Departamento: %s", department)

    dept_renipress = renipress[renipress["department"].str.upper() == department.upper()]
    dept_resolutive = dept_renipress[dept_renipress["is_resolutive"] & dept_renipress["has_valid_coords"]]
    dept_any_facility = dept_renipress[dept_renipress["has_valid_coords"]]
    dept_demand = demand_sampled[demand_sampled["department"].str.upper() == department.upper()]
    logger.info(
        "%s: %d establecimientos resolutivos, %d establecimientos (cualquier categoría), %d puntos de demanda muestreados",
        department, len(dept_resolutive), len(dept_any_facility), len(dept_demand),
    )

    # --- CAR: full matrix (needed by the Phase 4 scenario simulator) ---
    try:
        car_matrix_path = routing.cache_path(department, "car", "matrix")
        if car_matrix_path.exists():
            logger.info("Matriz car en caché: %s", car_matrix_path)
        else:
            G_car = routing.build_graph(department, "car", districts)
            demand_nodes, demand_snap_report = routing.snap_points_to_graph(dept_demand, G_car)
            facility_nodes, facility_snap_report = routing.snap_points_to_graph(dept_resolutive, G_car)
            snap_reports.append({"department": department, "profile": "car", "point_type": "demand", **demand_snap_report})
            snap_reports.append({"department": department, "profile": "car", "point_type": "resolutive_facility", **facility_snap_report})

            t0 = time.time()
            matrix = routing.full_matrix_from_facilities(
                G_car, demand_nodes, facility_nodes, origin_id_col="demand_id", facility_id_col="facility_id"
            )
            logger.info(
                "%s: matriz car completa (%d demanda x %d instalaciones = %d filas) en %.1fs",
                department, len(demand_nodes), len(facility_nodes), len(matrix), time.time() - t0,
            )
            matrix.to_parquet(car_matrix_path)

        car_matrix = pd.read_parquet(car_matrix_path)
        nearest_car = routing.nearest_facility(car_matrix, origin_id_col="demand_id")
        nearest_car_path = routing.cache_path(department, "car", "nearest")
        nearest_car.to_parquet(nearest_car_path)
        n_routable = int(car_matrix.groupby("demand_id")["routable"].any().sum())
        logger.info(
            "%s (car): %d/%d puntos de demanda con al menos 1 instalación resolutiva alcanzable",
            department, n_routable, dept_demand.shape[0],
        )
    except Exception as e:
        logger.error("%s (car): FALLÓ, se continúa con el resto — %s", department, e)
        failures.append({"department": department, "profile": "car", "error": str(e)})

    # --- FOOT: nearest resolutive (cross-mode) + nearest any-category (urban only) ---
    try:
        foot_nearest_path = routing.cache_path(department, "foot", "nearest")
        foot_any_path = routing.cache_path(department, "foot_any", "nearest")
        if foot_nearest_path.exists() and foot_any_path.exists():
            logger.info("Resultados foot en caché para %s", department)
        else:
            G_foot = routing.build_graph(department, "foot", districts)
            demand_nodes_foot, demand_snap_foot = routing.snap_points_to_graph(dept_demand, G_foot)
            resolutive_nodes_foot, resolutive_snap_foot = routing.snap_points_to_graph(dept_resolutive, G_foot)
            any_facility_nodes_foot, any_facility_snap_foot = routing.snap_points_to_graph(dept_any_facility, G_foot)
            snap_reports.append({"department": department, "profile": "foot", "point_type": "demand", **demand_snap_foot})
            snap_reports.append({"department": department, "profile": "foot", "point_type": "resolutive_facility", **resolutive_snap_foot})
            snap_reports.append({"department": department, "profile": "foot", "point_type": "any_facility", **any_facility_snap_foot})

            resolutive_source_nodes = resolutive_nodes_foot["node"].dropna().tolist()
            nearest_resolutive_times = routing.nearest_from_sources(G_foot, resolutive_source_nodes, weight="travel_time")
            foot_rows = []
            for demand_id, row in demand_nodes_foot.iterrows():
                node = row["node"]
                t = nearest_resolutive_times.get(node) if pd.notna(node) else None
                foot_rows.append({"demand_id": demand_id, "duration_min": (t / 60.0) if t is not None else None, "routable": t is not None})
            pd.DataFrame(foot_rows).to_parquet(foot_nearest_path)

            urban_demand = dept_demand[dept_demand["is_urban"]]
            urban_nodes_foot = demand_nodes_foot.loc[demand_nodes_foot.index.isin(urban_demand.index)]
            any_source_nodes = any_facility_nodes_foot["node"].dropna().tolist()
            nearest_any_times = routing.nearest_from_sources(G_foot, any_source_nodes, weight="travel_time")
            foot_any_rows = []
            for demand_id, row in urban_nodes_foot.iterrows():
                node = row["node"]
                t = nearest_any_times.get(node) if pd.notna(node) else None
                foot_any_rows.append({"demand_id": demand_id, "duration_min": (t / 60.0) if t is not None else None, "routable": t is not None})
            pd.DataFrame(foot_any_rows).to_parquet(foot_any_path)
            logger.info(
                "%s (foot): %d/%d demanda->resolutiva más cercana | %d/%d urbanos->cualquier categoría más cercana",
                department,
                sum(1 for r in foot_rows if r["routable"]), len(foot_rows),
                sum(1 for r in foot_any_rows if r["routable"]), len(foot_any_rows),
            )
    except Exception as e:
        logger.error("%s (foot): FALLÓ, se continúa con el resto — %s", department, e)
        failures.append({"department": department, "profile": "foot", "error": str(e)})

    # --- BIKE: nearest resolutive (cross-mode) ---
    try:
        bike_nearest_path = routing.cache_path(department, "bike", "nearest")
        if bike_nearest_path.exists():
            logger.info("Resultados bike en caché para %s", department)
        else:
            G_bike = routing.build_graph(department, "bike", districts)
            demand_nodes_bike, demand_snap_bike = routing.snap_points_to_graph(dept_demand, G_bike)
            resolutive_nodes_bike, resolutive_snap_bike = routing.snap_points_to_graph(dept_resolutive, G_bike)
            snap_reports.append({"department": department, "profile": "bike", "point_type": "demand", **demand_snap_bike})
            snap_reports.append({"department": department, "profile": "bike", "point_type": "resolutive_facility", **resolutive_snap_bike})

            resolutive_source_nodes = resolutive_nodes_bike["node"].dropna().tolist()
            nearest_bike_times = routing.nearest_from_sources(G_bike, resolutive_source_nodes, weight="travel_time")
            bike_rows = []
            for demand_id, row in demand_nodes_bike.iterrows():
                node = row["node"]
                t = nearest_bike_times.get(node) if pd.notna(node) else None
                bike_rows.append({"demand_id": demand_id, "duration_min": (t / 60.0) if t is not None else None, "routable": t is not None})
            pd.DataFrame(bike_rows).to_parquet(bike_nearest_path)
            logger.info("%s (bike): %d/%d demanda->resolutiva más cercana", department, sum(1 for r in bike_rows if r["routable"]), len(bike_rows))
    except Exception as e:
        logger.error("%s (bike): FALLÓ, se continúa con el resto — %s", department, e)
        failures.append({"department": department, "profile": "bike", "error": str(e)})

    logger.info("%s completo en %.1f min", department, (time.time() - t_dept0) / 60.0)


def run() -> None:
    cfg = load_config()
    t0 = time.time()
    renipress, sigmed, districts, population = _load_phase1_outputs()
    demand_sampled = prepare_demand_points(sigmed, population)

    demand_out = cfg.path("processed_dir") / "demand_points_sampled_3depts.parquet"
    demand_sampled.to_parquet(demand_out)
    logger.info("Escrito: %s (%d filas)", demand_out, len(demand_sampled))

    snap_reports: list[dict] = []
    failures: list[dict] = []
    for department in cfg.department_names:
        run_department(department, renipress, demand_sampled, districts, snap_reports, failures)

    snap_report_path = cfg.path("outputs_dir") / "snapping_report.json"
    snap_report_path.write_text(json.dumps(snap_reports, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte de snapping escrito en %s", snap_report_path)

    if failures:
        failures_path = cfg.path("outputs_dir") / "phase2_failures.json"
        failures_path.write_text(json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.warning(
            "%d departamento/perfil fallaron y quedaron pendientes (ver %s) — re-ejecutar el pipeline los reintenta sin recomputar lo ya cacheado",
            len(failures), failures_path,
        )
    logger.info("Fase 2 completa en %.1f min", (time.time() - t0) / 60.0)


if __name__ == "__main__":
    run()
