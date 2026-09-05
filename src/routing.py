"""Phase 2 — routing engine: OSMnx-compatible graphs built OFFLINE from the
local Peru OSM extract (data/raw/peru-latest.osm.pbf), via GDAL's OSM
vector driver (already available through pyogrio/fiona — no pyrosm, no
compiler, no Docker; see config.md for the full story of how we got here).

Every result is cached to data/processed/routing_matrix_<department>_<profile>.parquet;
re-running the pipeline must not recompute rows already on disk. Unroutable
origin/destination pairs (disconnected graph components) are marked
routable=False with NaN time/distance — never silently substituted with a
straight-line estimate.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import pyogrio

from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("routing")

# Highway-tag filters per profile. The 'car' set matches OSMnx's own
# network_type='drive' filter verbatim (captured from the exact Overpass
# query OSMnx issued during this project's earlier live-download attempts —
# see config.md). 'foot' and 'bike' are this project's own, documented
# choices: walk keeps every human-passable way (incl. footway/path/steps)
# and drops motor-only roads; bike drops pedestrian-only ways plus
# motor-only roads.
DRIVE_HIGHWAY_EXCLUDE = frozenset({
    "abandoned", "bridleway", "bus_guideway", "construction", "corridor",
    "cycleway", "elevator", "escalator", "footway", "no", "path",
    "pedestrian", "planned", "platform", "proposed", "raceway", "razed",
    "rest_area", "service", "services", "steps", "track",
})
WALK_HIGHWAY_EXCLUDE = frozenset({
    "abandoned", "bus_guideway", "construction", "corridor", "cycleway",
    "elevator", "escalator", "motorway", "motorway_link", "no", "planned",
    "platform", "proposed", "raceway", "razed",
})
BIKE_HIGHWAY_EXCLUDE = frozenset({
    "abandoned", "bus_guideway", "construction", "corridor", "elevator",
    "escalator", "footway", "motorway", "motorway_link", "no", "planned",
    "platform", "proposed", "raceway", "razed", "steps",
})
PROFILE_HIGHWAY_EXCLUDE = {"car": DRIVE_HIGHWAY_EXCLUDE, "foot": WALK_HIGHWAY_EXCLUDE, "bike": BIKE_HIGHWAY_EXCLUDE}

# Speed imputation by highway class (km/h) for the 'car' profile, in the
# same spirit as OSMnx's hwy_speeds fallback — most Peruvian ways carry no
# maxspeed tag. foot/bike use the flat speeds in config.md instead, since
# highway class doesn't meaningfully change walking/cycling pace.
CAR_SPEED_BY_HIGHWAY_KPH = {
    "motorway": 100, "motorway_link": 70, "trunk": 80, "trunk_link": 50,
    "primary": 60, "primary_link": 40, "secondary": 50, "secondary_link": 35,
    "tertiary": 40, "tertiary_link": 30, "unclassified": 30, "residential": 25,
    "living_street": 15, "service": 15, "track": 15,
}

_OTHER_TAGS_RE = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')


def _parse_other_tags(s: str | None) -> dict[str, str]:
    """GDAL's OSM driver packs every non-promoted OSM tag into one hstore-
    style string: "key"=>"value","key2"=>"value2". Used here only for the
    handful of access-restriction tags (access/motor_vehicle/foot/bicycle/
    oneway) that aren't already their own column."""
    if not isinstance(s, str):  # NaN (float) for lines with no extra tags
        return {}
    return dict(_OTHER_TAGS_RE.findall(s))


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def _department_polygon(department: str, districts_gdf: gpd.GeoDataFrame):
    sub = districts_gdf[districts_gdf["NOMBDEP"].str.upper() == department.upper()]
    if sub.empty:
        raise ValueError(f"No hay distritos para el departamento '{department}' en districts_gdf")
    return sub.union_all()


def graph_cache_path(department: str, profile: str) -> Path:
    cfg = load_config()
    return cfg.path("cache_dir") / "graphs" / f"{department.lower()}_{profile}.graphml"


def _is_access_excluded(other_tags: str | None, profile: str) -> bool:
    tags = _parse_other_tags(other_tags)
    if tags.get("access") == "private":
        return True
    if profile == "car" and tags.get("motor_vehicle") == "no":
        return True
    if profile == "foot" and tags.get("foot") == "no":
        return True
    if profile == "bike" and tags.get("bicycle") == "no":
        return True
    return False


def build_graph(department: str, profile: str, districts_gdf: gpd.GeoDataFrame, *, force: bool = False):
    """Build (or load from cache) a NetworkX MultiDiGraph for `department`
    and `profile` ('car', 'foot', or 'bike'), read directly from the local
    peru-latest.osm.pbf via GDAL's OSM driver — no live API call. Travel_time
    edge weights are already computed."""
    cfg = load_config()
    path = graph_cache_path(department, profile)

    if path.exists() and not force:
        logger.info("Grafo en caché: %s", path)
        return ox.load_graphml(
            path,
            edge_dtypes={"length": float, "travel_time": float, "highway": str},
        )

    t0 = time.time()
    poly = _department_polygon(department, districts_gdf)
    minx, miny, maxx, maxy = poly.bounds
    pbf_path = cfg.path("raw_dir") / cfg.sources["osm_pbf"]["local_raw_name"]

    logger.info("%s (%s): leyendo líneas OSM del .pbf local (bbox)...", department, profile)
    gdf = pyogrio.read_dataframe(
        str(pbf_path), layer="lines", bbox=(minx, miny, maxx, maxy), where="highway IS NOT NULL"
    )
    logger.info("%s (%s): %d líneas leídas en %.1fs", department, profile, len(gdf), time.time() - t0)

    exclude = PROFILE_HIGHWAY_EXCLUDE[profile]
    gdf = gdf[~gdf["highway"].isin(exclude)]
    gdf = gdf[gdf.intersects(poly)]  # bbox read over-fetches; clip to the real department polygon
    gdf = gdf[~gdf["other_tags"].apply(lambda t: _is_access_excluded(t, profile))]
    logger.info("%s (%s): %d segmentos tras filtrar tipo de vía y acceso", department, profile, len(gdf))

    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    G.graph["name"] = f"{department}_{profile}"

    fallback_car_kph = cfg.routing["fallback_speeds_kmh"]["car"]
    flat_speed_kph = None if profile == "car" else cfg.routing["fallback_speeds_kmh"][profile]

    node_id_by_coord: dict[tuple[float, float], int] = {}

    def _node_id(coord: tuple[float, float]) -> int:
        key = (round(coord[0], 7), round(coord[1], 7))
        nid = node_id_by_coord.get(key)
        if nid is None:
            nid = len(node_id_by_coord)
            node_id_by_coord[key] = nid
            G.add_node(nid, x=key[0], y=key[1])
        return nid

    for row in gdf.itertuples(index=False):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        coords = list(geom.coords)
        speed_kph = flat_speed_kph or CAR_SPEED_BY_HIGHWAY_KPH.get(row.highway, fallback_car_kph)
        speed_mps = speed_kph * 1000 / 3600
        oneway = _parse_other_tags(row.other_tags).get("oneway") in ("yes", "true", "1")

        for a, b in zip(coords[:-1], coords[1:]):
            u, v = _node_id(a), _node_id(b)
            length_m = _haversine_m(a[1], a[0], b[1], b[0])
            travel_time = length_m / speed_mps
            G.add_edge(u, v, length=length_m, travel_time=travel_time, highway=row.highway)
            if not oneway:
                G.add_edge(v, u, length=length_m, travel_time=travel_time, highway=row.highway)

    n_raw_nodes, n_raw_edges = G.number_of_nodes(), G.number_of_edges()
    if n_raw_nodes:
        largest_cc = max(nx.weakly_connected_components(G), key=len)
        G = G.subgraph(largest_cc).copy()
    logger.info(
        "%s (%s): grafo construido — %d nodos / %d aristas brutos, %d / %d en la componente conexa más grande (%.1fs total)",
        department, profile, n_raw_nodes, n_raw_edges, G.number_of_nodes(), G.number_of_edges(), time.time() - t0,
    )

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
    origin_nodes = origins_valid["node"]
    parts = []

    for fac_idx, fac_row in facilities_valid.iterrows():
        fac_node = fac_row["node"]
        # single_source_dijkstra_path_length is the expensive part (one
        # traversal of the whole graph); everything after it must be
        # vectorized pandas, not a Python-level loop over every origin —
        # with an unsimplified (no topology merge) graph and hundreds of
        # facilities, an iterrows()-per-origin inner loop turns "cheap
        # because #facilities << #origins" into the dominant cost instead.
        times = nx.single_source_dijkstra_path_length(graph, fac_node, weight="travel_time")
        lengths = nx.single_source_dijkstra_path_length(graph, fac_node, weight="length")

        duration_min = origin_nodes.map(times) / 60.0
        distance_m = origin_nodes.map(lengths)
        parts.append(
            pd.DataFrame(
                {
                    origin_id_col: origins_valid.index,
                    facility_id_col: fac_idx,
                    "duration_min": duration_min.values,
                    "distance_m": distance_m.values,
                    "routable": duration_min.notna().values,
                }
            )
        )

    # unroutable-by-missing-node origins/facilities (failed snap) still get a row
    missing_origins = origins.index.difference(origins_valid.index)
    if len(missing_origins):
        parts.append(
            pd.DataFrame(
                [
                    {origin_id_col: org_idx, facility_id_col: fac_idx, "duration_min": None, "distance_m": None, "routable": False}
                    for org_idx in missing_origins
                    for fac_idx in facilities.index
                ]
            )
        )

    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=[origin_id_col, facility_id_col, "duration_min", "distance_m", "routable"]
    )


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
