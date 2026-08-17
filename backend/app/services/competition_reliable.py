from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

from app.services import competition_runner as legacy

DEFAULT_INITIAL_CAPITAL = legacy.DEFAULT_INITIAL_CAPITAL
MAX_INITIAL_CAPITAL = legacy.MAX_INITIAL_CAPITAL

_ORIGINAL_SIMULATE_SYMBOL = legacy._simulate_symbol


def _remove_synthetic_segment_end_exit(result: dict[str, Any]) -> dict[str, Any]:
    """Convert reporting-boundary liquidations back into open mark-to-market holdings."""
    trades = list(result.get("trades") or [])
    boundary_trades = [trade for trade in trades if trade.get("exit_reason") == "segment_end"]
    if not boundary_trades:
        result["open_positions"] = []
        return result

    open_positions: list[dict[str, Any]] = []
    commission_reversal = 0.0
    tax_reversal = 0.0

    for trade in boundary_trades:
        exit_commission = float(trade.get("exit_commission") or 0.0)
        transaction_tax = float(trade.get("transaction_tax") or 0.0)
        shares = int(trade.get("shares") or 0)
        mark_price = float(trade.get("exit_price") or 0.0)
        market_value = shares * mark_price
        unrealized_profit = float(trade.get("profit") or 0.0) + exit_commission + transaction_tax
        commission_reversal += exit_commission
        tax_reversal += transaction_tax
        open_positions.append(
            {
                "robot_id": trade.get("robot_id"),
                "stock_code": trade.get("stock_code"),
                "segment": trade.get("segment"),
                "entry_date": trade.get("entry_date"),
                "entry_price": trade.get("entry_price"),
                "shares": shares,
                "mark_price": round(mark_price, 4),
                "market_value": round(market_value, 2),
                "unrealized_profit": round(unrealized_profit, 2),
                "entry_reason": trade.get("entry_reason"),
                "entry_commission": trade.get("entry_commission"),
                "stop_price": trade.get("stop_price"),
                "target_price": trade.get("target_price"),
                "valuation": "mark_to_market",
            }
        )

    result["trades"] = [trade for trade in trades if trade.get("exit_reason") != "segment_end"]
    result["open_positions"] = open_positions
    result["final_capital"] = round(float(result["final_capital"]) + commission_reversal + tax_reversal, 2)
    result["total_commission"] = round(max(0.0, float(result["total_commission"]) - commission_reversal), 2)
    result["total_transaction_tax"] = round(max(0.0, float(result["total_transaction_tax"]) - tax_reversal), 2)
    equity_curve = result.get("equity_curve") or []
    if equity_curve:
        equity_curve[-1]["equity"] = round(float(equity_curve[-1]["equity"]) + commission_reversal + tax_reversal, 2)
    return result


def _simulate_symbol_mark_to_market(**kwargs: Any) -> dict[str, Any]:
    return _remove_synthetic_segment_end_exit(_ORIGINAL_SIMULATE_SYMBOL(**kwargs))


def run_competition_on_frames(
    frames: dict[str, Any],
    *,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    sources: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the existing fixed strategies while excluding synthetic boundary exits from win rate."""
    previous = legacy._simulate_symbol
    legacy._simulate_symbol = _simulate_symbol_mark_to_market
    try:
        result = legacy.run_competition_on_frames(
            frames,
            initial_capital=initial_capital,
            sources=sources,
        )
    finally:
        legacy._simulate_symbol = previous

    result.setdefault("disclosures", []).append(
        "區間結束時仍持有的部位採收盤價 mark-to-market；不建立人工賣出交易，因此不計入勝率或 Wilson 樣本。"
    )
    result.setdefault("fairness", {})["segment_end_policy"] = "mark_to_market_open_position"
    return result


@lru_cache(maxsize=8)
def _run_competition_cached(initial_capital: float, cache_date: str) -> dict[str, Any]:
    frames, sources = legacy._download_competition_frames()
    return run_competition_on_frames(frames, initial_capital=initial_capital, sources=sources)


def run_competition(initial_capital: float = DEFAULT_INITIAL_CAPITAL) -> dict[str, Any]:
    capital = round(float(initial_capital), 2)
    return _run_competition_cached(capital, date.today().isoformat())
