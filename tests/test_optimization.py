import pandas as pd

from src.optimization import greedy_facility_siting


def _matrix():
    # 2 resolutive facilities already covering demand 1,2; three I-3/I-4
    # candidates (A covers 3,4; B covers 3 only; C covers nothing new)
    rows = [
        {"demand_id": 1, "facility_id": "R1", "duration_min": 10, "routable": True, "facility_is_resolutive": True},
        {"demand_id": 2, "facility_id": "R1", "duration_min": 15, "routable": True, "facility_is_resolutive": True},
        {"demand_id": 3, "facility_id": "A", "duration_min": 20, "routable": True, "facility_is_resolutive": False},
        {"demand_id": 4, "facility_id": "A", "duration_min": 25, "routable": True, "facility_is_resolutive": False},
        {"demand_id": 3, "facility_id": "B", "duration_min": 22, "routable": True, "facility_is_resolutive": False},
        {"demand_id": 1, "facility_id": "C", "duration_min": 5, "routable": True, "facility_is_resolutive": False},
    ]
    return pd.DataFrame(rows)


def _population():
    return pd.Series({1: 100, 2: 200, 3: 50, 4: 30})


def test_greedy_picks_the_facility_with_the_most_new_coverage_first():
    result = greedy_facility_siting(_matrix(), _population(), time_threshold_min=30, k=5)
    assert result.iloc[0]["facility_id"] == "A"  # covers 50+30=80 new pop, beats B's 50
    assert result.iloc[0]["marginal_population_gained"] == 80


def test_greedy_stops_when_no_candidate_adds_new_coverage():
    result = greedy_facility_siting(_matrix(), _population(), time_threshold_min=30, k=5)
    # after picking A (covers 3,4) and B (only covers 3, already covered) and
    # C (only covers 1, already covered by baseline), no further gain exists
    assert len(result) == 1


def test_greedy_respects_k_limit():
    result = greedy_facility_siting(_matrix(), _population(), time_threshold_min=30, k=0)
    assert len(result) == 0
