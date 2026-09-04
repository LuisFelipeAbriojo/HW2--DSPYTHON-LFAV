"""Phase 1 — data quality rules. Each check_* function takes the raw
GeoDataFrame/DataFrame and returns (clean_df, flagged_df, report_row) so the
data quality report in export.run_data_quality_report can be assembled from
one list of report rows without re-deriving counts elsewhere."""

from __future__ import annotations

import pandas as pd

from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("validation")


def normalize_category(raw_category: str) -> str:
    """Map a raw RENIPRESS category string to the canonical whitelist in
    config.md (resolutive_categories + non_resolutive_categories)."""
    raise NotImplementedError


def is_resolutive(category: str, status: str) -> bool:
    cfg = load_config()
    return (
        category in cfg.resolutive_categories
        and status.strip().upper() in cfg.active_status_values
    )


def check_missing_coordinates(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raise NotImplementedError


def check_out_of_bbox(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raise NotImplementedError


def check_swapped_lat_lon(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raise NotImplementedError


def check_district_containment(df: pd.DataFrame, districts_gdf) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raise NotImplementedError


def check_duplicate_codes(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raise NotImplementedError


def check_encoding(df: pd.DataFrame, text_columns: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raise NotImplementedError


def run_all_checks(df: pd.DataFrame, districts_gdf) -> tuple[pd.DataFrame, list[dict]]:
    """Run every check_* in sequence, returning the cleaned frame plus a list
    of report rows (one per rule) for the data quality report."""
    raise NotImplementedError
