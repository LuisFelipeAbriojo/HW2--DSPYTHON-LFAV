"""Phase 3 — metric construction. Every function takes a DataFrame and
returns a DataFrame (no metric logic lives in app.py)."""

from __future__ import annotations

import pandas as pd

from src.config import load_config


def access_time_by_point(nearest_df: pd.DataFrame) -> pd.DataFrame:
    """One row per demand point: t_min to nearest resolutive facility."""
    raise NotImplementedError


def coverage_bands(access_df: pd.DataFrame, population_col: str = "population") -> pd.DataFrame:
    """Share of population within each config.md metrics.coverage_bands_minutes
    band, plus a 'beyond_max' band."""
    raise NotImplementedError


def population_weighted_mean_access(
    access_df: pd.DataFrame, group_by: str, population_col: str = "population"
) -> pd.DataFrame:
    """Population-weighted mean access time aggregated at `group_by`
    (district/province/department ubigeo column)."""
    raise NotImplementedError


def critical_gap_ranking(district_access_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    raise NotImplementedError


def gini_of_access(access_df: pd.DataFrame, population_col: str = "population") -> float:
    """Population-weighted Gini coefficient of access time. Chosen over a
    simple variance measure because it is bounded [0,1], standard in the
    health-access literature, and directly comparable across departments of
    very different population size."""
    raise NotImplementedError


def lorenz_curve(access_df: pd.DataFrame, population_col: str = "population") -> pd.DataFrame:
    raise NotImplementedError


def urban_rural_contrast(access_df: pd.DataFrame) -> pd.DataFrame:
    """Split by the urban/rural rule declared in config.md
    (metrics.urban_rural_rule)."""
    raise NotImplementedError


def access_vs_secondary_dimension(
    district_access_df: pd.DataFrame, secondary_df: pd.DataFrame, secondary_col: str
) -> pd.DataFrame:
    """Join population-weighted access against config.md
    metrics.cross_analysis_secondary_dimension (default: poverty_rate)."""
    raise NotImplementedError
