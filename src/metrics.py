"""Phase 3 — metric construction. Every function takes a DataFrame and
returns a DataFrame (or, for gini_of_access, a scalar it is named for) —
no metric logic lives in app.py. All aggregation is population-weighted
per the assignment's explicit requirement: an unweighted district average
would treat a 12-person hamlet the same as a 12,000-person town.

Expected schema for `access_df` throughout this module: one row per demand
point, with at least [t_min, population_est, ubigeo, is_urban] — built by
src/pipeline_phase3.py from src/routing.py's nearest_{dept}_car.parquet
joined against demand_points_sampled_3depts.parquet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import load_config


def access_time_by_point(nearest_df: pd.DataFrame) -> pd.DataFrame:
    """One row per demand point: t_min to nearest resolutive facility
    (NaN, not 0, for unroutable points — they must never silently count as
    'instant access')."""
    result = nearest_df.copy()
    result["t_min"] = np.where(result["routable"], result["duration_min"], np.nan)
    return result


def coverage_bands(access_df: pd.DataFrame, population_col: str = "population_est") -> pd.DataFrame:
    """Share of population within each config.md
    metrics.coverage_bands_minutes band, plus a 'beyond_max' band and an
    'unroutable' band (population with no path at all to any resolutive
    facility in their department's graph — a real finding, not noise)."""
    cfg = load_config()
    bands_min = cfg.metrics["coverage_bands_minutes"]
    total_pop = access_df[population_col].sum()

    rows = []
    lower = 0.0
    for upper in bands_min:
        mask = (access_df["t_min"] > lower) & (access_df["t_min"] <= upper)
        pop = access_df.loc[mask, population_col].sum()
        rows.append({"band": f"{int(lower)}-{int(upper)} min", "population": pop, "share": pop / total_pop})
        lower = upper

    beyond_mask = access_df["t_min"] > lower
    beyond_pop = access_df.loc[beyond_mask, population_col].sum()
    rows.append({"band": f">{int(lower)} min", "population": beyond_pop, "share": beyond_pop / total_pop})

    unroutable_mask = access_df["t_min"].isna()
    unroutable_pop = access_df.loc[unroutable_mask, population_col].sum()
    rows.append({"band": "unroutable", "population": unroutable_pop, "share": unroutable_pop / total_pop})

    return pd.DataFrame(rows)


def population_weighted_mean_access(
    access_df: pd.DataFrame, group_by: str, population_col: str = "population_est"
) -> pd.DataFrame:
    """Population-weighted mean access time aggregated at `group_by`
    (e.g. 'ubigeo' for district, 'province', 'department'). Rows with no
    route (t_min is NaN) are excluded from the weighted mean itself but
    counted separately as `pct_population_unroutable`."""

    def _weighted(group: pd.DataFrame) -> pd.Series:
        routable = group.dropna(subset=["t_min"])
        total_pop = group[population_col].sum()
        routable_pop = routable[population_col].sum()
        weighted_mean = (
            (routable["t_min"] * routable[population_col]).sum() / routable_pop
            if routable_pop > 0
            else np.nan
        )
        return pd.Series(
            {
                "population_weighted_mean_t_min": weighted_mean,
                "total_population": total_pop,
                "n_demand_points": len(group),
                "pct_population_unroutable": 100 * (total_pop - routable_pop) / total_pop if total_pop else np.nan,
            }
        )

    return access_df.groupby(group_by).apply(_weighted, include_groups=False).reset_index()


def critical_gap_ranking(district_access_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """The `top_n` districts with the worst (highest) population-weighted
    access time, from a table already aggregated by
    population_weighted_mean_access(..., group_by='ubigeo')."""
    return (
        district_access_df.dropna(subset=["population_weighted_mean_t_min"])
        .sort_values("population_weighted_mean_t_min", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


def lorenz_curve(access_df: pd.DataFrame, population_col: str = "population_est") -> pd.DataFrame:
    """Population-weighted Lorenz curve of access time: cumulative
    population share (x) vs. cumulative access-time share (y). Perfect
    equality is the y=x diagonal."""
    d = access_df.dropna(subset=["t_min"]).sort_values("t_min")
    pop = d[population_col].to_numpy()
    val = d["t_min"].to_numpy()

    cum_pop_share = np.cumsum(pop) / pop.sum()
    cum_val_share = np.cumsum(pop * val) / (pop * val).sum()

    return pd.DataFrame(
        {
            "cum_population_share": np.concatenate([[0.0], cum_pop_share]),
            "cum_access_time_share": np.concatenate([[0.0], cum_val_share]),
        }
    )


def gini_of_access(access_df: pd.DataFrame, population_col: str = "population_est") -> float:
    """Population-weighted Gini coefficient of access time, via the area
    under the Lorenz curve (1 - 2*B). Chosen over a plain variance/stdev
    because it is bounded [0,1], standard in the health-access literature,
    scale-invariant (comparable across departments with very different
    mean access times), and directly visualizable alongside
    lorenz_curve()."""
    curve = lorenz_curve(access_df, population_col)
    area_under_curve = np.trapezoid(curve["cum_access_time_share"], curve["cum_population_share"])
    return float(1 - 2 * area_under_curve)


def urban_rural_contrast(access_df: pd.DataFrame, population_col: str = "population_est") -> pd.DataFrame:
    """Population-weighted mean access time split by is_urban, per
    config.md metrics.urban_rural_rule."""
    return population_weighted_mean_access(access_df, group_by="is_urban", population_col=population_col)


def access_vs_secondary_dimension(
    district_access_df: pd.DataFrame, secondary_df: pd.DataFrame, secondary_col: str
) -> pd.DataFrame:
    """Join population-weighted district access against config.md
    metrics.cross_analysis_secondary_dimension (rurality, by default —
    see config.md for why: it's the one option computable from data
    already in hand, unlike poverty rate/altitude/population-under-5,
    which would need an additional source). Returns the merged table;
    correlation direction/strength and the causal-vs-correlational framing
    belong in the report (src/export.py + report/main.tex), not here."""
    return district_access_df.merge(secondary_df, on="ubigeo", how="inner")


def district_rurality(access_df: pd.DataFrame, population_col: str = "population_est") -> pd.DataFrame:
    """Per-district share of population classified rural (1 - is_urban
    population share) — the secondary dimension used by
    access_vs_secondary_dimension() by default."""

    def _share_rural(group: pd.DataFrame) -> float:
        total = group[population_col].sum()
        urban = group.loc[group["is_urban"], population_col].sum()
        return 100 * (total - urban) / total if total else np.nan

    return (
        access_df.groupby("ubigeo")
        .apply(lambda g: _share_rural(g), include_groups=False)
        .rename("pct_rural")
        .reset_index()
    )
