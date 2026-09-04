import numpy as np
import pandas as pd
import pytest

from src.metrics import (
    access_time_by_point,
    access_vs_secondary_dimension,
    coverage_bands,
    critical_gap_ranking,
    district_rurality,
    gini_of_access,
    lorenz_curve,
    population_weighted_mean_access,
    urban_rural_contrast,
)


def _nearest_df():
    return pd.DataFrame(
        [
            {"demand_id": 1, "duration_min": 10.0, "routable": True, "population_est": 100, "ubigeo": "A", "is_urban": True},
            {"demand_id": 2, "duration_min": 45.0, "routable": True, "population_est": 50, "ubigeo": "A", "is_urban": False},
            {"demand_id": 3, "duration_min": 90.0, "routable": True, "population_est": 20, "ubigeo": "B", "is_urban": False},
            {"demand_id": 4, "duration_min": None, "routable": False, "population_est": 10, "ubigeo": "B", "is_urban": False},
        ]
    )


def test_access_time_by_point_nulls_unroutable():
    result = access_time_by_point(_nearest_df())
    assert result.loc[result["demand_id"] == 4, "t_min"].isna().item()
    assert result.loc[result["demand_id"] == 1, "t_min"].item() == 10.0


def test_coverage_bands_sum_to_total_population():
    access_df = access_time_by_point(_nearest_df())
    bands = coverage_bands(access_df)
    # bands (30/60/120/beyond) + the unroutable row together partition the
    # whole population exactly once
    assert bands["population"].sum() == pytest.approx(access_df["population_est"].sum())
    assert bands["share"].between(0, 1).all()


def test_population_weighted_mean_access_excludes_unroutable_from_mean():
    access_df = access_time_by_point(_nearest_df())
    result = population_weighted_mean_access(access_df, group_by="ubigeo")
    district_b = result[result["ubigeo"] == "B"].iloc[0]
    # only demand_id 3 (t_min=90) is routable in district B; demand_id 4 is excluded from the mean
    assert district_b["population_weighted_mean_t_min"] == pytest.approx(90.0)
    assert district_b["pct_population_unroutable"] == pytest.approx(100 * 10 / 30)


def test_critical_gap_ranking_orders_worst_first():
    access_df = access_time_by_point(_nearest_df())
    district_access = population_weighted_mean_access(access_df, group_by="ubigeo")
    ranked = critical_gap_ranking(district_access, top_n=2)
    assert ranked.iloc[0]["ubigeo"] == "B"  # 90 min > A's weighted mean


def test_gini_of_access_zero_when_everyone_has_equal_time():
    equal_df = pd.DataFrame({"t_min": [20.0, 20.0, 20.0], "population_est": [10, 20, 30]})
    assert gini_of_access(equal_df) == pytest.approx(0.0, abs=1e-9)


def test_gini_of_access_positive_when_unequal():
    access_df = access_time_by_point(_nearest_df())
    g = gini_of_access(access_df)
    assert 0 < g < 1


def test_lorenz_curve_starts_at_origin_and_ends_at_one():
    access_df = access_time_by_point(_nearest_df())
    curve = lorenz_curve(access_df)
    assert curve.iloc[0]["cum_population_share"] == 0.0
    assert curve.iloc[-1]["cum_population_share"] == pytest.approx(1.0)
    assert curve.iloc[-1]["cum_access_time_share"] == pytest.approx(1.0)


def test_urban_rural_contrast_splits_by_is_urban():
    access_df = access_time_by_point(_nearest_df())
    result = urban_rural_contrast(access_df)
    assert set(result["is_urban"]) == {True, False}


def test_district_rurality_and_cross_analysis_merge():
    access_df = access_time_by_point(_nearest_df())
    rurality = district_rurality(access_df)
    # district A: 100 urban / 150 total -> 33.3% rural; district B: 0 urban / 30 -> 100% rural
    assert rurality.set_index("ubigeo").loc["B", "pct_rural"] == pytest.approx(100.0)

    district_access = population_weighted_mean_access(access_df, group_by="ubigeo")
    merged = access_vs_secondary_dimension(district_access, rurality, secondary_col="pct_rural")
    assert "pct_rural" in merged.columns
    assert "population_weighted_mean_t_min" in merged.columns
