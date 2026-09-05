"""Phase 2 — routing engine: OSMnx + NetworkX, graphs downloaded live from
Overpass API via osmnx.graph_from_polygon() and cached to disk as GraphML
(see config.md for why not pyrosm-from-local-pbf, and not OSRM/Docker).

Every result is cached to data/processed/routing_matrix_<department>_<profile>.parquet;
re-running the pipeline must not recompute rows already on disk. Unroutable
origin/destination pairs (disconnected graph components) are marked
routable=False with NaN time/distance — never silently substituted with a
straight-line estimate.
"""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
import requests

from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("routing")

PROFILE_TO_NETWORK_TYPE = {"car": "drive", "foot": "walk", "bike": "bike"}

# Overpass API is a shared, rate-limited public service and occasionally
# drops connections (SSL EOF, 504 Gateway Timeout) or is entirely
# unreachable under load. OSMnx already retries within one
# graph_from_polygon() call for HTTP-level failures, but a raw connection
# error can still escape and crash the whole pipeline — so this wraps the
# call again with backoff AND, if the default instance stays down, fails
# over to public mirrors. Verified repeatedly on 2026-09-04 (last checked
# right before this pipeline run): overpass-api.de was unreachable
# (connection reset / SSL EOF on every attempt, for over an hour) while
# overpass.kumi.systems and overpass.osm.ch both responded normally — this
# is the "documented fallback" the assignment's Phase 2 asks for. Ordered
# with the two working mirrors first so a confirmed-down default instance
# doesn't burn retry time on every single department/profile.
OVERPASS_MIRRORS = (
    "https://overpass.kumi.systems/api",
    "https://overpass.osm.ch/api",
    "https://overpass-api.de/api",
)
OVERPASS_RETRY_DELAYS_S = (20, 45)  # per mirror, before moving to the next one


def _graph_from_polygon_with_retry(poly, network_type: str):
    last_error = None
    for mirror in OVERPASS_MIRRORS:
        ox.settings.overpass_url = mirror
        for attempt, delay in enumerate((0, *OVERPASS_RETRY_DELAYS_S)):
            if delay:
                logger.warning(
                    "Overpass (%s) falló (intento %d), reintentando en %ds: %s", mirror, attempt, delay, last_error
                )
                time.sleep(delay)
            try:
                G = ox.graph_from_polygon(poly, network_type=network_type, simplify=True)
                if mirror != OVERPASS_MIRRORS[0]:
                    logger.warning("Usando espejo Overpass de respaldo: %s", mirror)
                return G
            except (requests.exceptions.RequestException, ConnectionError) as e:
                last_error = e
        logger.warning("Espejo Overpass %s agotó sus reintentos, probando el siguiente", mirror)
    raise RuntimeError(f"Overpass falló en los {len(OVERPASS_MIRRORS)} espejos configurados") from last_error


def _configure_osmnx_cache() -> None:
    cfg = load_config()
    ox.settings.cache_folder = str(cfg.path("cache_dir") / "osmnx")
    # Verbose per-request Overpass logging is left ON: a walk-network query
    # for a whole department can involve many tiled sub-requests, and
    # Overpass has proven flaky mid-session (see config.md) — without this,
    # a stuck request looks identical to a slow one from the pipeline log.
    ox.settings.log_console = True
    # OSMnx's default max_query_area_size (2,500 km^2) split Cusco's ~72,000
    # km^2 polygon into 62 sub-queries — and against a flaky Overpass mirror,
    # 62 independent round-trips means 62 independent chances to stall or
    # drop the connection (observed: nearly 3 hours to finish Cusco's "car"
    # graph alone). Raising the threshold to 15,000 km^2 cuts that to ~5-8
    # larger requests instead — fewer round-trips, each one a bigger but
    # still well within Overpass's 180s per-request timeout (verified: even
    # Cusco's individual successful sub-requests transferred in seconds).
    ox.settings.max_query_area_size = 15_000_000_000


def _department_polygon(department: str, districts_gdf: gpd.GeoDataFrame):
    sub = districts_gdf[districts_gdf["NOMBDEP"].str.upper() == department.upper()]
    if sub.empty:
        raise ValueError(f"No hay distritos para el departamento '{department}' en districts_gdf")
    return sub.union_all()


def graph_cache_path(department: str, profile: str) -> Path:
    cfg = load_config()
    return cfg.path("cache_dir") / "graphs" / f"{department.lower()}_{profile}.graphml"


def build_graph(department: str, profile: str, districts_gdf: gpd.GeoDataFrame, *, force: bool = False):
    """Download (or load from cache) the OSMnx graph for `department` and
    `profile` ('car', 'foot', or 'bike'), with travel_time edge weights
    already computed (config.md routing.fallback_speeds_kmh for foot/bike,
    OSMnx's highway-type speed imputation for car)."""
    _configure_osmnx_cache()
    cfg = load_config()
    network_type = PROFILE_TO_NETWORK_TYPE[profile]
    path = graph_cache_path(department, profile)

    if path.exists() and not force:
        logger.info("Grafo en caché: %s", path)
        return ox.load_graphml(
            path,
            edge_dtypes={"length": float, "speed_kph": float, "travel_time": float, "osmid": str},
        )

    logger.info("Descargando grafo '%s' (%s) desde Overpass...", department, profile)
    t0 = time.time()
    poly = _department_polygon(department, districts_gdf)
    G = _graph_from_polygon_with_retry(poly, network_type)
    logger.info(
        "Grafo '%s' (%s) descargado: %d nodos, %d aristas (%.1fs)",
        department, profile, len(G.nodes), len(G.edges), time.time() - t0,
    )

    if profile == "car":
        fallback_kph = cfg.routing["fallback_speeds_kmh"]["car"]
        G = ox.routing.add_edge_speeds(G, fallback=fallback_kph)
        G = ox.routing.add_edge_travel_times(G)
    else:
        speed_kph = cfg.routing["fallback_speeds_kmh"][profile]
        speed_mps = speed_kph * 1000 / 3600
        for _, _, _, data in G.edges(keys=True, data=True):
            data["speed_kph"] = speed_kph
            data["travel_time"] = data["length"] / speed_mps

    path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, path)
    logger.info("Grafo guardado en caché: %s", path)
    return G


def snap_points_to_graph(points_gdf: gpd.GeoDataFrame, graph) -> tuple[pd.DataFrame, dict]:
    """Snap each point to its nearest graph node. Returns a DataFrame indexed
    like points_gdf with columns [node, snap_dist_m], plus a report dict:
    {n_points, n_failed, mean_snap_distance_m, max_snap_distance_m}."""
    graph_proj = ox.project_graph(graph)
    points_proj = points_gdf.to_crs(graph_proj.graph["crs"])

    valid = points_proj.geometry.notna() & ~points_proj.geometry.is_empty
    result = pd.DataFrame(index=points_gdf.index, columns=["node", "snap_dist_m"])

    if valid.any():
        nodes, dists = ox.distance.nearest_nodes(
            graph_proj,
            X=points_proj.loc[valid].geometry.x.values,
            Y=points_proj.loc[valid].geometry.y.values,
            return_dist=True,
        )
        result.loc[valid, "node"] = nodes
        result.loc[valid, "snap_dist_m"] = dists

    n_failed = int((~valid).sum())
    report = {
        "n_points": int(len(points_gdf)),
        "n_failed": n_failed,
        "mean_snap_distance_m": float(pd.to_numeric(result["snap_dist_m"]).mean()) if valid.any() else None,
        "max_snap_distance_m": float(pd.to_numeric(result["snap_dist_m"]).max()) if valid.any() else None,
    }
    logger.info(
        "Snapping: %d/%d puntos snapeados, distancia media %.1fm, máxima %.1fm, %d fallidos (sin coordenadas)",
        len(points_gdf) - n_failed, len(points_gdf),
        report["mean_snap_distance_m"] or 0.0, report["max_snap_distance_m"] or 0.0, n_failed,
    )
    return result, report


def full_matrix_from_facilities(
    graph, origins: pd.DataFrame, facilities: pd.DataFrame, *, origin_id_col: str, facility_id_col: str
) -> pd.DataFrame:
    """Full origin x facility matrix: for each facility, ONE single-source
    Dijkstra run (over the whole graph) gives travel_time and length to
    every node at once — far cheaper than one shortest-path call per
    (origin, facility) pair, since #facilities << #origins here. Returns a
    long-format DataFrame with one row per (origin, facility) pair,
    including unroutable pairs (routable=False, time/distance=NaN)."""
    origins_valid = origins.dropna(subset=["node"])
    facilities_valid = facilities.dropna(subset=["node"])
    rows = []

    for fac_idx, fac_row in facilities_valid.iterrows():
        fac_node = fac_row["node"]
        times = nx.single_source_dijkstra_path_length(graph, fac_node, weight="travel_time")
        lengths = nx.single_source_dijkstra_path_length(graph, fac_node, weight="length")

        for org_idx, org_row in origins_valid.iterrows():
            org_node = org_row["node"]
            t = times.get(org_node)
            d = lengths.get(org_node)
            rows.append(
                {
                    origin_id_col: org_idx,
                    facility_id_col: fac_idx,
                    "duration_min": (t / 60.0) if t is not None else None,
                    "distance_m": d,
                    "routable": t is not None,
                }
            )

    # unroutable-by-missing-node origins/facilities (failed snap) still get a row
    for org_idx in origins.index.difference(origins_valid.index):
        for fac_idx in facilities.index:
            rows.append({origin_id_col: org_idx, facility_id_col: fac_idx, "duration_min": None, "distance_m": None, "routable": False})

    return pd.DataFrame(rows)


def nearest_from_sources(graph, source_nodes: list, weight: str = "travel_time") -> dict:
    """Multi-source Dijkstra: distance from EVERY node to its NEAREST of
    `source_nodes`, in a single graph traversal. Used when only the nearest
    facility matters (not the full matrix) — e.g. cross-mode (car/bike/foot)
    comparison, or 'nearest facility of any category' for the walk profile."""
    if not source_nodes:
        return {}
    distances, _ = nx.multi_source_dijkstra(graph, sources=set(source_nodes), weight=weight)
    return distances


def nearest_facility(matrix: pd.DataFrame, origin_id_col: str = "origin_id") -> pd.DataFrame:
    """Reduce a full matrix to one row per origin: nearest facility id,
    distance, and duration (routable rows only; origins with zero routable
    rows get facility_id=NaN)."""
    routable = matrix[matrix["routable"]]
    idx = routable.groupby(origin_id_col)["duration_min"].idxmin()
    return routable.loc[idx].reset_index(drop=True)


def cache_path(department: str, profile: str, kind: str = "matrix") -> Path:
    cfg = load_config()
    return cfg.path("processed_dir") / f"routing_{kind}_{department.lower()}_{profile}.parquet"
