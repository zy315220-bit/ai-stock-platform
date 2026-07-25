from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _empty_drawdown_statistics() -> dict[str, Any]:
    return {
        "max_drawdown_percent": 0.0,
        "average_drawdown_percent": 0.0,
        "current_drawdown_percent": 0.0,
        "longest_drawdown_days": 0,
        "longest_drawdown_bars": 0,
        "drawdown_period_count": 0,
    }


def _calculate_drawdown_statistics(
    equity_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    計算完整回撤統計：

    - max_drawdown_percent：
      最大回撤幅度
    - average_drawdown_percent：
      所有處於回撤狀態交易日的平均回撤幅度
    - current_drawdown_percent：
      回測結束時的回撤幅度
    - longest_drawdown_days：
      從前高至恢復前高的最長日曆天數
    - longest_drawdown_bars：
      最長回撤期間內，低於前高的交易日數
    - drawdown_period_count：
      進入回撤狀態的次數
    """

    if not equity_curve:
        return _empty_drawdown_statistics()

    valid_points: list[tuple[pd.Timestamp, float]] = []

    for point in equity_curve:
        try:
            equity = float(
                point.get("equity", 0.0)
            )
            point_date = pd.Timestamp(
                point.get("date")
            )
        except (TypeError, ValueError):
            continue

        if (
            not math.isfinite(equity)
            or pd.isna(point_date)
        ):
            continue

        valid_points.append(
            (point_date, equity)
        )

    if not valid_points:
        return _empty_drawdown_statistics()

    peak_date, peak_equity = valid_points[0]

    drawdowns: list[float] = []

    current_period_start: pd.Timestamp | None = None
    current_period_bars = 0

    longest_drawdown_days = 0
    longest_drawdown_bars = 0
    drawdown_period_count = 0

    for point_date, equity in valid_points:
        if equity >= peak_equity:
            peak_equity = equity
            peak_date = point_date

            if current_period_start is not None:
                period_days = max(
                    (
                        point_date
                        - current_period_start
                    ).days,
                    0,
                )

                longest_drawdown_days = max(
                    longest_drawdown_days,
                    period_days,
                )

                longest_drawdown_bars = max(
                    longest_drawdown_bars,
                    current_period_bars,
                )

                current_period_start = None
                current_period_bars = 0

            drawdown = 0.0

        else:
            drawdown = (
                (
                    peak_equity
                    - equity
                )
                / peak_equity
                * 100
                if peak_equity > 0
                else 0.0
            )

            if current_period_start is None:
                current_period_start = peak_date
                current_period_bars = 1
                drawdown_period_count += 1
            else:
                current_period_bars += 1

        drawdowns.append(
            drawdown
        )

    if current_period_start is not None:
        final_date = valid_points[-1][0]

        period_days = max(
            (
                final_date
                - current_period_start
            ).days,
            0,
        )

        longest_drawdown_days = max(
            longest_drawdown_days,
            period_days,
        )

        longest_drawdown_bars = max(
            longest_drawdown_bars,
            current_period_bars,
        )

    positive_drawdowns = [
        value
        for value in drawdowns
        if value > 0
    ]

    average_drawdown = (
        sum(positive_drawdowns)
        / len(positive_drawdowns)
        if positive_drawdowns
        else 0.0
    )

    return {
        "max_drawdown_percent": round(
            max(drawdowns, default=0.0),
            2,
        ),
        "average_drawdown_percent": round(
            average_drawdown,
            2,
        ),
        "current_drawdown_percent": round(
            drawdowns[-1],
            2,
        ),
        "longest_drawdown_days": int(
            longest_drawdown_days
        ),
        "longest_drawdown_bars": int(
            longest_drawdown_bars
        ),
        "drawdown_period_count": int(
            drawdown_period_count
        ),
    }


def _calculate_max_drawdown(
    equity_curve: list[dict[str, Any]],
) -> float:
    """
    計算最大回撤百分比。
    """

    statistics = _calculate_drawdown_statistics(
        equity_curve
    )

    return float(
        statistics["max_drawdown_percent"]
    )