"""Phase 2 orchestration: build OSMnx graphs (car/foot/bike) per department,
snap demand + supply points, compute the full car x resolutive-facility
matrix (needed by Phase 4's scenario simulator) and nearest-only
foot/bike distances for the cross-mode comparison.

Runs one profile at a time across ALL departments (car first, then foot,
then bike) rather than looping department-by-department through all three
profiles. Overpass has proven flaky mid-session (see config.md) — this
ordering guarantees the car matrices Phase 3/4 actually depend on land
first, instead of a slow/failing foot download for department 1 blocking
department 2 and 3's car results.

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


def _dept_slices(department, renipress, demand_sampled):
    dept_renipress = renipress[renipress["department"].str.upper() == department.upper()]
    dept_resolutive = dept_renipress[dept_renipress["is_resolutive"] & dept_renipress["has_valid_coords"]]
    dept_any_facility = dept_renipress[dept_renipress["has_valid_coords"]]
    dept_demand = demand_sampled[demand_sampled["department"].str.upper() == department.upper()]
    return dept_resolutive, dept_any_facility, dept_demand


def run_car(department, renipress, demand_sampled, districts, snap_reports, failures) -> None:
    cfg = load_config()
    dept_resolutive, _, dept_demand = _dept_slices(department, renipress, demand_sampled)

    # The full matrix routes to resolutive facilities AND to I-3/I-4
    # candidates (config.md dashboard.simulator_upgradeable_categories) —
    # not just the ones already resolutive. Without the candidates as real
    # destinations, the Phase 4 scenario simulator ("upgrade this I-3 to
    # resolutive, recompute coverage") has no distances to recompute with,
    # which defeats the entire point of precomputing a full matrix instead
    # of just nearest-facility distances.
    dept_renipress = renipress[renipress["department"].str.upper() == department.upper()]
    dept_upgrade_candidates = dept_renipress[
        dept_renipress["category"].isin(cfg.dashboard["simulator_upgradeable_categories"])
        & dept_renipress["has_valid_coords"]
    ]
    dept_all_facilities = pd.concat([dept_resolutive, dept_upgrade_candidates])

    try:
        car_matrix_path = routing.cache_path(department, "car", "matrix")
        if car_matrix_path.exists():
            logger.info("Matriz car en caché: %s", car_matrix_path)
        else:
            t0 = time.time()
            G_car = routing.build_graph(department, "car", districts)
            demand_nodes, demand_snap_report = routing.snap_points_to_graph(dept_demand, G_car)
            facility_nodes, facility_snap_report = routing.snap_points_to_graph(dept_all_facilities, G_car)
            snap_reports.append({"department": department, "profile": "car", "point_type": "demand", **demand_snap_report})
            snap_reports.append({"department": department, "profile": "car", "point_type": "resolutive_and_candidate_facility", **facility_snap_report})

            matrix = routing.full_matrix_from_facilities(
                G_car, demand_nodes, facility_nodes, origin_id_col="demand_id", facility_id_col="facility_id"
            )
            matrix["facility_is_resolutive"] = matrix["facility_id"].isin(dept_resolutive.index)
            logger.info(
                "%s: matriz car completa (%d demanda x %d instalaciones [%d resolutivas + %d candidatas I-3/I-4] = %d filas) en %.1fs",
                department, len(demand_nodes), len(facility_nodes), len(dept_resolutive), len(dept_upgrade_candidates), len(matrix), time.time() - t0,
            )
            matrix.to_parquet(car_matrix_path)

        car_matrix = pd.read_parquet(car_matrix_path)
        baseline_matrix = car_matrix[car_matrix["facility_is_resolutive"]]
        nearest_car = routing.nearest_facility(baseline_matrix, origin_id_col="demand_id")
        nearest_car.to_parquet(routing.cache_path(department, "car", "nearest"))
        n_routable = int(baseline_matrix.groupby("demand_id")["routable"].any().sum())
        logger.info(
            "%s (car): %d/%d puntos de demanda con al menos 1 instalación resolutiva alcanzable",
            department, n_routable, dept_demand.shape[0],
        )
    except Exception as e:
        logger.error("%s (car): FALLÓ, se continúa con el resto — %s", department, e)
        failures.append({"department": department, "profile": "car", "error": str(e)})


def run_foot(department, renipress, demand_sampled, districts, snap_reports, failures) -> None:
    dept_resolutive, dept_any_facility, dept_demand = _dept_slices(department, renipress, demand_sampled)
    try:
        foot_nearest_path = routing.cache_path(department, "foot", "nearest")
        foot_any_path = routing.cache_path(department, "foot_any", "nearest")
        if foot_nearest_path.exists() and foot_any_path.exists():
            logger.info("Resultados foot en caché para %s", department)
            return

        t0 = time.time()
        G_foot = routing.build_graph(department, "foot", districts)
        demand_nodes_foot, demand_snap_foot = routing.snap_points_to_graph(dept_demand, G_foot)
        resolutive_nodes_foot, resolutive_snap_foot = routing.snap_points_to_graph(dept_resolutive, G_foot)
        any_facility_nodes_foot, any_facility_snap_foot = routing.snap_points_to_graph(dept_any_facility, G_foot)
        snap_reports.append({"department": department, "profile": "foot", "point_type": "demand", **demand_snap_foot})
        snap_reports.append({"department": department, "profile": "foot", "point_type": "resolutive_facility", **resolutive_snap_foot})
        snap_reports.append({"department": department, "profile": "foot", "point_type": "any_facility", **any_facility_snap_foot})

        resolutive_source_nodes = resolutive_nodes_foot["node"].dropna().tolist()
        nearest_resolutive_times = routing.nearest_from_sources(G_foot, resolutive_source_nodes, weight="travel_time")
        foot_rows = [
            {
                "demand_id": demand_id,
                "duration_min": (nearest_resolutive_times.get(row["node"]) / 60.0) if pd.notna(row["node"]) and row["node"] in nearest_resolutive_times else None,
                "routable": pd.notna(row["node"]) and row["node"] in nearest_resolutive_times,
            }
            for demand_id, row in demand_nodes_foot.iterrows()
        ]
        pd.DataFrame(foot_rows).to_parquet(foot_nearest_path)

        urban_demand = dept_demand[dept_demand["is_urban"]]
        urban_nodes_foot = demand_nodes_foot.loc[demand_nodes_foot.index.isin(urban_demand.index)]
        any_source_nodes = any_facility_nodes_foot["node"].dropna().tolist()
        nearest_any_times = routing.nearest_from_sources(G_foot, any_source_nodes, weight="travel_time")
        foot_any_rows = [
            {
                "demand_id": demand_id,
                "duration_min": (nearest_any_times.get(row["node"]) / 60.0) if pd.notna(row["node"]) and row["node"] in nearest_any_times else None,
                "routable": pd.notna(row["node"]) and row["node"] in nearest_any_times,
            }
            for demand_id, row in urban_nodes_foot.iterrows()
        ]
        pd.DataFrame(foot_any_rows).to_parquet(foot_any_path)
        logger.info(
            "%s (foot): %d/%d demanda->resolutiva más cercana | %d/%d urbanos->cualquier categoría más cercana (%.1fs)",
            department,
            sum(1 for r in foot_rows if r["routable"]), len(foot_rows),
            sum(1 for r in foot_any_rows if r["routable"]), len(foot_any_rows),
            time.time() - t0,
        )
    except Exception as e:
        logger.error("%s (foot): FALLÓ, se continúa con el resto — %s", department, e)
        failures.append({"department": department, "profile": "foot", "error": str(e)})


def run_bike(department, renipress, demand_sampled, districts, snap_reports, failures) -> None:
    dept_resolutive, _, dept_demand = _dept_slices(department, renipress, demand_sampled)
    try:
        bike_nearest_path = routing.cache_path(department, "bike", "nearest")
        if bike_nearest_path.exists():
            logger.info("Resultados bike en caché para %s", department)
            return

        t0 = time.time()
        G_bike = routing.build_graph(department, "bike", districts)
        demand_nodes_bike, demand_snap_bike = routing.snap_points_to_graph(dept_demand, G_bike)
        resolutive_nodes_bike, resolutive_snap_bike = routing.snap_points_to_graph(dept_resolutive, G_bike)
        snap_reports.append({"department": department, "profile": "bike", "point_type": "demand", **demand_snap_bike})
        snap_reports.append({"department": department, "profile": "bike", "point_type": "resolutive_facility", **resolutive_snap_bike})

        resolutive_source_nodes = resolutive_nodes_bike["node"].dropna().tolist()
        nearest_bike_times = routing.nearest_from_sources(G_bike, resolutive_source_nodes, weight="travel_time")
        bike_rows = [
            {
                "demand_id": demand_id,
                "duration_min": (nearest_bike_times.get(row["node"]) / 60.0) if pd.notna(row["node"]) and row["node"] in nearest_bike_times else None,
                "routable": pd.notna(row["node"]) and row["node"] in nearest_bike_times,
            }
            for demand_id, row in demand_nodes_bike.iterrows()
        ]
        pd.DataFrame(bike_rows).to_parquet(bike_nearest_path)
        logger.info(
            "%s (bike): %d/%d demanda->resolutiva más cercana (%.1fs)",
            department, sum(1 for r in bike_rows if r["routable"]), len(bike_rows), time.time() - t0,
        )
    except Exception as e:
        logger.error("%s (bike): FALLÓ, se continúa con el resto — %s", department, e)
        failures.append({"department": department, "profile": "bike", "error": str(e)})


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

    logger.info("=" * 60)
    logger.info("PASADA 1/3: car (todos los departamentos)")
    for department in cfg.department_names:
        run_car(department, renipress, demand_sampled, districts, snap_reports, failures)

    logger.info("=" * 60)
    logger.info("PASADA 2/3: foot (todos los departamentos)")
    for department in cfg.department_names:
        run_foot(department, renipress, demand_sampled, districts, snap_reports, failures)

    logger.info("=" * 60)
    logger.info("PASADA 3/3: bike (todos los departamentos)")
    for department in cfg.department_names:
        run_bike(department, renipress, demand_sampled, districts, snap_reports, failures)

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
