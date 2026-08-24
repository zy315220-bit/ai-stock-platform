from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.services.history_policy import BACKTEST_WARMUP_MONTHS, RESEARCH_HISTORY_MONTHS, default_research_start_date
from app.services.research_history import frame_coverage
from indicators import add_indicators
from score_engine.calculate import calculate_score
from stock import download_stock

from .benchmark import _calculate_buy_and_hold
from .corporate_action_adapter import ledger_schedule_from_frame
from .corporate_action_execution import apply_session_corporate_actions
from .corporate_action_gate import prepare_research_frame, research_metadata
from .drawdown import _calculate_drawdown_statistics, _calculate_max_drawdown
from .metrics import _calculate_performance_metrics
from .report import _extract_score, _get_row_date, _prepare_stock_data
from .trades import (
    COMMISSION_RATE, ETF_TRANSACTION_TAX_RATE, _calculate_advanced_trade_statistics,
    _calculate_buy_cost, _calculate_exposure_percent, _calculate_purchasable_shares,
    _calculate_sell_value, _enrich_trades_with_excursions,
)

MAX_INITIAL_CAPITAL = 2_000_000
BACKTEST_REQUIRED_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume", "EMA20", "EMA60", "ATR"]


def _download_backtest_history(stock_code: str, *, required_start_date: str, required_end_date: str | None) -> pd.DataFrame:
    required_start = pd.Timestamp(required_start_date).normalize()
    required_end = pd.Timestamp(required_end_date or pd.Timestamp.today()).normalize()
    attempts = (
        {"prefer_official": False, "daily_period": "10y", "force_official_refresh": False},
        {"prefer_official": True, "daily_period": "max", "force_official_refresh": True},
    )
    best_frame = pd.DataFrame(); best_key = None; initial_rows = 0; errors: list[str] = []
    for attempt_index, options in enumerate(attempts):
        try:
            candidate = download_stock(stock_code, prefer_official=bool(options["prefer_official"]), daily_period=str(options["daily_period"]), update_with_intraday=False, official_months=RESEARCH_HISTORY_MONTHS + BACKTEST_WARMUP_MONTHS, force_official_refresh=bool(options["force_official_refresh"]), include_corporate_actions=True)
        except Exception as error:
            errors.append(str(error)); continue
        if attempt_index == 0: initial_rows = len(candidate) if candidate is not None else 0
        if candidate is None or candidate.empty: continue
        coverage = frame_coverage(candidate); actual_start = pd.Timestamp(candidate.index.min()).normalize(); actual_end = pd.Timestamp(candidate.index.max()).normalize()
        covers_start = actual_start <= required_start; covers_end = actual_end >= required_end - pd.Timedelta(days=10); complete_months = bool(coverage["complete_month_coverage"]); covers_requested_span = covers_start and covers_end and complete_months
        key = (int(covers_requested_span), int(complete_months), int(covers_end), -int(actual_start.value), int(actual_end.value), len(candidate))
        if best_key is None or key > best_key: best_key = key; best_frame = candidate
        if covers_requested_span:
            candidate.attrs["history_recovery"] = {"recovered": attempt_index > 0, "attempts": attempt_index + 1, "initial_rows": initial_rows, "final_rows": len(candidate), "method": "long_history" if attempt_index == 0 else "official_refresh"}
            return candidate
    if not best_frame.empty:
        best_frame.attrs["history_recovery"] = {"recovered": len(attempts) > 1, "attempts": len(attempts), "initial_rows": initial_rows, "final_rows": len(best_frame), "method": "best_available"}; return best_frame
    detail = "；".join(message for message in errors if message); raise ValueError(detail or f"找不到 {stock_code} 的歷史資料。")


def backtest_stock(stock_code: str, start_date: str | None = None, end_date: str | None = None, entry_score: float = 75, exit_score: float = 55, initial_capital: float = 100_000, commission_rate: float = COMMISSION_RATE, transaction_tax_rate: float = ETF_TRANSACTION_TAX_RATE) -> dict[str, Any]:
    normalized_code = stock_code.strip().upper()
    if not normalized_code: raise ValueError("股票代號不能空白。")
    normalized_capital = float(initial_capital)
    if not math.isfinite(normalized_capital) or normalized_capital <= 0: raise ValueError("初始資金必須大於 0。")
    if normalized_capital > MAX_INITIAL_CAPITAL: raise ValueError("初始資金不能超過 2,000,000 元。")
    if entry_score <= exit_score: raise ValueError("進場分數必須高於出場分數。")
    if not 0 <= commission_rate < 1: raise ValueError("手續費率必須介於 0 到 1 之間。")
    if not 0 <= transaction_tax_rate < 1: raise ValueError("交易稅率必須介於 0 到 1 之間。")

    effective_start_date = start_date or default_research_start_date().isoformat()
    warmup_start_date = (pd.Timestamp(effective_start_date) - pd.DateOffset(months=BACKTEST_WARMUP_MONTHS)).strftime("%Y-%m-%d")
    df = _download_backtest_history(normalized_code, required_start_date=warmup_start_date, required_end_date=end_date)
    if df is None or df.empty: raise ValueError(f"找不到 {normalized_code} 的歷史資料。")
    df = prepare_research_frame(df, normalized_code)
    data_source = str(df.attrs.get("source", "未知")); history_recovery = dict(df.attrs.get("history_recovery", {}))
    corporate_action_attrs = dict(df.attrs)
    corporate_action_metadata = research_metadata(df)
    df = _prepare_stock_data(df=df, start_date=warmup_start_date, end_date=end_date); df = add_indicators(df.copy())
    if df is None or df.empty: raise ValueError("技術指標計算後沒有可用資料。")
    df = df.dropna(subset=BACKTEST_REQUIRED_COLUMNS).reset_index(drop=True); df.attrs.update(corporate_action_attrs)
    requested_start_timestamp = pd.Timestamp(effective_start_date).normalize(); df = df.loc[df["Date"] >= requested_start_timestamp].reset_index(drop=True); df.attrs.update(corporate_action_attrs)
    if len(df) < 61: raise ValueError("計算技術指標後的歷史資料不足，至少需要約 61 個有效交易日。")

    cash = normalized_capital; shares = 0; entry_price = None; entry_date = None; entry_signal_score = None
    entry_gross_amount = 0.0; entry_commission = 0.0; entry_total_cost = 0.0
    trades: list[dict[str, Any]] = []; equity_curve: list[dict[str, Any]] = []
    total_commission = 0.0; total_transaction_tax = 0.0; total_dividends = 0.0; position_dividends = 0.0
    corporate_action_schedule = ledger_schedule_from_frame(df)

    for index in range(60, len(df) - 1):
        historical_df = df.iloc[: index + 1].copy(); current_row = df.iloc[index]; next_row = df.iloc[index + 1]
        score = _extract_score(calculate_score(historical_df)); next_date = _get_row_date(next_row); next_open = float(next_row["Open"]); next_close = float(next_row["Close"])
        if next_open <= 0: continue

        # Apply official effective-date events before today's opening order. This is
        # now the single production dividend/accounting path; the legacy dividend
        # schedule is intentionally removed to prevent duplicate cash flows.
        previous_cash = cash
        ledger_state = apply_session_corporate_actions(stock_code=normalized_code, date=next_date, shares=shares, cash=cash, total_cost_basis=entry_total_cost if shares > 0 else 0.0, schedule=corporate_action_schedule)
        cash = ledger_state.cash; shares = ledger_state.shares
        ledger_cash_flow = max(0.0, cash - previous_cash)
        if ledger_cash_flow > 0 and shares > 0:
            total_dividends += ledger_cash_flow; position_dividends += ledger_cash_flow

        if shares == 0 and score >= entry_score:
            purchasable_shares = _calculate_purchasable_shares(cash=cash, price=next_open, commission_rate=commission_rate)
            if purchasable_shares > 0:
                buy_cost = _calculate_buy_cost(price=next_open, shares=purchasable_shares, commission_rate=commission_rate); shares = purchasable_shares; cash -= buy_cost["total_cost"]
                entry_price = next_open; entry_date = next_date; entry_signal_score = score; entry_gross_amount = buy_cost["gross_amount"]; entry_commission = buy_cost["commission"]; entry_total_cost = buy_cost["total_cost"]; total_commission += entry_commission
        elif shares > 0 and score <= exit_score:
            sell_result = _calculate_sell_value(price=next_open, shares=shares, commission_rate=commission_rate, transaction_tax_rate=transaction_tax_rate); cash += sell_result["net_amount"]
            exit_commission = sell_result["commission"]; transaction_tax = sell_result["transaction_tax"]; total_commission += exit_commission; total_transaction_tax += transaction_tax
            net_profit = sell_result["net_amount"] + position_dividends - entry_total_cost; return_percent = net_profit / entry_total_cost * 100 if entry_total_cost > 0 else 0.0
            trades.append({"entry_date": entry_date, "exit_date": next_date, "entry_price": round(entry_price or 0, 2), "exit_price": round(next_open, 2), "shares": shares, "entry_gross_amount": round(entry_gross_amount, 2), "entry_commission": round(entry_commission, 2), "entry_total_cost": round(entry_total_cost, 2), "exit_gross_amount": round(sell_result["gross_amount"], 2), "exit_commission": round(exit_commission, 2), "transaction_tax": round(transaction_tax, 2), "exit_net_amount": round(sell_result["net_amount"], 2), "profit": round(net_profit, 2), "return_percent": round(return_percent, 2), "entry_score": round(entry_signal_score, 2) if entry_signal_score is not None else None, "exit_score": round(score, 2), "exit_reason": "score_below_exit_threshold", "dividends": round(position_dividends, 2)})
            shares = 0; entry_price = None; entry_date = None; entry_signal_score = None; entry_gross_amount = 0.0; entry_commission = 0.0; entry_total_cost = 0.0; position_dividends = 0.0
        equity = cash + shares * next_close
        equity_curve.append({"date": next_date, "equity": round(equity, 2), "cash": round(cash, 2), "shares": shares, "close": round(next_close, 2), "score": round(score, 2)})

    if shares > 0:
        final_row = df.iloc[-1]; final_close = float(final_row["Close"]); final_date = _get_row_date(final_row)
        sell_result = _calculate_sell_value(price=final_close, shares=shares, commission_rate=commission_rate, transaction_tax_rate=transaction_tax_rate); cash += sell_result["net_amount"]
        exit_commission = sell_result["commission"]; transaction_tax = sell_result["transaction_tax"]; total_commission += exit_commission; total_transaction_tax += transaction_tax
        net_profit = sell_result["net_amount"] + position_dividends - entry_total_cost; return_percent = net_profit / entry_total_cost * 100 if entry_total_cost > 0 else 0.0
        trades.append({"entry_date": entry_date, "exit_date": final_date, "entry_price": round(entry_price or 0, 2), "exit_price": round(final_close, 2), "shares": shares, "entry_gross_amount": round(entry_gross_amount, 2), "entry_commission": round(entry_commission, 2), "entry_total_cost": round(entry_total_cost, 2), "exit_gross_amount": round(sell_result["gross_amount"], 2), "exit_commission": round(exit_commission, 2), "transaction_tax": round(transaction_tax, 2), "exit_net_amount": round(sell_result["net_amount"], 2), "profit": round(net_profit, 2), "return_percent": round(return_percent, 2), "entry_score": round(entry_signal_score, 2) if entry_signal_score is not None else None, "exit_score": None, "exit_reason": "end_of_backtest", "dividends": round(position_dividends, 2)})
        shares = 0
        if equity_curve: equity_curve[-1].update({"equity": round(cash, 2), "cash": round(cash, 2), "shares": 0})

    final_capital = float(cash); total_profit = final_capital - initial_capital; total_return = total_profit / initial_capital * 100
    winning_trades = [trade for trade in trades if float(trade["profit"]) > 0]; win_rate = len(winning_trades) / len(trades) * 100 if trades else 0.0
    max_drawdown = _calculate_max_drawdown(equity_curve); actual_start_date = _get_row_date(df.iloc[0]); actual_end_date = _get_row_date(df.iloc[-1]); history_coverage = frame_coverage(df.set_index("Date"))
    buy_and_hold = _calculate_buy_and_hold(df=df, initial_capital=initial_capital, commission_rate=commission_rate, transaction_tax_rate=transaction_tax_rate); buy_and_hold_return = float(buy_and_hold.get("return_percent", 0.0)); alpha_percent = total_return - buy_and_hold_return
    _enrich_trades_with_excursions(df=df, trades=trades); exposure_percent = _calculate_exposure_percent(equity_curve); drawdown_statistics = _calculate_drawdown_statistics(equity_curve)
    advanced_trade_statistics = _calculate_advanced_trade_statistics(trades=trades, initial_capital=initial_capital, final_capital=final_capital, max_drawdown_percent=max_drawdown, exposure_percent=exposure_percent)
    performance_metrics = _calculate_performance_metrics(equity_curve=equity_curve, trades=trades, initial_capital=initial_capital, final_capital=final_capital, actual_start_date=actual_start_date, actual_end_date=actual_end_date, max_drawdown_percent=max_drawdown)
    return {"stock_code": normalized_code, "data_source": data_source, "requested_start_date": effective_start_date, "requested_end_date": end_date, "actual_start_date": actual_start_date, "actual_end_date": actual_end_date, "history_coverage": history_coverage, "history_recovery": history_recovery, "requested_history_months": RESEARCH_HISTORY_MONTHS, "entry_score": entry_score, "exit_score": exit_score, "commission_rate": commission_rate, "transaction_tax_rate": transaction_tax_rate, "initial_capital": round(initial_capital, 2), "final_capital": round(final_capital, 2), "total_profit": round(total_profit, 2), "total_return_percent": round(total_return, 2), "total_commission": round(total_commission, 2), "total_transaction_tax": round(total_transaction_tax, 2), "total_dividends": round(total_dividends, 2), "corporate_actions": {**corporate_action_metadata, "split_adjustments": corporate_action_attrs.get("split_adjustments", []), "dividend_source": corporate_action_attrs.get("dividend_source"), "dividend_event_count": len(corporate_action_attrs.get("dividends", [])), "event_count": len(corporate_action_attrs.get("corporate_action_events", [])), "resolution_count": len(corporate_action_attrs.get("corporate_action_resolutions", [])), "accounting_path": "event-ledger-v1"}, "total_transaction_cost": round(total_commission + total_transaction_tax, 2), "trade_count": len(trades), "winning_trade_count": len(winning_trades), "win_rate_percent": round(win_rate, 2), "max_drawdown_percent": round(max_drawdown, 2), "buy_and_hold": buy_and_hold, "alpha_percent": round(alpha_percent, 2), "performance_metrics": performance_metrics, "advanced_trade_statistics": advanced_trade_statistics, "drawdown_statistics": drawdown_statistics, "exposure_percent": round(exposure_percent, 2), "trades": trades, "equity_curve": equity_curve}
