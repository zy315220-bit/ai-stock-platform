from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd

from indicators import add_indicators
from score_engine.calculate import calculate_score
from stock import download_stock

from .benchmark import _calculate_buy_and_hold
from .drawdown import _calculate_drawdown_statistics, _calculate_max_drawdown
from .metrics import _calculate_performance_metrics
from .report import _extract_score, _get_row_date, _prepare_stock_data
from .trades import (
    COMMISSION_RATE,
    ETF_TRANSACTION_TAX_RATE,
    _calculate_advanced_trade_statistics,
    _calculate_buy_cost,
    _calculate_exposure_percent,
    _calculate_purchasable_shares,
    _calculate_sell_value,
    _enrich_trades_with_excursions,
)

MAX_INITIAL_CAPITAL = 2_000_000
INDICATOR_WARMUP_CALENDAR_DAYS = 180


def _official_months_for_backtest(start_date: str) -> int:
    try:
        start = pd.Timestamp(start_date).date()
    except (TypeError, ValueError):
        return 10
    today = date.today()
    months = (today.year - start.year) * 12 + today.month - start.month + 8
    return max(10, min(months, 240))


def backtest_stock(stock_code: str, start_date: str = "2023-01-01", end_date: str | None = None, entry_score: float = 75, exit_score: float = 55, initial_capital: float = 100_000, commission_rate: float = COMMISSION_RATE, transaction_tax_rate: float = ETF_TRANSACTION_TAX_RATE) -> dict[str, Any]:
    normalized_code = stock_code.strip().upper()
    if not normalized_code:
        raise ValueError("股票代號不能空白。")
    normalized_capital = float(initial_capital)
    if not math.isfinite(normalized_capital) or normalized_capital <= 0:
        raise ValueError("初始資金必須大於 0。")
    if normalized_capital > MAX_INITIAL_CAPITAL:
        raise ValueError("初始資金不能超過 2,000,000 元。")
    if entry_score <= exit_score:
        raise ValueError("進場分數必須高於出場分數。")
    if not (0 <= commission_rate < 1) or not (0 <= transaction_tax_rate < 1):
        raise ValueError("交易成本率必須介於 0 到 1 之間。")

    requested_start = pd.Timestamp(start_date).normalize()
    warmup_start = (requested_start - pd.Timedelta(days=INDICATOR_WARMUP_CALENDAR_DAYS)).date().isoformat()
    df = download_stock(normalized_code, prefer_official=True, official_months=_official_months_for_backtest(warmup_start))
    data_source = str(df.attrs.get("source", "未知"))
    if df is None or df.empty:
        raise ValueError(f"找不到 {normalized_code} 的歷史資料。")
    df = _prepare_stock_data(df=df, start_date=warmup_start, end_date=end_date)
    df = add_indicators(df.copy())
    if df is None or df.empty:
        raise ValueError("技術指標計算後沒有可用資料。")
    df = df.dropna().reset_index(drop=True)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    trade_start_index = df.index[df["Date"] >= requested_start]
    if len(trade_start_index) == 0:
        raise ValueError(f"指定開始日期 {start_date} 之後沒有可交易歷史資料。")
    first_trade_index = int(trade_start_index[0])
    if len(df) - first_trade_index < 2:
        raise ValueError("指定交易區間的有效歷史資料不足。")

    cash, shares = normalized_capital, 0
    entry_price = entry_date = entry_signal_score = None
    entry_gross_amount = entry_commission = entry_total_cost = 0.0
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    total_commission = total_transaction_tax = 0.0

    for index in range(first_trade_index, len(df) - 1):
        historical_df = df.iloc[: index + 1].copy()
        current_row, next_row = df.iloc[index], df.iloc[index + 1]
        score = _extract_score(calculate_score(historical_df))
        signal_date, next_date = _get_row_date(current_row), _get_row_date(next_row)
        next_open = float(next_row["Open"])
        if shares == 0 and score >= entry_score:
            purchasable_shares = _calculate_purchasable_shares(cash, next_open, commission_rate)
            if purchasable_shares > 0:
                buy_cost = _calculate_buy_cost(purchasable_shares, next_open, commission_rate)
                shares = purchasable_shares
                cash -= buy_cost["total_cost"]
                entry_price, entry_date, entry_signal_score = next_open, next_date, score
                entry_gross_amount, entry_commission, entry_total_cost = buy_cost["gross_amount"], buy_cost["commission"], buy_cost["total_cost"]
                total_commission += entry_commission
        elif shares > 0 and score <= exit_score:
            sell_value = _calculate_sell_value(shares, next_open, commission_rate, transaction_tax_rate)
            cash += sell_value["net_amount"]
            total_commission += sell_value["commission"]
            total_transaction_tax += sell_value["transaction_tax"]
            trades.append({"entry_date": entry_date, "exit_date": next_date, "entry_price": entry_price, "exit_price": next_open, "shares": shares, "entry_signal_score": entry_signal_score, "exit_signal_score": score, "entry_gross_amount": entry_gross_amount, "entry_commission": entry_commission, "entry_total_cost": entry_total_cost, "exit_gross_amount": sell_value["gross_amount"], "exit_commission": sell_value["commission"], "transaction_tax": sell_value["transaction_tax"], "exit_net_value": sell_value["net_amount"], "profit": sell_value["net_amount"] - entry_total_cost})
            shares = 0
            entry_price = entry_date = entry_signal_score = None
            entry_gross_amount = entry_commission = entry_total_cost = 0.0
        current_close = float(current_row["Close"])
        equity_curve.append({"date": signal_date, "equity": cash + shares * current_close, "cash": cash, "shares": shares, "close": current_close})

    final_close = float(df.iloc[-1]["Close"])
    final_date = _get_row_date(df.iloc[-1])
    final_equity = cash + shares * final_close
    equity_curve.append({"date": final_date, "equity": final_equity, "cash": cash, "shares": shares, "close": final_close})
    trade_df = df.iloc[first_trade_index:].reset_index(drop=True)
    enriched_trades = _enrich_trades_with_excursions(trades=trades, df=trade_df)
    max_drawdown = _calculate_max_drawdown(equity_curve)
    drawdown_statistics = _calculate_drawdown_statistics(equity_curve)
    performance_metrics = _calculate_performance_metrics(equity_curve=equity_curve, trades=enriched_trades, initial_capital=normalized_capital, final_capital=final_equity, actual_start_date=_get_row_date(trade_df.iloc[0]), actual_end_date=final_date, max_drawdown_percent=abs(max_drawdown))
    advanced_trade_statistics = _calculate_advanced_trade_statistics(enriched_trades)
    buy_and_hold = _calculate_buy_and_hold(df=trade_df, initial_capital=normalized_capital, commission_rate=commission_rate, transaction_tax_rate=transaction_tax_rate)
    exposure_percent = _calculate_exposure_percent(equity_curve)
    total_return_percent = (final_equity / normalized_capital - 1) * 100
    return {"stock_code": normalized_code, "data_source": data_source, "start_date": start_date, "end_date": end_date, "initial_capital": normalized_capital, "final_equity": final_equity, "total_return_percent": total_return_percent, "max_drawdown_percent": max_drawdown, "total_trades": len(enriched_trades), "total_commission": total_commission, "total_transaction_tax": total_transaction_tax, "exposure_percent": exposure_percent, "performance_metrics": performance_metrics, "advanced_trade_statistics": advanced_trade_statistics, "drawdown_statistics": drawdown_statistics, "buy_and_hold": buy_and_hold, "trades": enriched_trades, "equity_curve": equity_curve}
