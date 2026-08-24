from __future__ import annotations

from collections import OrderedDict
from datetime import date
import hashlib
import json
import math
from threading import RLock
from typing import Any

import pandas as pd

from corporate_actions import dividends_by_ex_date
from app.services.history_policy import (
    BACKTEST_WARMUP_MONTHS,
    RESEARCH_HISTORY_MONTHS,
    default_research_start_date,
    effective_history_start_date,
)
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
BACKTEST_REQUIRED_COLUMNS = [
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "EMA20",
    "EMA60",
    "ATR",
]
RESEARCH_EMA_COLUMNS = {"EMA5", "EMA20", "EMA60"}
ENTRY_MODES = {
    "score",
    "score_and_rsi_momentum",
    "score_and_bollinger_breakout",
    "score_and_volume_confirmation",
}
EXIT_MODES = {
    "score",
    "score_or_time",
    "score_or_ema_reversal",
    "score_or_time_or_ema_reversal",
}


class InsufficientBacktestHistoryError(ValueError):
    """The requested evaluation slice cannot support indicator research."""
SCORE_SERIES_CACHE_SCHEMA = "score-engine-series-v1"
_SCORE_SERIES_CACHE_MAX_ENTRIES = 32
_SCORE_SERIES_CACHE: OrderedDict[
    tuple[str, str],
    tuple[float, ...],
] = OrderedDict()
_SCORE_SERIES_CACHE_LOCK = RLock()
_DAILY_SCORE_CACHE_MAX_ENTRIES = 20_000
_DAILY_SCORE_CACHE: OrderedDict[
    tuple[str, str, str],
    float,
] = OrderedDict()
_HISTORY_SNAPSHOT_CACHE_MAX_ENTRIES = 16
_HISTORY_SNAPSHOT_CACHE: OrderedDict[
    tuple[str, str, int],
    pd.DataFrame,
] = OrderedDict()
_HISTORY_SNAPSHOT_CACHE_LOCK = RLock()


def _history_snapshot_key(stock_code: str) -> tuple[str, str, int]:
    # Function identity isolates test/provider overrides while production keeps
    # one stable daily snapshot for the process lifetime.
    return stock_code, date.today().isoformat(), id(download_stock)


def _copy_frame_with_attrs(frame: pd.DataFrame) -> pd.DataFrame:
    copied = frame.copy(deep=True)
    copied.attrs.update(dict(frame.attrs))
    return copied


def _history_snapshot_covers(
    frame: pd.DataFrame,
    stock_code: str,
    required_start: pd.Timestamp,
    required_end: pd.Timestamp,
) -> bool:
    if frame is None or frame.empty:
        return False
    coverage = frame_coverage(frame)
    actual_start = pd.Timestamp(frame.index.min()).normalize()
    actual_end = pd.Timestamp(frame.index.max()).normalize()
    effective_start = pd.Timestamp(
        effective_history_start_date(
            stock_code,
            required_start.date(),
        )
    ).normalize()
    return bool(
        actual_start.to_period("M") <= effective_start.to_period("M")
        and actual_end >= required_end - pd.Timedelta(days=10)
        and coverage["complete_month_coverage"]
    )


def _get_history_snapshot(
    stock_code: str,
    required_start: pd.Timestamp,
    required_end: pd.Timestamp,
) -> pd.DataFrame | None:
    key = _history_snapshot_key(stock_code)
    with _HISTORY_SNAPSHOT_CACHE_LOCK:
        frame = _HISTORY_SNAPSHOT_CACHE.get(key)
        if frame is None or not _history_snapshot_covers(
            frame,
            stock_code,
            required_start,
            required_end,
        ):
            return None
        _HISTORY_SNAPSHOT_CACHE.move_to_end(key)
        copied = _copy_frame_with_attrs(frame)
    recovery = dict(copied.attrs.get("history_recovery", {}))
    recovery.update(cache_hit=True, cache_scope="daily_process_snapshot")
    copied.attrs["history_recovery"] = recovery
    return copied


def _put_history_snapshot(stock_code: str, frame: pd.DataFrame) -> None:
    key = _history_snapshot_key(stock_code)
    with _HISTORY_SNAPSHOT_CACHE_LOCK:
        _HISTORY_SNAPSHOT_CACHE[key] = _copy_frame_with_attrs(frame)
        _HISTORY_SNAPSHOT_CACHE.move_to_end(key)
        while len(_HISTORY_SNAPSHOT_CACHE) > _HISTORY_SNAPSHOT_CACHE_MAX_ENTRIES:
            _HISTORY_SNAPSHOT_CACHE.popitem(last=False)


def _clear_history_snapshot_cache() -> None:
    with _HISTORY_SNAPSHOT_CACHE_LOCK:
        _HISTORY_SNAPSHOT_CACHE.clear()


def _score_series_fingerprint(stock_code: str, df: pd.DataFrame) -> str:
    columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    hashes = pd.util.hash_pandas_object(
        df[columns],
        index=False,
        categorize=True,
    ).to_numpy(dtype="uint64", copy=False)
    digest = hashlib.sha256()
    digest.update(SCORE_SERIES_CACHE_SCHEMA.encode("utf-8"))
    digest.update(stock_code.encode("utf-8"))
    digest.update(hashes.tobytes())
    corporate_action_payload = {
        "price_basis": df.attrs.get("price_basis"),
        "split_adjusted": df.attrs.get("split_adjusted"),
        "corporate_action_validated": df.attrs.get(
            "corporate_action_validated"
        ),
        "split_adjustments": df.attrs.get("split_adjustments", []),
        "dividends": df.attrs.get("dividends", []),
        "corporate_action_events": df.attrs.get(
            "corporate_action_events",
            [],
        ),
        "corporate_action_resolutions": df.attrs.get(
            "corporate_action_resolutions",
            [],
        ),
    }
    digest.update(
        json.dumps(
            corporate_action_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )
    return digest.hexdigest()


def _score_series_for_frame(
    stock_code: str,
    df: pd.DataFrame,
) -> tuple[tuple[float, ...], bool, str]:
    fingerprint = _score_series_fingerprint(stock_code, df)
    key = (stock_code, fingerprint)
    with _SCORE_SERIES_CACHE_LOCK:
        cached = _SCORE_SERIES_CACHE.get(key)
        if cached is not None:
            _SCORE_SERIES_CACHE.move_to_end(key)
            return cached, True, fingerprint

    values = [float("nan")] * len(df)
    row_hashes = pd.util.hash_pandas_object(
        df[["Date", "Open", "High", "Low", "Close", "Volume"]],
        index=False,
        categorize=True,
    ).to_numpy(dtype="uint64", copy=False)
    for index in range(60, len(df) - 1):
        # Score Engine reads the latest row plus at most 20 trailing sessions.
        # A 60-session causal window is therefore equivalent to the full prefix
        # while avoiding quadratic copies during large autonomous searches.
        causal_window = df.iloc[index - 59 : index + 1]
        window_fingerprint = hashlib.sha256(
            row_hashes[index - 59 : index + 1].tobytes()
        ).hexdigest()[:20]
        date_key = pd.Timestamp(df.iloc[index]["Date"]).strftime(
            "%Y-%m-%d"
        )
        daily_key = (stock_code, date_key, window_fingerprint)
        with _SCORE_SERIES_CACHE_LOCK:
            daily_score = _DAILY_SCORE_CACHE.get(daily_key)
            if daily_score is not None:
                _DAILY_SCORE_CACHE.move_to_end(daily_key)
        if daily_score is None:
            daily_score = _extract_score(calculate_score(causal_window))
            with _SCORE_SERIES_CACHE_LOCK:
                _DAILY_SCORE_CACHE[daily_key] = daily_score
                _DAILY_SCORE_CACHE.move_to_end(daily_key)
                while (
                    len(_DAILY_SCORE_CACHE)
                    > _DAILY_SCORE_CACHE_MAX_ENTRIES
                ):
                    _DAILY_SCORE_CACHE.popitem(last=False)
        values[index] = daily_score
    result = tuple(values)
    with _SCORE_SERIES_CACHE_LOCK:
        existing = _SCORE_SERIES_CACHE.get(key)
        if existing is not None:
            _SCORE_SERIES_CACHE.move_to_end(key)
            return existing, True, fingerprint
        _SCORE_SERIES_CACHE[key] = result
        _SCORE_SERIES_CACHE.move_to_end(key)
        while len(_SCORE_SERIES_CACHE) > _SCORE_SERIES_CACHE_MAX_ENTRIES:
            _SCORE_SERIES_CACHE.popitem(last=False)
    return result, False, fingerprint


def _clear_score_series_cache() -> None:
    with _SCORE_SERIES_CACHE_LOCK:
        _SCORE_SERIES_CACHE.clear()
        _DAILY_SCORE_CACHE.clear()


def _build_research_return_series(
    df: pd.DataFrame,
    equity_curve: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    """Align strategy returns with the same-stock total-return benchmark."""
    if len(equity_curve) < 2:
        return {
            "dates": [],
            "strategy_daily_returns": [],
            "benchmark_daily_returns": [],
        }
    prices = {
        pd.Timestamp(row["Date"]).normalize(): float(row["Close"])
        for _, row in df[["Date", "Close"]].iterrows()
    }
    dividends = {
        pd.Timestamp(event_date).normalize(): float(amount)
        for event_date, amount in dividends_by_ex_date(df).items()
    }
    dates: list[str] = []
    strategy_returns: list[float] = []
    benchmark_returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        previous_equity = float(previous.get("equity", 0.0) or 0.0)
        current_equity = float(current.get("equity", 0.0) or 0.0)
        previous_date = pd.Timestamp(previous["date"]).normalize()
        current_date = pd.Timestamp(current["date"]).normalize()
        previous_close = prices.get(previous_date, 0.0)
        current_close = prices.get(current_date, 0.0)
        if previous_equity <= 0 or previous_close <= 0 or current_close <= 0:
            continue
        strategy_return = current_equity / previous_equity - 1.0
        benchmark_return = (
            current_close + dividends.get(current_date, 0.0)
        ) / previous_close - 1.0
        if not math.isfinite(strategy_return) or not math.isfinite(
            benchmark_return
        ):
            continue
        dates.append(current_date.strftime("%Y-%m-%d"))
        strategy_returns.append(float(strategy_return))
        benchmark_returns.append(float(benchmark_return))
    return {
        "dates": dates,
        "strategy_daily_returns": strategy_returns,
        "benchmark_daily_returns": benchmark_returns,
    }


def _download_backtest_history(
    stock_code: str,
    *,
    required_start_date: str,
    required_end_date: str | None,
) -> pd.DataFrame:
    required_start = pd.Timestamp(required_start_date).normalize()
    required_end = pd.Timestamp(
        required_end_date or pd.Timestamp.today()
    ).normalize()
    effective_required_start = pd.Timestamp(
        effective_history_start_date(
            stock_code,
            required_start.date(),
        )
    ).normalize()
    cached = _get_history_snapshot(
        stock_code,
        required_start,
        required_end,
    )
    if cached is not None:
        return cached
    attempts = (
        {
            "prefer_official": False,
            "daily_period": "10y",
            "force_official_refresh": False,
        },
        {
            "prefer_official": True,
            "daily_period": "max",
            "force_official_refresh": True,
        },
    )
    best_frame = pd.DataFrame()
    best_key = None
    initial_rows = 0
    errors: list[str] = []

    for attempt_index, options in enumerate(attempts):
        try:
            candidate = download_stock(
                stock_code,
                prefer_official=bool(options["prefer_official"]),
                daily_period=str(options["daily_period"]),
                update_with_intraday=False,
                official_months=(
                    RESEARCH_HISTORY_MONTHS + BACKTEST_WARMUP_MONTHS
                ),
                force_official_refresh=bool(
                    options["force_official_refresh"]
                ),
                include_corporate_actions=True,
            )
        except Exception as error:
            errors.append(str(error))
            continue

        if attempt_index == 0:
            initial_rows = len(candidate) if candidate is not None else 0
        if candidate is None or candidate.empty:
            continue

        coverage = frame_coverage(candidate)
        actual_start = pd.Timestamp(candidate.index.min()).normalize()
        actual_end = pd.Timestamp(candidate.index.max()).normalize()
        covers_start = (
            actual_start.to_period("M")
            <= effective_required_start.to_period("M")
        )
        covers_end = actual_end >= required_end - pd.Timedelta(days=10)
        complete_months = bool(coverage["complete_month_coverage"])
        covers_requested_span = (
            covers_start and covers_end and complete_months
        )
        key = (
            int(covers_requested_span),
            int(complete_months),
            int(covers_end),
            -int(actual_start.value),
            int(actual_end.value),
            len(candidate),
        )
        if best_key is None or key > best_key:
            best_key = key
            best_frame = candidate
        if covers_requested_span:
            candidate.attrs["history_recovery"] = {
                "recovered": attempt_index > 0,
                "attempts": attempt_index + 1,
                "initial_rows": initial_rows,
                "final_rows": len(candidate),
                "method": (
                    "long_history"
                    if attempt_index == 0
                    else "official_refresh"
                ),
                "cache_hit": False,
            }
            _put_history_snapshot(stock_code, candidate)
            return candidate

    if not best_frame.empty:
        best_frame.attrs["history_recovery"] = {
            "recovered": len(attempts) > 1,
            "attempts": len(attempts),
            "initial_rows": initial_rows,
            "final_rows": len(best_frame),
            "method": "best_available",
            "cache_hit": False,
        }
        _put_history_snapshot(stock_code, best_frame)
        return best_frame

    detail = "；".join(message for message in errors if message)
    raise ValueError(detail or f"找不到 {stock_code} 的歷史資料。")


def backtest_stock(
    stock_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    entry_score: float = 75,
    exit_score: float = 55,
    initial_capital: float = 100_000,
    commission_rate: float = COMMISSION_RATE,
    transaction_tax_rate: float = ETF_TRANSACTION_TAX_RATE,
    require_ema_trend: bool = False,
    ema_fast_column: str = "EMA20",
    ema_slow_column: str = "EMA60",
    entry_mode: str = "score",
    exit_mode: str = "score",
    max_holding_days: int = 60,
    liquidate_at_end: bool = True,
    include_research_series: bool = False,
) -> dict[str, Any]:
    """Backtest one fixed strategy without look-ahead.

    Research-only parameters extend the production score strategy while keeping
    the exact same validated OHLCV, corporate-action ledger, transaction costs,
    and next-session-open execution path.
    """

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
    if not 0 <= commission_rate < 1:
        raise ValueError("手續費率必須介於 0 到 1 之間。")
    if not 0 <= transaction_tax_rate < 1:
        raise ValueError("交易稅率必須介於 0 到 1 之間。")
    if (
        ema_fast_column not in RESEARCH_EMA_COLUMNS
        or ema_slow_column not in RESEARCH_EMA_COLUMNS
    ):
        raise ValueError(
            "EMA research columns must be EMA5, EMA20, or EMA60."
        )
    if ema_fast_column == ema_slow_column:
        raise ValueError("EMA fast and slow columns must differ.")
    if entry_mode not in ENTRY_MODES:
        raise ValueError(f"Unsupported entry_mode: {entry_mode}")
    if exit_mode not in EXIT_MODES:
        raise ValueError(f"Unsupported exit_mode: {exit_mode}")
    if (
        not isinstance(max_holding_days, int)
        or not 2 <= max_holding_days <= 252
    ):
        raise ValueError(
            "max_holding_days must be between 2 and 252 trading days."
        )

    effective_start_date = (
        start_date or default_research_start_date().isoformat()
    )
    warmup_start_date = (
        pd.Timestamp(effective_start_date)
        - pd.DateOffset(months=BACKTEST_WARMUP_MONTHS)
    ).strftime("%Y-%m-%d")
    df = _download_backtest_history(
        normalized_code,
        required_start_date=warmup_start_date,
        required_end_date=end_date,
    )
    if df is None or df.empty:
        raise ValueError(f"找不到 {normalized_code} 的歷史資料。")

    df = prepare_research_frame(df, normalized_code)
    data_source = str(df.attrs.get("source", "未知"))
    history_recovery = dict(df.attrs.get("history_recovery", {}))
    corporate_action_attrs = dict(df.attrs)
    corporate_action_metadata = research_metadata(df)
    df = _prepare_stock_data(
        df=df,
        start_date=warmup_start_date,
        end_date=end_date,
    )
    df = add_indicators(df.copy())
    if df is None or df.empty:
        raise InsufficientBacktestHistoryError(
            "技術指標計算後沒有可用資料。"
        )

    required_columns = list(BACKTEST_REQUIRED_COLUMNS)
    if require_ema_trend or "ema_reversal" in exit_mode:
        required_columns.extend([ema_fast_column, ema_slow_column])
    if entry_mode == "score_and_rsi_momentum":
        required_columns.append("RSI")
    elif entry_mode == "score_and_bollinger_breakout":
        required_columns.extend(["Close", "Upper"])
    elif entry_mode == "score_and_volume_confirmation":
        required_columns.append("VolumeRatio")
    df = df.dropna(subset=list(dict.fromkeys(required_columns))).reset_index(
        drop=True
    )
    df.attrs.update(corporate_action_attrs)
    requested_start_timestamp = pd.Timestamp(
        effective_start_date
    ).normalize()
    df = df.loc[df["Date"] >= requested_start_timestamp].reset_index(
        drop=True
    )
    df.attrs.update(corporate_action_attrs)
    if len(df) < 61:
        raise InsufficientBacktestHistoryError(
            "計算技術指標後的歷史資料不足，至少需要約 61 個有效交易日。"
        )

    cash = normalized_capital
    shares = 0
    entry_price = None
    entry_date = None
    entry_signal_score = None
    entry_index: int | None = None
    entry_gross_amount = 0.0
    entry_commission = 0.0
    entry_total_cost = 0.0
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    total_commission = 0.0
    total_transaction_tax = 0.0
    total_dividends = 0.0
    position_dividends = 0.0
    corporate_action_schedule = ledger_schedule_from_frame(df)
    score_series, score_cache_hit, score_series_fingerprint = (
        _score_series_for_frame(normalized_code, df)
    )

    for index in range(60, len(df) - 1):
        current_row = df.iloc[index]
        next_row = df.iloc[index + 1]
        score = score_series[index]
        next_date = _get_row_date(next_row)
        next_open = float(next_row["Open"])
        next_close = float(next_row["Close"])
        if next_open <= 0:
            continue

        previous_cash = cash
        ledger_state = apply_session_corporate_actions(
            stock_code=normalized_code,
            date=next_date,
            shares=shares,
            cash=cash,
            total_cost_basis=(
                entry_total_cost if shares > 0 else 0.0
            ),
            schedule=corporate_action_schedule,
        )
        cash = ledger_state.cash
        shares = ledger_state.shares
        ledger_cash_flow = max(0.0, cash - previous_cash)
        if ledger_cash_flow > 0 and shares > 0:
            total_dividends += ledger_cash_flow
            position_dividends += ledger_cash_flow

        ema_trend_ok = (
            not require_ema_trend
            or float(current_row[ema_fast_column])
            > float(current_row[ema_slow_column])
        )
        entry_structure_ok = (
            entry_mode == "score"
            or (
                entry_mode == "score_and_rsi_momentum"
                and 55.0 <= float(current_row["RSI"]) <= 80.0
            )
            or (
                entry_mode == "score_and_bollinger_breakout"
                and float(current_row["Close"])
                >= float(current_row["Upper"])
            )
            or (
                entry_mode == "score_and_volume_confirmation"
                and float(current_row["VolumeRatio"]) >= 1.2
            )
        )
        if (
            shares == 0
            and score >= entry_score
            and ema_trend_ok
            and entry_structure_ok
        ):
            purchasable_shares = _calculate_purchasable_shares(
                cash=cash,
                price=next_open,
                commission_rate=commission_rate,
            )
            if purchasable_shares > 0:
                buy_cost = _calculate_buy_cost(
                    price=next_open,
                    shares=purchasable_shares,
                    commission_rate=commission_rate,
                )
                shares = purchasable_shares
                cash -= buy_cost["total_cost"]
                entry_price = next_open
                entry_date = next_date
                entry_signal_score = score
                entry_index = index + 1
                entry_gross_amount = buy_cost["gross_amount"]
                entry_commission = buy_cost["commission"]
                entry_total_cost = buy_cost["total_cost"]
                total_commission += entry_commission
        elif shares > 0:
            held_days = (
                max(0, index - entry_index + 1)
                if entry_index is not None
                else 0
            )
            score_exit = score <= exit_score
            time_exit = (
                exit_mode
                in {"score_or_time", "score_or_time_or_ema_reversal"}
                and held_days >= max_holding_days
            )
            ema_exit = (
                exit_mode
                in {
                    "score_or_ema_reversal",
                    "score_or_time_or_ema_reversal",
                }
                and float(current_row[ema_fast_column])
                <= float(current_row[ema_slow_column])
            )
            if score_exit or time_exit or ema_exit:
                exit_reason = (
                    "score_below_exit_threshold"
                    if score_exit
                    else (
                        "max_holding_days"
                        if time_exit
                        else "ema_reversal"
                    )
                )
                sell_result = _calculate_sell_value(
                    price=next_open,
                    shares=shares,
                    commission_rate=commission_rate,
                    transaction_tax_rate=transaction_tax_rate,
                )
                cash += sell_result["net_amount"]
                exit_commission = sell_result["commission"]
                transaction_tax = sell_result["transaction_tax"]
                total_commission += exit_commission
                total_transaction_tax += transaction_tax
                net_profit = (
                    sell_result["net_amount"]
                    + position_dividends
                    - entry_total_cost
                )
                return_percent = (
                    net_profit / entry_total_cost * 100
                    if entry_total_cost > 0
                    else 0.0
                )
                trades.append(
                    {
                        "entry_date": entry_date,
                        "exit_date": next_date,
                        "entry_price": round(entry_price or 0, 2),
                        "exit_price": round(next_open, 2),
                        "shares": shares,
                        "entry_gross_amount": round(
                            entry_gross_amount, 2
                        ),
                        "entry_commission": round(entry_commission, 2),
                        "entry_total_cost": round(entry_total_cost, 2),
                        "exit_gross_amount": round(
                            sell_result["gross_amount"], 2
                        ),
                        "exit_commission": round(exit_commission, 2),
                        "transaction_tax": round(transaction_tax, 2),
                        "exit_net_amount": round(
                            sell_result["net_amount"], 2
                        ),
                        "profit": round(net_profit, 2),
                        "return_percent": round(return_percent, 2),
                        "entry_score": (
                            round(entry_signal_score, 2)
                            if entry_signal_score is not None
                            else None
                        ),
                        "exit_score": round(score, 2),
                        "exit_reason": exit_reason,
                        "holding_days": held_days,
                        "dividends": round(position_dividends, 2),
                    }
                )
                shares = 0
                entry_price = None
                entry_date = None
                entry_signal_score = None
                entry_index = None
                entry_gross_amount = 0.0
                entry_commission = 0.0
                entry_total_cost = 0.0
                position_dividends = 0.0

        equity = cash + shares * next_close
        equity_curve.append(
            {
                "date": next_date,
                "equity": round(equity, 2),
                "cash": round(cash, 2),
                "shares": shares,
                "close": round(next_close, 2),
                "score": round(score, 2),
            }
        )

    open_position = None
    if shares > 0:
        final_row = df.iloc[-1]
        final_close = float(final_row["Close"])
        final_date = _get_row_date(final_row)
        if liquidate_at_end:
            sell_result = _calculate_sell_value(
                price=final_close,
                shares=shares,
                commission_rate=commission_rate,
                transaction_tax_rate=transaction_tax_rate,
            )
            cash += sell_result["net_amount"]
            exit_commission = sell_result["commission"]
            transaction_tax = sell_result["transaction_tax"]
            total_commission += exit_commission
            total_transaction_tax += transaction_tax
            net_profit = (
                sell_result["net_amount"]
                + position_dividends
                - entry_total_cost
            )
            return_percent = (
                net_profit / entry_total_cost * 100
                if entry_total_cost > 0
                else 0.0
            )
            trades.append(
                {
                    "entry_date": entry_date,
                    "exit_date": final_date,
                    "entry_price": round(entry_price or 0, 2),
                    "exit_price": round(final_close, 2),
                    "shares": shares,
                    "entry_gross_amount": round(entry_gross_amount, 2),
                    "entry_commission": round(entry_commission, 2),
                    "entry_total_cost": round(entry_total_cost, 2),
                    "exit_gross_amount": round(
                        sell_result["gross_amount"], 2
                    ),
                    "exit_commission": round(exit_commission, 2),
                    "transaction_tax": round(transaction_tax, 2),
                    "exit_net_amount": round(
                        sell_result["net_amount"], 2
                    ),
                    "profit": round(net_profit, 2),
                    "return_percent": round(return_percent, 2),
                    "entry_score": (
                        round(entry_signal_score, 2)
                        if entry_signal_score is not None
                        else None
                    ),
                    "exit_score": None,
                    "exit_reason": "end_of_backtest",
                    "dividends": round(position_dividends, 2),
                }
            )
            shares = 0
            if equity_curve:
                equity_curve[-1].update(
                    {
                        "equity": round(cash, 2),
                        "cash": round(cash, 2),
                        "shares": 0,
                    }
                )
        else:
            unrealized_profit = (
                shares * final_close
                + position_dividends
                - entry_total_cost
            )
            open_position = {
                "entry_date": entry_date,
                "entry_price": round(entry_price or 0, 2),
                "shares": shares,
                "entry_signal_score": (
                    round(entry_signal_score, 2)
                    if entry_signal_score is not None
                    else None
                ),
                "mark_date": final_date,
                "mark_price": round(final_close, 2),
                "unrealized_profit": round(unrealized_profit, 2),
                "unrealized_return_percent": round(
                    (
                        unrealized_profit / entry_total_cost * 100
                        if entry_total_cost
                        else 0.0
                    ),
                    2,
                ),
                "dividends": round(position_dividends, 2),
            }

    final_market_value = (
        float(shares) * float(df.iloc[-1]["Close"])
        if shares > 0
        else 0.0
    )
    final_capital = float(cash) + final_market_value
    total_profit = final_capital - normalized_capital
    total_return = total_profit / normalized_capital * 100
    winning_trades = [
        trade for trade in trades if float(trade["profit"]) > 0
    ]
    win_rate = (
        len(winning_trades) / len(trades) * 100 if trades else 0.0
    )
    max_drawdown = _calculate_max_drawdown(equity_curve)
    actual_start_date = _get_row_date(df.iloc[0])
    actual_end_date = _get_row_date(df.iloc[-1])
    history_coverage = frame_coverage(df.set_index("Date"))
    buy_and_hold = _calculate_buy_and_hold(
        df=df,
        initial_capital=normalized_capital,
        commission_rate=commission_rate,
        transaction_tax_rate=transaction_tax_rate,
    )
    buy_and_hold_return = float(
        buy_and_hold.get("return_percent", 0.0)
    )
    alpha_percent = total_return - buy_and_hold_return
    _enrich_trades_with_excursions(df=df, trades=trades)
    exposure_percent = _calculate_exposure_percent(equity_curve)
    drawdown_statistics = _calculate_drawdown_statistics(equity_curve)
    advanced_trade_statistics = _calculate_advanced_trade_statistics(
        trades=trades,
        initial_capital=normalized_capital,
        final_capital=final_capital,
        max_drawdown_percent=max_drawdown,
        exposure_percent=exposure_percent,
    )
    performance_metrics = _calculate_performance_metrics(
        equity_curve=equity_curve,
        trades=trades,
        initial_capital=normalized_capital,
        final_capital=final_capital,
        actual_start_date=actual_start_date,
        actual_end_date=actual_end_date,
        max_drawdown_percent=max_drawdown,
    )
    research_return_series = (
        _build_research_return_series(df, equity_curve)
        if include_research_series
        else None
    )

    strategy_parameters = {
        "entry_score": entry_score,
        "exit_score": exit_score,
        "require_ema_trend": require_ema_trend,
        "ema_fast_column": ema_fast_column,
        "ema_slow_column": ema_slow_column,
        "entry_mode": entry_mode,
        "exit_mode": exit_mode,
        "max_holding_days": max_holding_days,
        "liquidate_at_end": liquidate_at_end,
    }
    return {
        "stock_code": normalized_code,
        "data_source": data_source,
        "requested_start_date": effective_start_date,
        "requested_end_date": end_date,
        "actual_start_date": actual_start_date,
        "actual_end_date": actual_end_date,
        "history_coverage": history_coverage,
        "history_recovery": history_recovery,
        "requested_history_months": RESEARCH_HISTORY_MONTHS,
        "entry_score": entry_score,
        "exit_score": exit_score,
        "strategy_parameters": strategy_parameters,
        "score_series_cache": {
            "schema": SCORE_SERIES_CACHE_SCHEMA,
            "cache_hit": score_cache_hit,
            "fingerprint": score_series_fingerprint[:20],
        },
        "commission_rate": commission_rate,
        "transaction_tax_rate": transaction_tax_rate,
        "initial_capital": round(normalized_capital, 2),
        "final_capital": round(final_capital, 2),
        "total_profit": round(total_profit, 2),
        "total_return_percent": round(total_return, 2),
        "total_commission": round(total_commission, 2),
        "total_transaction_tax": round(total_transaction_tax, 2),
        "total_dividends": round(total_dividends, 2),
        "corporate_actions": {
            **corporate_action_metadata,
            "split_adjustments": corporate_action_attrs.get(
                "split_adjustments", []
            ),
            "dividend_source": corporate_action_attrs.get(
                "dividend_source"
            ),
            "dividend_event_count": len(
                corporate_action_attrs.get("dividends", [])
            ),
            "event_count": len(
                corporate_action_attrs.get(
                    "corporate_action_events", []
                )
            ),
            "resolution_count": len(
                corporate_action_attrs.get(
                    "corporate_action_resolutions", []
                )
            ),
            "accounting_path": "event-ledger-v1",
        },
        "total_transaction_cost": round(
            total_commission + total_transaction_tax, 2
        ),
        "trade_count": len(trades),
        "total_trades": len(trades),
        "completed_trades": len(trades),
        "winning_trade_count": len(winning_trades),
        "win_rate_percent": round(win_rate, 2),
        "open_position_count": int(open_position is not None),
        "open_position": open_position,
        "max_drawdown_percent": round(max_drawdown, 2),
        "buy_and_hold": buy_and_hold,
        "alpha_percent": round(alpha_percent, 2),
        "performance_metrics": performance_metrics,
        "advanced_trade_statistics": advanced_trade_statistics,
        "drawdown_statistics": drawdown_statistics,
        "exposure_percent": round(exposure_percent, 2),
        "trades": trades,
        "equity_curve": equity_curve,
        "research_return_series": research_return_series,
    }
