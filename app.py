"""Phase 4 — Streamlit dashboard. Reads only precomputed files from
data/processed/ and data/outputs/; never calls a routing engine or rebuilds
a graph at load time (see config.md and src/routing.py for how those files
are produced ahead of time, and src/pipeline_phase2.py / pipeline_phase3.py
for how to regenerate them).

Run with: streamlit run app.py
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st

from src import metrics, routing
from src.config import load_config

st.set_page_config(page_title="Golden Hour — Acceso a salud resolutiva", layout="wide")

cfg = load_config()


# ---------------------------------------------------------------- loaders --

@st.cache_data
def load_districts() -> gpd.GeoDataFrame:
    return gpd.read_parquet(cfg.path("processed_dir") / "districts_3depts.parquet")


@st.cache_data
def load_facilities() -> gpd.GeoDataFrame:
    return gpd.read_parquet(cfg.path("processed_dir") / "renipress_clean_3depts.parquet")


@st.cache_data
def load_demand_points() -> gpd.GeoDataFrame:
    return gpd.read_parquet(cfg.path("processed_dir") / "demand_points_sampled_3depts.parquet")


@st.cache_data
def load_data_quality_report() -> pd.DataFrame:
    return pd.read_csv(cfg.path("outputs_dir") / "data_quality_report.csv")


@st.cache_data
def load_access_by_district() -> pd.DataFrame:
    return pd.read_csv(cfg.path("outputs_dir") / "access_by_district.csv", dtype={"ubigeo": str})


@st.cache_data
def load_critical_gaps() -> pd.DataFrame:
    return pd.read_csv(cfg.path("outputs_dir") / "critical_gap_ranking.csv", dtype={"ubigeo": str})


@st.cache_data
def load_coverage_bands() -> pd.DataFrame:
    return pd.read_csv(cfg.path("outputs_dir") / "coverage_bands.csv")


@st.cache_data
def load_urban_rural_contrast() -> pd.DataFrame:
    return pd.read_csv(cfg.path("outputs_dir") / "urban_rural_contrast.csv")


@st.cache_data
def load_access_df() -> pd.DataFrame:
    """Point-level access_df, rebuilt from cached files (not re-routed) —
    the same join pipeline_phase3.build_access_dataset does, available
    here for the histogram/ECDF view and the scenario simulator."""
    demand = load_demand_points()
    parts = []
    for department in cfg.department_names:
        path = routing.cache_path(department, "car", "nearest")
        if path.exists():
            parts.append(pd.read_parquet(path))
    if not parts:
        return pd.DataFrame()
    nearest_car = pd.concat(parts).set_index("demand_id")
    access = demand.join(nearest_car, how="left")
    return metrics.access_time_by_point(access.reset_index().rename(columns={"index": "demand_id"}))


@st.cache_data
def load_car_matrix(department: str) -> pd.DataFrame | None:
    path = routing.cache_path(department, "car", "matrix")
    return pd.read_parquet(path) if path.exists() else None


# ------------------------------------------------------------------ guard --

districts = load_districts()
facilities = load_facilities()
try:
    access_by_district = load_access_by_district()
except FileNotFoundError:
    st.error(
        "Todavía no existen las tablas de la Fase 3 en data/outputs/. "
        "Corre `python -m src.pipeline_phase2` y luego `python -m src.pipeline_phase3` primero."
    )
    st.stop()

departments_ready = sorted(access_by_district.merge(
    districts[["IDDIST", "NOMBDEP"]], left_on="ubigeo", right_on="IDDIST", how="left"
)["NOMBDEP"].dropna().unique())
# NOMBDEP comes from the boundaries file in UPPERCASE ("CUSCO"); config.md's
# department_names are Title Case ("Cusco"). Compare case-insensitively --
# a literal set difference here is non-empty for every department, always,
# and used to show a stale "Fase 2 en curso" caption even once every
# department was long done.
departments_ready_upper = {d.upper() for d in departments_ready}

# ----------------------------------------------------------------- sidebar --

st.sidebar.header("Filtros")
selected_depts = st.sidebar.multiselect("Departamento", cfg.department_names, default=cfg.department_names)
if not departments_ready:
    st.sidebar.warning("Ningún departamento tiene resultados de la Fase 3 todavía.")
elif {d.upper() for d in selected_depts} - departments_ready_upper:
    st.sidebar.caption(f"Con datos listos: {', '.join(departments_ready)}. El resto se completará al terminar la Fase 2.")

provinces_available = sorted(facilities.loc[facilities["department"].str.title().isin(selected_depts), "province"].dropna().unique())
selected_provinces = st.sidebar.multiselect("Provincia", provinces_available, default=[])

categories_available = sorted(facilities["category"].dropna().unique())
selected_categories = st.sidebar.multiselect("Categoría de establecimiento", categories_available, default=categories_available)

institutions_available = sorted(facilities["institution"].dropna().unique())
selected_institutions = st.sidebar.multiselect("Institución", institutions_available, default=institutions_available)

time_threshold = st.sidebar.slider(
    "Umbral de tiempo de acceso (min)", min_value=10, max_value=180,
    value=cfg.dashboard["default_time_threshold_minutes"], step=5,
)

st.title("Golden Hour: acceso vial a salud resolutiva")
st.caption(f"Departamentos en alcance: {', '.join(cfg.department_names)} · Motor de ruteo: {cfg.routing['engine']}")

if not selected_depts:
    st.warning("Selecciona al menos un departamento en la barra lateral.")
    st.stop()

# Filtered slices used throughout the page
dist_upper = {d.upper() for d in selected_depts}
districts_f = districts[districts["NOMBDEP"].str.upper().isin(dist_upper)]
if selected_provinces:
    districts_f = districts_f[districts_f["NOMBPROV"].isin(selected_provinces)]

facilities_f = facilities[
    facilities["department"].str.upper().isin(dist_upper)
    & facilities["category"].isin(selected_categories)
    & facilities["institution"].isin(selected_institutions)
]
if selected_provinces:
    facilities_f = facilities_f[facilities_f["province"].isin(selected_provinces)]

access_by_district_f = access_by_district[access_by_district["ubigeo"].isin(districts_f["IDDIST"])]

access_df = load_access_df()
if not access_df.empty:
    access_df_f = access_df[access_df["department"].str.upper().isin(dist_upper)]
    if selected_provinces:
        access_df_f = access_df_f[access_df_f["province"].isin(selected_provinces)]
else:
    access_df_f = access_df


# --------------------------------------------------------------- KPI header --

st.subheader("Indicadores clave")
if access_df_f.empty:
    st.info("Sin datos de acceso todavía para los departamentos seleccionados.")
else:
    total_pop = access_df_f["population_est"].sum()
    pop_beyond_threshold = access_df_f.loc[
        access_df_f["t_min"].isna() | (access_df_f["t_min"] > time_threshold), "population_est"
    ].sum()
    median_access = access_df_f["t_min"].median()
    worst_row = access_by_district_f.sort_values("population_weighted_mean_t_min", ascending=False).head(1)
    worst_district_name = "—"
    if not worst_row.empty:
        match = districts_f[districts_f["IDDIST"] == worst_row.iloc[0]["ubigeo"]]
        if not match.empty:
            worst_district_name = f"{match.iloc[0]['NOMBDIST']} ({worst_row.iloc[0]['population_weighted_mean_t_min']:.0f} min)"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Población en alcance", f"{total_pop:,.0f}")
    c2.metric(f"Población a más de {time_threshold} min (o sin ruta)", f"{pop_beyond_threshold:,.0f}", f"{100*pop_beyond_threshold/total_pop:.1f}%" if total_pop else None)
    c3.metric("Peor distrito (acceso ponderado)", worst_district_name)
    c4.metric("Mediana de acceso (min)", f"{median_access:.1f}" if pd.notna(median_access) else "—")


# ------------------------------------------------------------- choropleth --

st.subheader("Mapa: tiempo de acceso ponderado por población, por distrito")
map_df = districts_f.merge(access_by_district_f, left_on="IDDIST", right_on="ubigeo", how="left")
if map_df["population_weighted_mean_t_min"].notna().any():
    minx, miny, maxx, maxy = map_df.total_bounds
    map_center = {"lat": (miny + maxy) / 2, "lon": (minx + maxx) / 2}
    map_zoom = 8 if max(maxx - minx, maxy - miny) < 2 else 5.5  # tighter zoom for one department vs all three

    fig_map = px.choropleth_map(
        map_df,
        geojson=map_df.geometry.__geo_interface__,
        locations=map_df.index,
        color="population_weighted_mean_t_min",
        hover_name="NOMBDIST",
        hover_data={"NOMBPROV": True, "total_population": ":,.0f", "population_weighted_mean_t_min": ":.1f"},
        color_continuous_scale="OrRd",
        map_style="carto-positron",
        center=map_center,
        zoom=map_zoom,
        opacity=0.75,
        labels={"population_weighted_mean_t_min": "Acceso (min)"},
    )
    fig_map.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=500)
    st.plotly_chart(fig_map, width="stretch")
else:
    st.info("Sin resultados de acceso todavía para los distritos filtrados.")


# ---------------------------------------------------------------- facilities --

st.subheader("Establecimientos de salud")
show_resolutive = st.checkbox("Mostrar resolutivos", value=True)
show_non_resolutive = st.checkbox("Mostrar no resolutivos", value=True)
layer_mask = pd.Series(False, index=facilities_f.index)
if show_resolutive:
    layer_mask |= facilities_f["is_resolutive"]
if show_non_resolutive:
    layer_mask |= ~facilities_f["is_resolutive"]
facilities_show = facilities_f[layer_mask & facilities_f["has_valid_coords"]]

if facilities_show.empty:
    st.info("Sin establecimientos que coincidan con los filtros.")
else:
    fac_minx, fac_miny, fac_maxx, fac_maxy = facilities_show.total_bounds
    fac_center = {"lat": (fac_miny + fac_maxy) / 2, "lon": (fac_minx + fac_maxx) / 2}
    fac_zoom = 8 if max(fac_maxx - fac_minx, fac_maxy - fac_miny) < 2 else 5.5

    fig_fac = px.scatter_map(
        facilities_show,
        lat=facilities_show.geometry.y,
        lon=facilities_show.geometry.x,
        color="is_resolutive",
        hover_name="facility_name",
        hover_data={"category": True, "institution": True, "province": True},
        color_discrete_map={True: "#2ca02c", False: "#7f7f7f"},
        labels={"is_resolutive": "Resolutivo"},
        map_style="carto-positron",
        center=fac_center,
        zoom=fac_zoom,
        height=450,
    )
    fig_fac.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(fig_fac, width="stretch")
st.caption(f"{len(facilities_show)} establecimientos mostrados de {len(facilities_f)} en el filtro actual.")


# ------------------------------------------------------------- distribution --

st.subheader("Distribución del tiempo de acceso")
if access_df_f.empty:
    st.info("Sin datos todavía.")
else:
    split_by = st.radio("Separar por", ["Departamento", "Urbano/Rural"], horizontal=True)
    color_col = "department" if split_by == "Departamento" else "is_urban"
    fig_hist = px.histogram(
        access_df_f.dropna(subset=["t_min"]), x="t_min", color=color_col,
        marginal="box", nbins=40, labels={"t_min": "Tiempo de acceso (min)"},
    )
    st.plotly_chart(fig_hist, width="stretch")


# ------------------------------------------------------------------ ranking --

st.subheader("Distritos con peor acceso")
gaps_f = load_critical_gaps()
gaps_f = gaps_f[gaps_f["ubigeo"].isin(districts_f["IDDIST"])].sort_values(
    "population_weighted_mean_t_min", ascending=False
)
st.dataframe(gaps_f, width="stretch")
st.download_button(
    "Descargar ranking (CSV)", gaps_f.to_csv(index=False).encode("utf-8"),
    file_name="critical_gap_ranking.csv", mime="text/csv",
)


# ---------------------------------------------------------- scenario simulator --

st.subheader("Simulador de escenario: elevar establecimientos I-3/I-4 a resolutivos")
st.caption(
    "Selecciona uno o más establecimientos actualmente I-3/I-4 y calcula la ganancia marginal "
    "de población cubierta (auto, umbral seleccionado en la barra lateral), usando la matriz "
    "completa ya precomputada — no se vuelve a rutear en vivo."
)

upgradeable_cats = cfg.dashboard["simulator_upgradeable_categories"]
sim_department = st.selectbox("Departamento para simular", [d for d in selected_depts if d.upper() in departments_ready_upper] or selected_depts)
candidates = facilities[
    (facilities["department"].str.upper() == sim_department.upper())
    & facilities["category"].isin(upgradeable_cats)
    & facilities["has_valid_coords"]
]
candidate_labels = candidates["facility_name"] + " (" + candidates["category"] + ", " + candidates["district"] + ")"
selected_upgrade_idx = st.multiselect(
    "Establecimientos a elevar a resolutivos", options=candidates.index, format_func=lambda i: candidate_labels.loc[i]
)

car_matrix = load_car_matrix(sim_department)
if car_matrix is None:
    st.info(f"Todavía no hay matriz car precomputada para {sim_department} (Fase 2 en curso).")
elif not selected_upgrade_idx:
    st.caption("Selecciona al menos un establecimiento para ver el efecto.")
else:
    demand = load_demand_points()
    demand_dept = demand[demand["department"].str.upper() == sim_department.upper()]

    # The stored matrix already routes to resolutive facilities AND I-3/I-4
    # candidates (src/pipeline_phase2.py) precisely so this simulator can
    # recompute coverage without re-routing live. Baseline = resolutive
    # rows only; scenario = baseline + whichever candidates got selected.
    baseline_matrix = car_matrix[car_matrix["facility_is_resolutive"]]
    baseline_nearest = routing.nearest_facility(baseline_matrix, origin_id_col="demand_id")
    baseline_covered = baseline_nearest[baseline_nearest["duration_min"] <= time_threshold]
    baseline_pop_covered = demand_dept.loc[demand_dept.index.isin(baseline_covered["demand_id"])]["population_est"].sum()

    upgraded_in_matrix = car_matrix["facility_id"].isin(selected_upgrade_idx)
    if not upgraded_in_matrix.any():
        st.warning(
            "Los establecimientos seleccionados no están en la matriz precomputada — probablemente "
            "fallaron el snapping a la red vial en la Fase 2. Prueba con otro establecimiento."
        )
    else:
        scenario_matrix = pd.concat([baseline_matrix, car_matrix[upgraded_in_matrix]])
        scenario_nearest = routing.nearest_facility(scenario_matrix, origin_id_col="demand_id")
        scenario_covered = scenario_nearest[scenario_nearest["duration_min"] <= time_threshold]
        scenario_pop_covered = demand_dept.loc[demand_dept.index.isin(scenario_covered["demand_id"])]["population_est"].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Población cubierta (actual)", f"{baseline_pop_covered:,.0f}")
        c2.metric("Población cubierta (escenario)", f"{scenario_pop_covered:,.0f}")
        c3.metric("Ganancia marginal", f"{scenario_pop_covered - baseline_pop_covered:,.0f}")


# ---------------------------------------------------------- facility siting --

st.subheader("Innovación: recomendación de ubicación (Maximal Covering Location)")
st.caption(
    "En vez de elegir manualmente qué establecimiento simular, este algoritmo voraz (greedy MCLP) "
    "recorre TODOS los candidatos I-3/I-4 y responde: de uno en uno, ¿cuál agrega más población nueva "
    "cubierta dentro del umbral? Reutiliza la matriz de la Fase 2 — no se vuelve a rutear en vivo."
)
try:
    siting = pd.read_csv(cfg.path("outputs_dir") / "facility_siting_recommendations.csv")
    siting_f = siting[siting["department"].str.upper().isin(dist_upper)]
    if siting_f.empty:
        st.info("Sin recomendaciones para los departamentos seleccionados.")
    else:
        st.dataframe(
            siting_f[["department", "facility_name", "category", "district", "institution", "marginal_population_gained", "cumulative_gain_over_baseline"]],
            use_container_width=True,
        )
        fig_siting = px.bar(
            siting_f, x="facility_name", y="marginal_population_gained", color="department",
            labels={"facility_name": "Establecimiento", "marginal_population_gained": "Ganancia marginal de población"},
            title="Ganancia marginal de población por establecimiento recomendado",
        )
        st.plotly_chart(fig_siting, use_container_width=True)
except FileNotFoundError:
    st.info("Corre `python -m src.pipeline_phase3` para generar las recomendaciones de siting.")


# ------------------------------------------------------------ data quality --

st.subheader("Panel de calidad de datos (Fase 1)")
dq = load_data_quality_report()
st.dataframe(dq, width="stretch")
