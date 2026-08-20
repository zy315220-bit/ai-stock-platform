from __future__ import annotations

from typing import Any


DEFAULT_MAX_PBO_PERCENT = 25.0
DEFAULT_MIN_POSITIVE_SLICE_RATE = 0.60


def evaluate_champion_gate(
    *,
    competition: dict[str, Any],
    pbo_analysis: dict[str, Any],
    max_pbo_percent: float = DEFAULT_MAX_PBO_PERCENT,
    min_positive_slice_rate: float = DEFAULT_MIN_POSITIVE_SLICE_RATE,
) -> dict[str, Any]:
    """Combine forward evidence and CSCV/PBO into one official champion gate."""
    leader = competition.get("leader") or {}
    ranking = competition.get("ranking") or {}
    robots = competition.get("robots") or []
    robot_id = str(leader.get("robot_id") or "")
    robot = next((row for row in robots if str(row.get("robot_id")) == robot_id), None)
    if not robot_id or robot is None:
        raise ValueError("competition leader is missing from robot results")

    forward = robot.get("forward") or {}
    forward_trades = int(forward.get("trade_count") or 0)
    minimum_trades = int(ranking.get("minimum_forward_trades_for_champion") or 0)
    sample_gate = bool(leader.get("qualified")) and forward_trades >= minimum_trades

    matrix = pbo_analysis.get("matrix") or {}
    pbo = pbo_analysis.get("pbo") or {}
    robot_ids = [str(value) for value in matrix.get("robot_ids") or []]
    rows = matrix.get("matrix") or []
    if robot_id not in robot_ids:
        raise ValueError("competition leader is missing from PBO matrix")
    column = robot_ids.index(robot_id)
    values = [float(row[column]) for row in rows if len(row) > column]
    if not values:
        raise ValueError("PBO matrix has no leader performance slices")
    positive_slices = sum(value > 0 for value in values)
    positive_slice_rate = positive_slices / len(values)
    pbo_percent = float(pbo.get("pbo_percent"))
    robustness_gate = (
        pbo_percent <= max_pbo_percent
        and positive_slice_rate >= min_positive_slice_rate
    )

    passed = sample_gate and robustness_gate
    reasons: list[str] = []
    if not sample_gate:
        reasons.append(
            f"forward 樣本不足或未通過原競賽資格：{forward_trades}/{minimum_trades} 筆交易。"
        )
    if pbo_percent > max_pbo_percent:
        reasons.append(f"PBO {pbo_percent:.2f}% 高於門檻 {max_pbo_percent:.2f}%。")
    if positive_slice_rate < min_positive_slice_rate:
        reasons.append(
            f"跨時間正報酬切片率 {positive_slice_rate * 100:.2f}% 低於門檻 {min_positive_slice_rate * 100:.0f}%。"
        )
    if passed:
        reasons.append("同時通過 forward 樣本資格與 CSCV/PBO 跨時間穩健性檢驗。")

    return {
        "robot_id": robot_id,
        "name": robot.get("name") or leader.get("name"),
        "status": "qualified_champion" if passed else "provisional_leader",
        "qualified": passed,
        "forward_sample_gate": {
            "passed": sample_gate,
            "trade_count": forward_trades,
            "minimum_trade_count": minimum_trades,
            "wilson_lower_percent": robot.get("wilson_lower_percent"),
        },
        "cross_time_robustness_gate": {
            "passed": robustness_gate,
            "pbo_percent": round(pbo_percent, 2),
            "maximum_pbo_percent": max_pbo_percent,
            "positive_slice_count": positive_slices,
            "slice_count": len(values),
            "positive_slice_rate_percent": round(positive_slice_rate * 100, 2),
            "minimum_positive_slice_rate_percent": round(min_positive_slice_rate * 100, 2),
        },
        "reasons": reasons,
        "policy": "正式冠軍必須同時通過 forward/Wilson 樣本資格與 CSCV/PBO 跨時間穩健性閘門。",
    }
