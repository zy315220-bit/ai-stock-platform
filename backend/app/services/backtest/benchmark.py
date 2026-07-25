from __future__ import annotations

from typing import Any

import pandas as pd

from .report import _get_row_date
from .trades import (
    _calculate_buy_cost,
    _calculate_purchasable_shares,
    _calculate_sell_value,
)


def _calculate_buy_and_hold(
    df: pd.DataFrame,
    initial_capital: float,
    commission_rate: float,
    transaction_tax_rate: float,
) -> dict[str, Any]:
    """
    計算 Buy & Hold 績效。

    規則：
    - 第一個可用交易日開盤買進
    - 最後一個交易日收盤賣出
    - 計入買進、賣出手續費
    - 計入賣出交易稅
    """

    if df is None or df.empty:
        return {
            "entry_date": "",
            "exit_date": "",
            "entry_price": 0.0,
            "exit_price": 0.0,
            "shares": 0,
            "final_capital": round(initial_capital, 2),
            "profit": 0.0,
            "return_percent": 0.0,
            "entry_commission": 0.0,
            "exit_commission": 0.0,
            "transaction_tax": 0.0,
            "total_transaction_cost": 0.0,
        }

    first_row = df.iloc[0]
    final_row = df.iloc[-1]

    entry_price = float(first_row["Open"])
    exit_price = float(final_row["Close"])

    shares = _calculate_purchasable_shares(
        cash=initial_capital,
        price=entry_price,
        commission_rate=commission_rate,
    )

    if shares <= 0:
        return {
            "entry_date": _get_row_date(first_row),
            "exit_date": _get_row_date(final_row),
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "shares": 0,
            "final_capital": round(initial_capital, 2),
            "profit": 0.0,
            "return_percent": 0.0,
            "entry_commission": 0.0,
            "exit_commission": 0.0,
            "transaction_tax": 0.0,
            "total_transaction_cost": 0.0,
        }

    buy_cost = _calculate_buy_cost(
        price=entry_price,
        shares=shares,
        commission_rate=commission_rate,
    )

    remaining_cash = (
        initial_capital
        - buy_cost["total_cost"]
    )

    sell_result = _calculate_sell_value(
        price=exit_price,
        shares=shares,
        commission_rate=commission_rate,
        transaction_tax_rate=transaction_tax_rate,
    )

    final_capital = (
        remaining_cash
        + sell_result["net_amount"]
    )

    profit = (
        final_capital
        - initial_capital
    )

    return_percent = (
        profit
        / initial_capital
        * 100
        if initial_capital > 0
        else 0.0
    )

    total_transaction_cost = (
        buy_cost["commission"]
        + sell_result["commission"]
        + sell_result["transaction_tax"]
    )

    return {
        "entry_date": _get_row_date(first_row),
        "exit_date": _get_row_date(final_row),
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "shares": shares,
        "final_capital": round(final_capital, 2),
        "profit": round(profit, 2),
        "return_percent": round(return_percent, 2),
        "entry_commission": round(
            buy_cost["commission"],
            2,
        ),
        "exit_commission": round(
            sell_result["commission"],
            2,
        ),
        "transaction_tax": round(
            sell_result["transaction_tax"],
            2,
        ),
        "total_transaction_cost": round(
            total_transaction_cost,
            2,
        ),
    }