"""Population apportionment and demand-point sampling.

SIGMED's "Centros Poblados" layer has no population field (see config.md
sources.population_census2017). We only have population at the DISTRICT
level (INEI Censo 2017). This module apportions each district's population
across its centros poblados, then uses that estimate both to classify
urban/rural (config.md metrics.urban_rural_rule) and to draw a
population-weighted sample when a department's demand points exceed
config.md routing.max_demand_points.

Apportionment rule (documented limitation — not empirically derived):
SIGMED's `is_capital` (raw column CAPITAL) is not boolean — it is a
hierarchy level verified against real data on 2026-09-04: "0" = not a
capital (151,526 national rows), "3" = district capital (1,678), "2" =
province capital (171), "1" = department capital (25 — an exact match to
Peru's 24 departments + Callao, confirming the encoding). CAPITAL_WEIGHTS
below assigns each level an assumed population-mass multiplier relative to
an ordinary hamlet, escalating with administrative importance; a
district's census population is then split across its points in that
proportion. This is a coarse proxy, not a measurement — flagged explicitly
in the Phase 5 report's Limitations section.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import load_config

CAPITAL_WEIGHTS = {"0": 1.0, "3": 10.0, "2": 30.0, "1": 100.0}


def apportion_population_to_points(demand_df: pd.DataFrame, population_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Add a `population_est` column to demand_df by splitting each
    district's census population across its centros poblados per
    CAPITAL_WEIGHTS. Returns (result_df, n_points_with_no_district_population)."""
    result = demand_df.copy()
    # a handful of districts have no ubigeo (created after limites_distritales.geojson's
    # cutoff, see config.md sources.population_census2017) — their blank "" would
    # collide into one non-unique index key, so they're excluded here rather than
    # matched to the wrong district.
    pop_with_ubigeo = population_df[population_df["ubigeo"].astype(str).str.len() > 0]
    pop_by_ubigeo = pop_with_ubigeo.set_index("ubigeo")["poblacion_2017"]

    result["_weight"] = result["is_capital"].astype(str).map(CAPITAL_WEIGHTS).fillna(1.0)
    weight_sum_by_district = result.groupby("ubigeo")["_weight"].transform("sum")
    district_population = result["ubigeo"].map(pop_by_ubigeo)

    result["population_est"] = (result["_weight"] / weight_sum_by_district) * district_population
    result = result.drop(columns="_weight")

    n_no_population = int(result["population_est"].isna().sum())
    if n_no_population:
        result["population_est"] = result["population_est"].fillna(0.0)
    return result, n_no_population


def classify_urban(demand_df: pd.DataFrame) -> pd.DataFrame:
    """Boolean `is_urban` column per config.md metrics.urban_rural_rule
    (population_est >= urban_pop_threshold, OR the point is itself a
    district capital — a capital below the population threshold is still
    the district's urban center)."""
    cfg = load_config()
    threshold = cfg.metrics.get("urban_pop_threshold", 2000)
    result = demand_df.copy()
    is_any_capital = result["is_capital"].astype(str) != "0"
    result["is_urban"] = (result["population_est"] >= threshold) | is_any_capital
    return result


def sample_demand_points(demand_df: pd.DataFrame, max_points: int, seed: int) -> pd.DataFrame:
    """Population-weighted sample capped at max_points, stratified by
    department so every department in scope keeps points proportional to
    its share of total estimated population (not just its share of raw
    point count, which would over-represent departments with many tiny
    hamlets like Cusco)."""
    if len(demand_df) <= max_points:
        return demand_df.copy()

    rng = np.random.default_rng(seed)
    pop_by_dept = demand_df.groupby("department")["population_est"].sum()
    total_pop = pop_by_dept.sum()
    quota_by_dept = (pop_by_dept / total_pop * max_points).round().astype(int)

    sampled_parts = []
    for dept, quota in quota_by_dept.items():
        sub = demand_df[demand_df["department"] == dept]
        quota = min(quota, len(sub))
        if quota <= 0:
            continue
        weights = sub["population_est"].clip(lower=0.01)
        chosen_idx = rng.choice(sub.index, size=quota, replace=False, p=weights / weights.sum())
        sampled_parts.append(sub.loc[chosen_idx])

    return pd.concat(sampled_parts).sort_index()
