from __future__ import annotations

from itertools import combinations
import math
from typing import Sequence


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _average_rank(values: Sequence[float], target_index: int) -> float:
    target = values[target_index]
    less = sum(value < target for value in values)
    equal = sum(value == target for value in values)
    return less + (equal + 1.0) / 2.0


def calculate_cscv_pbo(matrix_payload: dict[str, object]) -> dict[str, object]:
    """Estimate PBO using combinatorially symmetric cross-validation.

    For every symmetric half-split of time slices, select the strategy with the
    highest mean in-sample return, then rank that same strategy out-of-sample.
    PBO is the fraction of selected strategies whose OOS relative rank is below
    the median (logit < 0). Complementary splits are both informative because
    their in-sample selections may differ.
    """
    if not bool(matrix_payload.get("ready_for_pbo")):
        raise ValueError("performance matrix is not ready for PBO")
    robot_ids = [str(value) for value in matrix_payload.get("robot_ids", [])]
    matrix = [[float(value) for value in row] for row in matrix_payload.get("matrix", [])]
    slice_count = len(matrix)
    strategy_count = len(robot_ids)
    if slice_count < 4 or slice_count % 2:
        raise ValueError("CSCV requires an even number of at least four slices")
    if strategy_count < 2 or any(len(row) != strategy_count for row in matrix):
        raise ValueError("invalid rectangular strategy matrix")
    if any(not math.isfinite(value) for row in matrix for value in row):
        raise ValueError("matrix contains non-finite performance")

    half = slice_count // 2
    split_records: list[dict[str, object]] = []
    # Enumerate each complementary pair once, then evaluate both directions.
    first_slice = 0
    for in_sample_tuple in combinations(range(slice_count), half):
        if first_slice not in in_sample_tuple:
            continue
        in_sample = set(in_sample_tuple)
        out_sample = [idx for idx in range(slice_count) if idx not in in_sample]
        for train, test in ((list(in_sample_tuple), out_sample), (out_sample, list(in_sample_tuple))):
            is_scores = [_mean([matrix[row][col] for row in train]) for col in range(strategy_count)]
            selected = max(range(strategy_count), key=lambda col: (is_scores[col], -col))
            oos_scores = [_mean([matrix[row][col] for row in test]) for col in range(strategy_count)]
            rank = _average_rank(oos_scores, selected)
            omega = rank / (strategy_count + 1.0)
            logit = math.log(omega / (1.0 - omega))
            split_records.append({
                "selected_robot_id": robot_ids[selected],
                "is_mean_return_percent": round(is_scores[selected], 8),
                "oos_mean_return_percent": round(oos_scores[selected], 8),
                "oos_rank": round(rank, 4),
                "oos_relative_rank": round(omega, 8),
                "logit": round(logit, 8),
                "overfit": logit < 0.0,
            })

    overfit_count = sum(bool(record["overfit"]) for record in split_records)
    pbo = overfit_count / len(split_records)
    selection_counts = {robot_id: 0 for robot_id in robot_ids}
    for record in split_records:
        selection_counts[str(record["selected_robot_id"])] += 1
    return {
        "method": "CSCV-PBO-v1",
        "slice_count": slice_count,
        "strategy_count": strategy_count,
        "split_count": len(split_records),
        "pbo": round(pbo, 8),
        "pbo_percent": round(pbo * 100.0, 2),
        "overfit_split_count": overfit_count,
        "selection_counts": selection_counts,
        "interpretation": "estimated_probability_selected_in_sample_winner_ranks_below_oos_median",
        "records": split_records,
        "warning": "PBO 衡量策略選拔的回測過度擬合風險，不等於未來虧損機率，也不保證低 PBO 策略未來獲利。",
    }
