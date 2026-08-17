from __future__ import annotations

from typing import Any

import pandas as pd

from app.services import competition_runner as legacy
from app.services.competition_reliable import _simulate_symbol_mark_to_market
from app.services.cscv_matrix import PerformanceSlice, build_performance_matrix
from app.services.trading_costs import TAIWAN_ETF_COST_MODEL

DEFAULT_SLICE_MONTHS = 1
MIN_HISTORY_SLICES = 4


def _month_slices(
    frames: dict[str, pd.DataFrame],
    *,
    slice_months: int = DEFAULT_SLICE_MONTHS,
    max_slices: int = 12,
) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    if slice_months <= 0:
        raise ValueError("slice_months must be positive")
    if max_slices < MIN_HISTORY_SLICES:
        raise ValueError(f"max_slices must be at least {MIN_HISTORY_SLICES}")
    latest = min(pd.Timestamp(frames[code].index.max()).normalize() for code in legacy.COMPETITION_UNIVERSE)
    earliest = max(pd.Timestamp(frames[code].index.min()).normalize() for code in legacy.COMPETITION_UNIVERSE)
    slices: list[tuple[str, pd.Timestamp, pd.Timestamp]] = []
    end = latest
    while len(slices) < max_slices:
        start = (end - pd.DateOffset(months=slice_months) + pd.Timedelta(days=1)).normalize()
        if start < earliest:
            break
        slices.append((f"slice-{start.date()}-{end.date()}", start, end))
        end = (start - pd.Timedelta(days=1)).normalize()
    slices.reverse()
    return slices


def build_historical_performance_matrix(
    frames: dict[str, pd.DataFrame],
    *,
    initial_capital: float = legacy.DEFAULT_INITIAL_CAPITAL,
    slice_months: int = DEFAULT_SLICE_MONTHS,
    max_slices: int = 12,
) -> dict[str, object]:
    """Run every frozen robot on identical non-overlapping historical slices."""
    missing = [code for code in legacy.COMPETITION_UNIVERSE if code not in frames]
    if missing:
        raise ValueError("競賽缺少股票資料：" + "、".join(missing))
    capital = float(initial_capital)
    if capital <= 0 or capital > legacy.MAX_INITIAL_CAPITAL:
        raise ValueError("invalid initial_capital")

    periods = _month_slices(frames, slice_months=slice_months, max_slices=max_slices)
    robot_ids = [str(spec["robot_id"]) for spec in legacy.ROBOT_SPECS]
    per_symbol_capital = capital / len(legacy.COMPETITION_UNIVERSE)
    cost_model = TAIWAN_ETF_COST_MODEL
    performance_slices: list[PerformanceSlice] = []

    for slice_id, start, end in periods:
        robot_returns: dict[str, float] = {}
        for robot_id in robot_ids:
            symbol_results = [
                _simulate_symbol_mark_to_market(
                    frame=frames[code], stock_code=code, robot_id=robot_id,
                    segment="cscv", start=start, end=end,
                    initial_capital=per_symbol_capital,
                    commission_rate=cost_model.commission_rate,
                    transaction_tax_rate=cost_model.transaction_tax_rate,
                )
                for code in legacy.COMPETITION_UNIVERSE
            ]
            portfolio = legacy._aggregate_portfolio(symbol_results, initial_capital=capital)
            robot_returns[robot_id] = float(portfolio["total_return_percent"])
        performance_slices.append(
            PerformanceSlice(
                slice_id=slice_id,
                start=legacy._date_text(start),
                end=legacy._date_text(end),
                robot_returns=robot_returns,
            )
        )

    if len(performance_slices) < MIN_HISTORY_SLICES:
        raise ValueError("insufficient common history for CSCV performance matrix")
    matrix = build_performance_matrix(performance_slices, robot_ids)
    matrix.update({
        "slice_months": slice_months,
        "initial_capital": round(capital, 2),
        "capital_per_symbol": round(per_symbol_capital, 2),
        "market_universe": list(legacy.COMPETITION_UNIVERSE),
        "cost_model_id": cost_model.model_id,
        "execution": "signal at close, execute next session open",
        "source": "real_strategy_simulation_on_common_history",
    })
    return matrix
