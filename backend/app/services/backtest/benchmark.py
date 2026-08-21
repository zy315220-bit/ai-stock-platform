from __future__ import annotations

from typing import Any

import pandas as pd

from corporate_actions import dividends_by_ex_date

from .report import _get_row_date
from .trades import (
    _calculate_buy_cost,
    _calculate_purchasable_shares,
    _calculate_sell_value,
)


def _require_split_safe_basis(df: pd.DataFrame) -> None:
    """Never publish a benchmark from an unverified/raw split price basis."""
    split_adjusted = df.attrs.get("split_adjusted")
    price_basis = str(df.attrs.get("price_basis") or "").strip().lower()
    split_adjustments = df.attrs.get("split_adjustments")
    safe_basis = split_adjusted is True or "split_adjusted" in price_basis
    # Official/raw data are acceptable only after the normalizer has explicitly
    # left an audit trail (including an empty list after validation).
    if not safe_basis and split_adjustments is not None:
        safe_basis = True
    if not safe_basis:
        raise ValueError(
            "研究價格基準未通過拆分驗證，拒絕計算同期持有報酬，"
            "避免股票分割/反向分割污染研究結果。"
        )


def _calculate_buy_and_hold(
    df: pd.DataFrame,
    initial_capital: float,
    commission_rate: float,
    transaction_tax_rate: float,
) -> dict[str, Any]:
    """Buy & Hold on a corporate-action-validated price basis."""
    if df is None or df.empty:
        return {
            "entry_date": "", "exit_date": "", "entry_price": 0.0,
            "exit_price": 0.0, "shares": 0,
            "final_capital": round(initial_capital, 2), "profit": 0.0,
            "return_percent": 0.0, "entry_commission": 0.0,
            "exit_commission": 0.0, "transaction_tax": 0.0,
            "total_transaction_cost": 0.0, "total_dividends": 0.0,
            "dividend_per_share": 0.0,
            "return_basis": "split_adjusted_total_return",
        }

    _require_split_safe_basis(df)
    first_row = df.iloc[0]
    final_row = df.iloc[-1]
    entry_price = float(first_row["Open"])
    exit_price = float(final_row["Close"])
    shares = _calculate_purchasable_shares(
        cash=initial_capital, price=entry_price, commission_rate=commission_rate
    )
    if shares <= 0:
        return {
            "entry_date": _get_row_date(first_row),
            "exit_date": _get_row_date(final_row),
            "entry_price": round(entry_price, 2), "exit_price": round(exit_price, 2),
            "shares": 0, "final_capital": round(initial_capital, 2), "profit": 0.0,
            "return_percent": 0.0, "entry_commission": 0.0,
            "exit_commission": 0.0, "transaction_tax": 0.0,
            "total_transaction_cost": 0.0, "total_dividends": 0.0,
            "dividend_per_share": 0.0,
            "return_basis": "split_adjusted_total_return",
        }

    buy_cost = _calculate_buy_cost(entry_price, shares, commission_rate)
    remaining_cash = initial_capital - buy_cost["total_cost"]
    sell_result = _calculate_sell_value(
        exit_price, shares, commission_rate, transaction_tax_rate
    )
    entry_date = pd.Timestamp(_get_row_date(first_row))
    exit_date = pd.Timestamp(_get_row_date(final_row))
    dividend_per_share = sum(
        amount for event_date, amount in dividends_by_ex_date(df).items()
        if entry_date < pd.Timestamp(event_date) <= exit_date
    )
    total_dividends = shares * dividend_per_share
    final_capital = remaining_cash + sell_result["net_amount"] + total_dividends
    profit = final_capital - initial_capital
    return_percent = profit / initial_capital * 100 if initial_capital > 0 else 0.0
    total_transaction_cost = (
        buy_cost["commission"] + sell_result["commission"] + sell_result["transaction_tax"]
    )
    return {
        "entry_date": _get_row_date(first_row), "exit_date": _get_row_date(final_row),
        "entry_price": round(entry_price, 2), "exit_price": round(exit_price, 2),
        "shares": shares, "final_capital": round(final_capital, 2),
        "profit": round(profit, 2), "return_percent": round(return_percent, 2),
        "entry_commission": round(buy_cost["commission"], 2),
        "exit_commission": round(sell_result["commission"], 2),
        "transaction_tax": round(sell_result["transaction_tax"], 2),
        "total_transaction_cost": round(total_transaction_cost, 2),
        "total_dividends": round(total_dividends, 2),
        "dividend_per_share": round(dividend_per_share, 6),
        "return_basis": "split_adjusted_total_return",
    }
