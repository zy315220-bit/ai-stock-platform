from __future__ import annotations

from typing import Any


def mark_open_position_at_segment_end(
    *,
    cash: float,
    shares: int,
    close_price: float,
    entry_price: float | None,
    entry_date: str | None,
    entry_reason: str,
    entry_total_cost: float,
    entry_commission: float,
    stop_price: float | None,
    target_price: float | None,
) -> tuple[float, dict[str, Any] | None]:
    """Value an open position without fabricating a completed sell trade.

    Segment boundaries are reporting boundaries, not executable strategy signals.
    Therefore an open holding contributes to ending equity at the observed close,
    but does not create an exit, commission, transaction tax, win/loss, or trade.
    """
    if shares <= 0:
        return float(cash), None
    if close_price <= 0:
        raise ValueError("close_price must be positive for an open position")

    market_value = shares * close_price
    final_equity = float(cash) + market_value
    unrealized_profit = final_equity - float(cash) - float(entry_total_cost)
    open_position = {
        "entry_date": entry_date,
        "entry_price": round(entry_price or 0.0, 4),
        "shares": int(shares),
        "mark_price": round(close_price, 4),
        "market_value": round(market_value, 2),
        "unrealized_profit": round(unrealized_profit, 2),
        "unrealized_return_percent": round(
            unrealized_profit / entry_total_cost * 100 if entry_total_cost else 0.0,
            4,
        ),
        "entry_reason": entry_reason,
        "entry_commission": round(entry_commission, 2),
        "stop_price": round(stop_price or 0.0, 4),
        "target_price": round(target_price or 0.0, 4),
        "valuation": "mark_to_market",
    }
    return final_equity, open_position
