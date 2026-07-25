from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _calculate_performance_metrics(
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    initial_capital: float,
    final_capital: float,
    actual_start_date: str,
    actual_end_date: str,
    max_drawdown_percent: float,
) -> dict[str, Any]:
    """
    計算回測常用績效指標：

    - CAGR
    - Sharpe Ratio
    - Sortino Ratio
    - Calmar Ratio
    - Profit Factor
    - 平均／最佳／最差單筆報酬
    - 平均持有天數
    """

    empty_result = {
        "cagr_percent": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "calmar_ratio": 0.0,
        "profit_factor": None,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "average_trade_return_percent": 0.0,
        "best_trade_return_percent": 0.0,
        "worst_trade_return_percent": 0.0,
        "average_holding_days": 0.0,
    }

    if not equity_curve:
        return empty_result

    # ==============================================
    # CAGR
    # ==============================================

    try:
        start_timestamp = pd.Timestamp(
            actual_start_date
        )

        end_timestamp = pd.Timestamp(
            actual_end_date
        )
    except (TypeError, ValueError):
        start_timestamp = pd.NaT
        end_timestamp = pd.NaT

    if (
        pd.isna(start_timestamp)
        or pd.isna(end_timestamp)
    ):
        elapsed_years = 0.0
    else:
        elapsed_days = max(
            (
                end_timestamp
                - start_timestamp
            ).days,
            1,
        )

        elapsed_years = (
            elapsed_days
            / 365.25
        )

    if (
        initial_capital > 0
        and final_capital > 0
        and elapsed_years > 0
    ):
        cagr = (
            (
                final_capital
                / initial_capital
            )
            ** (1 / elapsed_years)
            - 1
        )
    else:
        cagr = 0.0

    cagr_percent = (
        cagr * 100
    )

    # ==============================================
    # 日報酬、Sharpe、Sortino
    # ==============================================

    equity_values = []

    for point in equity_curve:
        try:
            value = float(
                point.get(
                    "equity",
                    0.0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if (
            math.isfinite(value)
            and value > 0
        ):
            equity_values.append(
                value
            )

    equity_series = pd.Series(
        equity_values,
        dtype="float64",
    )

    daily_returns = (
        equity_series
        .pct_change()
        .replace(
            [
                float("inf"),
                float("-inf"),
            ],
            pd.NA,
        )
        .dropna()
        .astype(float)
    )

    sharpe_ratio = 0.0
    sortino_ratio = 0.0

    if not daily_returns.empty:
        mean_daily_return = float(
            daily_returns.mean()
        )

        daily_std = float(
            daily_returns.std(
                ddof=1
            )
        )

        if (
            math.isfinite(daily_std)
            and daily_std > 0
        ):
            sharpe_ratio = (
                mean_daily_return
                / daily_std
                * math.sqrt(252)
            )

        downside_returns = (
            daily_returns.clip(
                upper=0
            )
        )

        downside_deviation = float(
            (
                downside_returns
                .pow(2)
                .mean()
            )
            ** 0.5
        )

        if (
            math.isfinite(
                downside_deviation
            )
            and downside_deviation > 0
        ):
            sortino_ratio = (
                mean_daily_return
                / downside_deviation
                * math.sqrt(252)
            )

    # ==============================================
    # Calmar Ratio
    # ==============================================

    calmar_ratio = (
        cagr_percent
        / max_drawdown_percent
        if max_drawdown_percent > 0
        else 0.0
    )

    # ==============================================
    # 交易統計
    # ==============================================

    trade_returns: list[float] = []
    profits: list[float] = []
    holding_days: list[int] = []

    for trade in trades:
        try:
            trade_return = float(
                trade.get(
                    "return_percent",
                    0.0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            trade_return = 0.0

        if math.isfinite(
            trade_return
        ):
            trade_returns.append(
                trade_return
            )

        try:
            profit = float(
                trade.get(
                    "profit",
                    0.0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            profit = 0.0

        if math.isfinite(profit):
            profits.append(profit)

        existing_holding_days = (
            trade.get(
                "holding_days"
            )
        )

        if (
            existing_holding_days
            is not None
        ):
            try:
                days = int(
                    existing_holding_days
                )
            except (
                TypeError,
                ValueError,
            ):
                days = 0

            holding_days.append(
                max(days, 0)
            )

            continue

        entry_date = trade.get(
            "entry_date"
        )

        exit_date = trade.get(
            "exit_date"
        )

        if entry_date and exit_date:
            try:
                days = (
                    pd.Timestamp(
                        exit_date
                    )
                    - pd.Timestamp(
                        entry_date
                    )
                ).days
            except (
                TypeError,
                ValueError,
            ):
                continue

            holding_days.append(
                max(days, 0)
            )

    gross_profit = sum(
        profit
        for profit in profits
        if profit > 0
    )

    gross_loss = abs(
        sum(
            profit
            for profit in profits
            if profit < 0
        )
    )

    if gross_loss > 0:
        profit_factor: (
            float | None
        ) = (
            gross_profit
            / gross_loss
        )

    elif gross_profit > 0:
        # 只有獲利交易，沒有虧損交易，
        # Profit Factor 理論上趨近無限。
        # JSON 不宜回傳 Infinity，因此使用 None。
        profit_factor = None

    else:
        profit_factor = 0.0

    average_trade_return = (
        sum(trade_returns)
        / len(trade_returns)
        if trade_returns
        else 0.0
    )

    best_trade_return = (
        max(trade_returns)
        if trade_returns
        else 0.0
    )

    worst_trade_return = (
        min(trade_returns)
        if trade_returns
        else 0.0
    )

    average_holding_days = (
        sum(holding_days)
        / len(holding_days)
        if holding_days
        else 0.0
    )

    return {
        "cagr_percent": round(
            cagr_percent,
            2,
        ),
        "sharpe_ratio": round(
            sharpe_ratio,
            3,
        ),
        "sortino_ratio": round(
            sortino_ratio,
            3,
        ),
        "calmar_ratio": round(
            calmar_ratio,
            3,
        ),
        "profit_factor": (
            round(
                profit_factor,
                3,
            )
            if profit_factor is not None
            else None
        ),
        "gross_profit": round(
            gross_profit,
            2,
        ),
        "gross_loss": round(
            gross_loss,
            2,
        ),
        "average_trade_return_percent": round(
            average_trade_return,
            2,
        ),
        "best_trade_return_percent": round(
            best_trade_return,
            2,
        ),
        "worst_trade_return_percent": round(
            worst_trade_return,
            2,
        ),
        "average_holding_days": round(
            average_holding_days,
            2,
        ),
    }