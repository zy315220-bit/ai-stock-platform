from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class PerformanceSlice:
    slice_id: str
    start: str
    end: str
    robot_returns: Mapping[str, float]


def build_performance_matrix(
    slices: Sequence[PerformanceSlice],
    robot_ids: Sequence[str],
) -> dict[str, object]:
    """Build the rectangular time-slice × strategy matrix required by CSCV/PBO.

    This function intentionally does not calculate PBO. It validates and freezes the
    data structure needed by a later CSCV implementation so missing strategies or
    duplicate/non-chronological slices cannot silently bias the estimate.
    """
    robots = [str(robot_id) for robot_id in robot_ids]
    if len(robots) < 2:
        raise ValueError("CSCV requires at least two strategies")
    if len(set(robots)) != len(robots):
        raise ValueError("robot_ids must be unique")
    if len(slices) < 2:
        raise ValueError("CSCV requires at least two time slices")

    seen_slices: set[str] = set()
    rows: list[list[float]] = []
    metadata: list[dict[str, str]] = []
    previous_end: str | None = None
    required = set(robots)

    for item in slices:
        if item.slice_id in seen_slices:
            raise ValueError(f"duplicate slice_id: {item.slice_id}")
        seen_slices.add(item.slice_id)
        if item.start > item.end:
            raise ValueError(f"slice {item.slice_id} starts after it ends")
        if previous_end is not None and item.start <= previous_end:
            raise ValueError("time slices must be strictly chronological and non-overlapping")
        previous_end = item.end

        available = set(item.robot_returns)
        missing = required - available
        extra = available - required
        if missing or extra:
            raise ValueError(
                f"slice {item.slice_id} strategy mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        row = [float(item.robot_returns[robot_id]) for robot_id in robots]
        if any(value != value or value in (float("inf"), float("-inf")) for value in row):
            raise ValueError(f"slice {item.slice_id} contains non-finite performance")
        rows.append(row)
        metadata.append({"slice_id": item.slice_id, "start": item.start, "end": item.end})

    return {
        "schema": "cscv-performance-matrix-v1",
        "metric": "net_total_return_percent",
        "robot_ids": robots,
        "slice_count": len(rows),
        "strategy_count": len(robots),
        "slices": metadata,
        "matrix": rows,
        "ready_for_pbo": len(rows) >= 4 and len(rows) % 2 == 0,
        "warning": "此矩陣只建立 CSCV/PBO 所需資料結構；未達足夠且偶數時間切片時不得宣稱 PBO。",
    }
