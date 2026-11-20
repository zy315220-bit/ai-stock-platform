"""Fixed entry predicates shared by historical execution and daily inference."""

from __future__ import annotations

from typing import Any, Mapping


def entry_predicates(
    row: Mapping[str, Any],
    score: float,
    *,
    entry_score: float,
    require_ema_trend: bool = False,
    ema_fast_column: str = "EMA20",
    ema_slow_column: str = "EMA60",
    entry_mode: str = "score",
) -> dict[str, bool]:
    trend_ok = (
        not require_ema_trend
        or float(row[ema_fast_column]) > float(row[ema_slow_column])
    )
    if entry_mode == "score":
        structure_ok = True
    elif entry_mode == "score_and_rsi_momentum":
        structure_ok = 55.0 <= float(row["RSI"]) <= 80.0
    elif entry_mode == "score_and_bollinger_breakout":
        structure_ok = float(row["Close"]) >= float(row["Upper"])
    elif entry_mode == "score_and_volume_confirmation":
        structure_ok = float(row["VolumeRatio"]) >= 1.2
    elif entry_mode == "mean_reversion_bollinger_rsi":
        structure_ok = (
            float(row["Close"]) <= float(row["Lower"])
            and float(row["RSI"]) <= 35.0
        )
    else:
        raise ValueError(f"Unsupported entry_mode: {entry_mode}")
    return {
        "score_threshold": score >= entry_score,
        "ema_trend": trend_ok,
        "entry_structure": structure_ok,
    }
