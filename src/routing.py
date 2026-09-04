"""Phase 2 — routing engine: OSMnx + NetworkX (see config.md for why no
Docker/OSRM). Importable and testable independently of the acquisition/
validation pipeline, per the assignment's Phase 2 technical considerations.

Every result is cached to data/processed/routing_matrix_<department>.parquet;
re-running the pipeline must not recompute rows already on disk.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("routing")


def build_graph(department: str, network_type: str = "drive"):
    """Download/cache an OSMnx graph for `department` and `network_type`
    ('drive', 'walk', or 'bike')."""
    raise NotImplementedError


def snap_points_to_graph(points_gdf, graph) -> tuple[pd.DataFrame, dict]:
    """Snap each point to its nearest graph node. Returns the snapped table
    plus a report dict: {n_failed, mean_snap_distance_m, max_snap_distance_m}."""
    raise NotImplementedError


def compute_travel_time_matrix(
    origins_gdf, destinations_gdf, graph, profile: str
) -> pd.DataFrame:
    """Full origin x destination matrix of (distance_m, duration_min) for one
    profile. Unroutable pairs get duration_min = NaN and routable = False —
    never a straight-line substitute unless explicitly requested."""
    raise NotImplementedError


def nearest_facility(matrix: pd.DataFrame) -> pd.DataFrame:
    """Reduce a full matrix to one row per origin: nearest facility id,
    distance, duration, and profile."""
    raise NotImplementedError


def cache_path(department: str, profile: str) -> Path:
    cfg = load_config()
    return cfg.path("processed_dir") / f"routing_matrix_{department}_{profile}.parquet"


def compute_or_load_matrix(
    department: str, origins_gdf, destinations_gdf, profile: str, *, force: bool = False
) -> pd.DataFrame:
    path = cache_path(department, profile)
    if path.exists() and not force:
        logger.info("Cache hit: %s", path)
        return pd.read_parquet(path)
    raise NotImplementedError
