import pandas as pd

from src.sampling import apportion_population_to_points, classify_urban, sample_demand_points


def _demand_df():
    return pd.DataFrame(
        [
            {"ubigeo": "140101", "department": "LAMBAYEQUE", "is_capital": "1"},
            {"ubigeo": "140101", "department": "LAMBAYEQUE", "is_capital": "0"},
            {"ubigeo": "140101", "department": "LAMBAYEQUE", "is_capital": "0"},
            {"ubigeo": "140102", "department": "LAMBAYEQUE", "is_capital": "3"},
            {"ubigeo": "140102", "department": "LAMBAYEQUE", "is_capital": "0"},
        ]
    )


def _population_df():
    return pd.DataFrame(
        [
            {"ubigeo": "140101", "poblacion_2017": 1020},
            {"ubigeo": "140102", "poblacion_2017": 110},
        ]
    )


def test_apportion_population_weights_capitals_more_and_sums_to_district_total():
    result, n_missing = apportion_population_to_points(_demand_df(), _population_df())
    assert n_missing == 0
    district_a = result[result["ubigeo"] == "140101"]
    assert district_a["population_est"].sum() == 1020
    capital_row = district_a[district_a["is_capital"] == "1"]
    assert capital_row["population_est"].item() > district_a[district_a["is_capital"] == "0"]["population_est"].iloc[0]


def test_apportion_flags_points_with_no_matching_district():
    demand = pd.concat([_demand_df(), pd.DataFrame([{"ubigeo": "999999", "department": "LAMBAYEQUE", "is_capital": "0"}])])
    result, n_missing = apportion_population_to_points(demand, _population_df())
    assert n_missing == 1
    assert result[result["ubigeo"] == "999999"]["population_est"].item() == 0.0


def test_classify_urban_flags_capitals_and_high_population():
    demand, _ = apportion_population_to_points(_demand_df(), _population_df())
    result = classify_urban(demand)
    # the department-capital row (is_capital == "1") should be urban regardless of population_est
    assert result[result["is_capital"] == "1"]["is_urban"].all()


def test_sample_demand_points_respects_cap_and_returns_all_when_under_cap():
    demand, _ = apportion_population_to_points(_demand_df(), _population_df())
    under_cap = sample_demand_points(demand, max_points=10, seed=42)
    assert len(under_cap) == len(demand)

    over_cap = sample_demand_points(demand, max_points=2, seed=42)
    assert len(over_cap) == 2
