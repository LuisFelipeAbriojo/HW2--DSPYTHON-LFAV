"""Innovation (beyond the assignment's base 20 points): facility siting via
a greedy Maximal Covering Location Problem (MCLP).

Question answered: of the I-3/I-4 facilities NOT currently resolutive, if
we could upgrade only k of them, which ones cover the most additional
population within the access-time threshold? This reuses the full car
matrix from Phase 2 (already routed to every I-3/I-4 candidate, not just
the resolutive set — see src/pipeline_phase2.py) and the population
estimates from Phase 2's sampling — no new data, no new routing.

Greedy MCLP is the standard approximation for this NP-hard problem: pick
the single best facility, lock it in, repeat. It is not guaranteed optimal
but is provably within (1 - 1/e) of the optimum for submodular coverage
objectives like this one, and is the practical standard for this class of
problem in the facility-location literature.
"""

from __future__ import annotations

import pandas as pd

from src.logging_utils import get_logger

logger = get_logger("optimization")


def greedy_facility_siting(
    car_matrix: pd.DataFrame, population_by_demand: pd.Series, time_threshold_min: float, k: int = 5
) -> pd.DataFrame:
    """Greedy MCLP over I-3/I-4 candidates in `car_matrix` (must carry
    facility_is_resolutive, produced by src/pipeline_phase2.py's
    run_car()). Returns up to `k` rows, one per pick in order, with the
    marginal and cumulative population covered within time_threshold_min —
    empty if there are no candidates or no coverage gain is possible."""
    baseline_covered_mask = (
        car_matrix["facility_is_resolutive"] & car_matrix["routable"] & (car_matrix["duration_min"] <= time_threshold_min)
    )
    covered = set(car_matrix.loc[baseline_covered_mask, "demand_id"])
    baseline_pop = population_by_demand.reindex(list(covered)).sum()

    candidate_mask = (
        ~car_matrix["facility_is_resolutive"] & car_matrix["routable"] & (car_matrix["duration_min"] <= time_threshold_min)
    )
    candidate_coverage = car_matrix.loc[candidate_mask].groupby("facility_id")["demand_id"].apply(set).to_dict()

    picks = []
    cumulative_pop = baseline_pop
    remaining = dict(candidate_coverage)

    for _ in range(k):
        if not remaining:
            break
        best_id, best_gain, best_new_ids = None, 0.0, None
        for fac_id, ids in remaining.items():
            new_ids = ids - covered
            if not new_ids:
                continue
            gain = population_by_demand.reindex(list(new_ids)).sum()
            if gain > best_gain:
                best_id, best_gain, best_new_ids = fac_id, gain, new_ids

        if best_id is None:
            break  # no remaining candidate adds any new coverage

        covered |= best_new_ids
        cumulative_pop += best_gain
        picks.append(
            {
                "rank": len(picks) + 1,
                "facility_id": best_id,
                "marginal_population_gained": best_gain,
                "cumulative_population_covered": cumulative_pop,
                "cumulative_gain_over_baseline": cumulative_pop - baseline_pop,
            }
        )
        del remaining[best_id]

    result = pd.DataFrame(picks)
    logger.info(
        "Greedy MCLP: %d instalaciones recomendadas, ganancia acumulada de población = %.0f (línea base = %.0f)",
        len(result), (result["cumulative_gain_over_baseline"].iloc[-1] if len(result) else 0), baseline_pop,
    )
    return result
