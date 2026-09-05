"""Phase 3 orchestration: join Phase 2's routing outputs with the sampled
demand points, compute every metric in src/metrics.py, and export the
resulting tables to data/outputs/ (CSV, ready for the LaTeX report and the
Streamlit dashboard).

Run with: python -m src.pipeline_phase3
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")

from src import metrics, routing
from src.config import load_config
from src.export import save_figure
from src.logging_utils import get_logger

logger = get_logger("pipeline_phase3")


def generate_figures(coverage: pd.DataFrame, lorenz: pd.DataFrame, gini: float, department_access: pd.DataFrame, urban_rural: pd.DataFrame) -> None:
    """Every figure the LaTeX report embeds is generated here from the same
    tables exported to data/outputs/ — never a dashboard screenshot."""
    fig, ax = plt.subplots(figsize=(6, 4))
    bands = coverage[coverage["band"] != "unroutable"]
    ax.bar(bands["band"], bands["share"] * 100, color="#c0392b")
    ax.set_ylabel("% de la población")
    ax.set_xlabel("Tiempo de acceso en auto a instalación resolutiva")
    ax.set_title("Cobertura poblacional por banda de tiempo de acceso")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    save_figure(fig, "fig_coverage_bands")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(lorenz["cum_population_share"], lorenz["cum_access_time_share"], color="#c0392b", label="Curva de Lorenz observada")
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Igualdad perfecta")
    ax.set_xlabel("Proporción acumulada de población")
    ax.set_ylabel("Proporción acumulada de tiempo de acceso")
    ax.set_title(f"Desigualdad de acceso (Gini = {gini:.3f})")
    ax.legend()
    plt.tight_layout()
    save_figure(fig, "fig_lorenz_curve")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(department_access["department"], department_access["population_weighted_mean_t_min"], color="#2c3e50")
    ax.set_ylabel("Minutos (ponderado por población)")
    ax.set_title("Tiempo de acceso promedio por departamento")
    plt.tight_layout()
    save_figure(fig, "fig_access_by_department")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 4))
    labels = urban_rural["is_urban"].map({True: "Urbano", False: "Rural"})
    ax.bar(labels, urban_rural["population_weighted_mean_t_min"], color=["#27ae60", "#e67e22"])
    ax.set_ylabel("Minutos (ponderado por población)")
    ax.set_title("Tiempo de acceso: urbano vs. rural")
    plt.tight_layout()
    save_figure(fig, "fig_urban_rural_contrast")
    plt.close(fig)

    logger.info("Figuras escritas en report/figures/")


def build_access_dataset(departments: list[str] | None = None) -> pd.DataFrame:
    """Join the sampled demand points (population_est, is_urban, ubigeo,
    department, province) with each department's car-profile nearest-facility
    result, into one access_df. Departments whose car routing isn't done yet
    are skipped with a warning (Phase 2 may still be running) rather than
    crashing — pass `departments` explicitly to force a specific subset."""
    cfg = load_config()
    demand = pd.read_parquet(cfg.path("processed_dir") / "demand_points_sampled_3depts.parquet")

    nearest_parts = []
    ready_departments = []
    for department in departments or cfg.department_names:
        path = routing.cache_path(department, "car", "nearest")
        if not path.exists():
            logger.warning("%s: sin resultados car todavía (Fase 2 en curso o pendiente) — se omite por ahora", department)
            continue
        nearest_parts.append(pd.read_parquet(path))
        ready_departments.append(department)

    if not nearest_parts:
        raise RuntimeError("Ningún departamento tiene resultados de ruteo car todavía — corre src.pipeline_phase2 primero")
    logger.info("Departamentos con datos car disponibles: %s", ready_departments)

    nearest_car = pd.concat(nearest_parts, ignore_index=False).set_index("demand_id")
    demand = demand[demand["department"].str.upper().isin({d.upper() for d in ready_departments})]

    access_df = demand.join(nearest_car, how="left")
    access_df = metrics.access_time_by_point(access_df.reset_index().rename(columns={"index": "demand_id"}))
    return access_df


def _haversine_m(lat1, lon1, lat2, lon2):
    import numpy as np

    r = 6_371_000.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def build_straight_line_vs_network() -> pd.DataFrame:
    """For every routable demand point, compare the network-routed distance
    (nearest resolutive facility, car) against the Haversine straight-line
    distance between the same two points — the detour factor the
    assignment's Phase 2/5 explicitly asks for, instead of assuming one."""
    import geopandas as gpd

    cfg = load_config()
    demand = gpd.read_parquet(cfg.path("processed_dir") / "demand_points_sampled_3depts.parquet")
    facilities = gpd.read_parquet(cfg.path("processed_dir") / "renipress_clean_3depts.parquet")

    parts = []
    for department in cfg.department_names:
        path = routing.cache_path(department, "car", "nearest")
        if path.exists():
            parts.append(pd.read_parquet(path))
    if not parts:
        return pd.DataFrame()
    nearest_car = pd.concat(parts, ignore_index=False)
    routable = nearest_car[nearest_car["routable"]].copy()

    demand_coords = demand.geometry
    routable["demand_lat"] = routable["demand_id"].map(demand_coords.y)
    routable["demand_lon"] = routable["demand_id"].map(demand_coords.x)
    facility_coords = facilities.geometry
    routable["facility_lat"] = routable["facility_id"].map(facility_coords.y)
    routable["facility_lon"] = routable["facility_id"].map(facility_coords.x)

    routable["straight_line_m"] = _haversine_m(
        routable["demand_lat"], routable["demand_lon"], routable["facility_lat"], routable["facility_lon"]
    )
    routable["detour_factor"] = routable["distance_m"] / routable["straight_line_m"].replace(0, pd.NA)
    return routable[["demand_id", "facility_id", "distance_m", "straight_line_m", "detour_factor"]]


def build_cross_mode_dataset() -> pd.DataFrame:
    """For every sampled demand point: t_min by car, foot, and bike to the
    nearest RESOLUTIVE facility (nearest-only, not the full matrix — see
    src/routing.py for why the full matrix is only built for car). A
    department is included only once car+foot+bike are all done."""
    cfg = load_config()
    parts = []
    for department in cfg.department_names:
        paths = {p: routing.cache_path(department, p, "nearest") for p in ("car", "foot", "bike")}
        if not all(p.exists() for p in paths.values()):
            logger.warning("%s: ruteo cross-modo incompleto todavía (car/foot/bike) — se omite por ahora", department)
            continue
        car = pd.read_parquet(paths["car"])[["demand_id", "duration_min", "routable"]]
        car = car.rename(columns={"duration_min": "t_min_car", "routable": "routable_car"})
        foot = pd.read_parquet(paths["foot"]).rename(columns={"duration_min": "t_min_foot", "routable": "routable_foot"})
        bike = pd.read_parquet(paths["bike"]).rename(columns={"duration_min": "t_min_bike", "routable": "routable_bike"})
        merged = car.merge(foot, on="demand_id", how="outer").merge(bike, on="demand_id", how="outer")
        merged["department"] = department
        parts.append(merged)
    if not parts:
        logger.warning("build_cross_mode_dataset: ningún departamento con car+foot+bike completos todavía")
        return pd.DataFrame(columns=["demand_id", "t_min_car", "routable_car", "t_min_foot", "routable_foot", "t_min_bike", "routable_bike", "department"])
    return pd.concat(parts, ignore_index=True)


def build_urban_walk_any_dataset() -> pd.DataFrame:
    """Urban demand points only: t_min on foot to the nearest facility of
    ANY category (not just resolutive) — per the assignment's Phase 2
    requirement, distinct from the resolutive-only comparisons above."""
    cfg = load_config()
    parts = []
    for department in cfg.department_names:
        path = routing.cache_path(department, "foot_any", "nearest")
        if not path.exists():
            logger.warning("%s: sin resultados foot_any todavía — se omite por ahora", department)
            continue
        part = pd.read_parquet(path)
        part["department"] = department
        parts.append(part)
    if not parts:
        return pd.DataFrame(columns=["demand_id", "duration_min", "routable", "department"])
    return pd.concat(parts, ignore_index=True)


def run() -> None:
    cfg = load_config()
    from src.export import df_to_latex_table

    logger.info("Construyendo access_df (demanda x tiempo de acceso en auto a instalación resolutiva más cercana)...")
    access_df = build_access_dataset()
    logger.info("access_df: %d puntos de demanda", len(access_df))

    outputs_dir = cfg.path("outputs_dir")

    coverage = metrics.coverage_bands(access_df)
    coverage.to_csv(outputs_dir / "coverage_bands.csv", index=False)
    logger.info("coverage_bands:\n%s", coverage.to_string(index=False))

    district_access = metrics.population_weighted_mean_access(access_df, group_by="ubigeo")
    district_access.to_csv(outputs_dir / "access_by_district.csv", index=False)

    province_access = metrics.population_weighted_mean_access(access_df, group_by="province")
    province_access.to_csv(outputs_dir / "access_by_province.csv", index=False)

    department_access = metrics.population_weighted_mean_access(access_df, group_by="department")
    department_access.to_csv(outputs_dir / "access_by_department.csv", index=False)
    logger.info("access_by_department:\n%s", department_access.to_string(index=False))

    # district_access needs department/province names attached for a readable ranking table
    district_lookup = access_df[["ubigeo", "department", "province"]].drop_duplicates(subset="ubigeo")
    district_access_named = district_access.merge(district_lookup, on="ubigeo", how="left")
    critical_gaps = metrics.critical_gap_ranking(district_access_named, top_n=20)
    critical_gaps.to_csv(outputs_dir / "critical_gap_ranking.csv", index=False)
    logger.info("Peores 5 distritos:\n%s", critical_gaps.head(5).to_string(index=False))

    gini = metrics.gini_of_access(access_df)
    lorenz = metrics.lorenz_curve(access_df)
    lorenz.to_csv(outputs_dir / "lorenz_curve.csv", index=False)
    logger.info("Gini de acceso (ponderado por población): %.4f", gini)
    (outputs_dir / "gini_coefficient.txt").write_text(f"{gini:.6f}\n", encoding="utf-8")

    urban_rural = metrics.urban_rural_contrast(access_df)
    urban_rural.to_csv(outputs_dir / "urban_rural_contrast.csv", index=False)
    logger.info("urban_rural_contrast:\n%s", urban_rural.to_string(index=False))

    generate_figures(coverage, lorenz, gini, department_access, urban_rural)

    rurality = metrics.district_rurality(access_df)
    cross_analysis = metrics.access_vs_secondary_dimension(district_access_named, rurality, secondary_col="pct_rural")
    cross_analysis.to_csv(outputs_dir / "access_vs_rurality.csv", index=False)
    corr = cross_analysis[["population_weighted_mean_t_min", "pct_rural"]].corr().iloc[0, 1]
    logger.info("Correlación (Pearson) access_time vs %% rural por distrito: %.3f", corr)

    logger.info("Construyendo comparación línea recta vs. red vial...")
    straight_vs_network = build_straight_line_vs_network()
    if not straight_vs_network.empty:
        straight_vs_network.to_csv(outputs_dir / "straight_line_vs_network.csv", index=False)
        median_detour = straight_vs_network["detour_factor"].median()
        logger.info(
            "Factor de desvío (distancia red / línea recta): mediana=%.2fx, p90=%.2fx (n=%d)",
            median_detour, straight_vs_network["detour_factor"].quantile(0.9), len(straight_vs_network),
        )

    logger.info("Construyendo comparación cross-modo (car/foot/bike)...")
    cross_mode = build_cross_mode_dataset()
    cross_mode.to_csv(outputs_dir / "cross_mode_comparison.csv", index=False)
    both_routable = cross_mode.dropna(subset=["t_min_car", "t_min_foot"])
    if len(both_routable):
        ratio = (both_routable["t_min_foot"] / both_routable["t_min_car"]).median()
        logger.info(
            "Cross-modo: %d/%d puntos con car Y foot alcanzables; mediana t_foot/t_car = %.1fx",
            len(both_routable), len(cross_mode), ratio,
        )

    logger.info("Construyendo dataset de caminata urbana a cualquier categoría...")
    urban_walk_any = build_urban_walk_any_dataset()
    urban_walk_any.to_csv(outputs_dir / "urban_walk_to_any_facility.csv", index=False)

    # LaTeX chokes on '_' outside math mode, so every table gets human labels
    # before df_to_latex_table -- not just cosmetic, it's what keeps the
    # report tables readable to someone who isn't reading the source code.
    display_cols = {
        "population_weighted_mean_t_min": "Acceso ponderado (min)",
        "total_population": "Población",
        "n_demand_points": "Puntos de demanda",
        "pct_population_unroutable": "\\% sin ruta",
        "department": "Departamento",
        "province": "Provincia",
        "band": "Banda de acceso",
        "population": "Población",
        "share": "\\% de población",
    }

    coverage_for_table = coverage.assign(share=lambda d: d["share"] * 100)
    df_to_latex_table(
        coverage_for_table.rename(columns=display_cols), "table_coverage_bands",
        caption="Cobertura poblacional por banda de tiempo de acceso (auto, instalación resolutiva más cercana)",
        label="tab:coverage-bands",
    )
    df_to_latex_table(
        critical_gaps.drop(columns=["ubigeo"]).head(15).rename(columns=display_cols),
        "table_critical_gaps",
        caption="Los 15 distritos con peor acceso ponderado por población",
        label="tab:critical-gaps",
    )
    df_to_latex_table(
        department_access.rename(columns=display_cols), "table_access_by_department",
        caption="Tiempo de acceso ponderado por población, por departamento",
        label="tab:access-by-department",
    )

    logger.info("Fase 3 completa. Tablas escritas en %s", outputs_dir)


if __name__ == "__main__":
    run()
