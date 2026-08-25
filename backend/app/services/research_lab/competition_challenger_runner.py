from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Callable

import pandas as pd

from corporate_actions import dividends_by_ex_date
from score_engine.calculate import calculate_score

from app.services.competition_runner import (
    COMMISSION_RATE,
    COMPETITION_UNIVERSE,
    DEFAULT_INITIAL_CAPITAL,
    ETF_TRANSACTION_TAX_RATE,
    MIN_FORWARD_TRADES_FOR_CHAMPION,
    STOP_ATR_MULTIPLE,
    TARGET_ATR_MULTIPLE,
    _aggregate_portfolio,
    _calculate_buy_cost,
    _calculate_purchasable_shares,
    _calculate_sell_value,
    _date_text,
    _download_competition_frames,
    _number,
    run_competition_on_frames,
)
from app.services.competition_service import rank_robot_results

from .competition_bridge import CHALLENGER_SCHEMA_VERSION, QUEUE_STATUS


TOURNAMENT_SCHEMA_VERSION = 1
COST_MODEL_ID = "TWSE-ETF-0.1425-0.1-CORP-ACTIONS-v2"
RISK_MODEL_ID = "ATR-2R-STOP-4R-TARGET-v1"
MARKET_UNIVERSE_ID = "TW-ETF-CORE-4-v1"
ScoreFn = Callable[[pd.DataFrame], Any]


def _extract_score(value: Any) -> float:
    if isinstance(value, tuple) and value:
        value = value[0]
    elif hasattr(value, "total_score"):
        value = getattr(value, "total_score")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return math.nan
    return parsed if math.isfinite(parsed) else math.nan


def build_causal_score_series(
    frame: pd.DataFrame,
    *,
    score_fn: ScoreFn = calculate_score,
) -> tuple[float, ...]:
    """Pre-compute score-engine values using only the current and past 59 sessions."""
    values = [math.nan] * len(frame)
    for index in range(59, len(frame)):
        causal_window = frame.iloc[index - 59 : index + 1]
        try:
            values[index] = _extract_score(score_fn(causal_window))
        except Exception:
            values[index] = math.nan
    return tuple(values)


def _entry_allowed(row: pd.Series, score: float, parameters: dict[str, Any]) -> bool:
    if not math.isfinite(score):
        return False
    entry_score = float(parameters.get("entry_score", 75))
    if score < entry_score:
        return False

    fast = str(parameters.get("ema_fast_column") or "EMA20")
    slow = str(parameters.get("ema_slow_column") or "EMA60")
    if parameters.get("require_ema_trend"):
        fast_value = _number(row, fast)
        slow_value = _number(row, slow)
        if not math.isfinite(fast_value) or not math.isfinite(slow_value):
            return False
        if fast_value <= slow_value:
            return False

    mode = str(parameters.get("entry_mode") or "score")
    if mode == "score":
        return True
    if mode == "score_and_rsi_momentum":
        rsi = _number(row, "RSI")
        return math.isfinite(rsi) and 55.0 <= rsi <= 80.0
    if mode == "score_and_bollinger_breakout":
        close = _number(row, "Close")
        upper = _number(row, "Upper")
        return math.isfinite(close) and math.isfinite(upper) and close >= upper
    if mode == "score_and_volume_confirmation":
        volume_ratio = _number(row, "VolumeRatio")
        return math.isfinite(volume_ratio) and volume_ratio >= 1.2
    raise ValueError(f"Unsupported challenger entry_mode: {mode}")


def _exit_reason(
    row: pd.Series,
    score: float,
    parameters: dict[str, Any],
    *,
    held_sessions: int,
) -> str | None:
    if not math.isfinite(score):
        return None
    exit_score = float(parameters.get("exit_score", 55))
    if score <= exit_score:
        return "score_below_exit_threshold"

    exit_mode = str(parameters.get("exit_mode") or "score")
    max_holding_days = int(parameters.get("max_holding_days", 60))
    if "time" in exit_mode and held_sessions >= max_holding_days:
        return "max_holding_days"

    if "ema_reversal" in exit_mode:
        fast = str(parameters.get("ema_fast_column") or "EMA20")
        slow = str(parameters.get("ema_slow_column") or "EMA60")
        fast_value = _number(row, fast)
        slow_value = _number(row, slow)
        if math.isfinite(fast_value) and math.isfinite(slow_value) and fast_value <= slow_value:
            return "ema_reversal"
    return None


def _empty_symbol_result(
    stock_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    initial_capital: float,
) -> dict[str, Any]:
    return {
        "stock_code": stock_code,
        "data_available": False,
        "actual_start": None,
        "actual_end": None,
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(initial_capital, 2),
        "total_commission": 0.0,
        "total_transaction_tax": 0.0,
        "total_dividends": 0.0,
        "trades": [],
        "equity_curve": [
            {"date": _date_text(start), "equity": round(initial_capital, 2)},
            {"date": _date_text(end), "equity": round(initial_capital, 2)},
        ],
    }


def _close_position(
    *,
    cash: float,
    shares: int,
    price: float,
    commission_rate: float,
    transaction_tax_rate: float,
) -> tuple[float, dict[str, float]]:
    sale = _calculate_sell_value(
        price=price,
        shares=shares,
        commission_rate=commission_rate,
        transaction_tax_rate=transaction_tax_rate,
    )
    return cash + sale["net_amount"], sale


def simulate_challenger_symbol(
    *,
    frame: pd.DataFrame,
    score_series: tuple[float, ...],
    stock_code: str,
    challenger: dict[str, Any],
    start: pd.Timestamp,
    end: pd.Timestamp,
    initial_capital: float,
    commission_rate: float = COMMISSION_RATE,
    transaction_tax_rate: float = ETF_TRANSACTION_TAX_RATE,
) -> dict[str, Any]:
    """Run a certified research rule under the competition's exact execution/risk shell."""
    positions = [
        index
        for index, timestamp in enumerate(frame.index)
        if start <= pd.Timestamp(timestamp) <= end
    ]
    if not positions:
        return _empty_symbol_result(stock_code, start, end, initial_capital)
    if len(score_series) != len(frame):
        raise ValueError("Score series length does not match competition frame")

    spec = challenger.get("spec") or {}
    parameters = spec.get("parameters") or {}
    robot_id = str(challenger.get("robot_id") or spec.get("robot_id") or "").strip()
    if not robot_id:
        raise ValueError("Challenger robot_id is required")

    cash = float(initial_capital)
    shares = 0
    entry_price: float | None = None
    entry_date: str | None = None
    entry_reason = ""
    entry_total_cost = 0.0
    entry_commission = 0.0
    entry_frame_position: int | None = None
    stop_price: float | None = None
    target_price: float | None = None
    pending_entry: tuple[str, float] | None = None
    pending_exit: str | None = None
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    total_commission = 0.0
    total_transaction_tax = 0.0
    total_dividends = 0.0
    position_dividends = 0.0
    dividend_schedule = dividends_by_ex_date(frame)

    first_position = positions[0]
    if first_position > 0:
        prior = frame.iloc[first_position - 1]
        prior_score = score_series[first_position - 1]
        prior_atr = _number(prior, "ATR")
        if _entry_allowed(prior, prior_score, parameters) and math.isfinite(prior_atr) and prior_atr > 0:
            pending_entry = ("research_score_entry", prior_atr)

    for position in positions:
        row = frame.iloc[position]
        session_date = _date_text(frame.index[position])
        open_price = _number(row, "Open")
        high_price = _number(row, "High")
        low_price = _number(row, "Low")
        close_price = _number(row, "Close")
        if not all(math.isfinite(value) for value in (open_price, high_price, low_price, close_price)):
            continue

        dividend_per_share = dividend_schedule.get(session_date, 0.0)
        if shares > 0 and dividend_per_share > 0:
            received = shares * dividend_per_share
            cash += received
            total_dividends += received
            position_dividends += received

        if pending_exit and shares > 0:
            cash, sale = _close_position(
                cash=cash,
                shares=shares,
                price=open_price,
                commission_rate=commission_rate,
                transaction_tax_rate=transaction_tax_rate,
            )
            profit = sale["net_amount"] + position_dividends - entry_total_cost
            trades.append({
                "robot_id": robot_id,
                "stock_code": stock_code,
                "segment": "forward",
                "entry_date": entry_date,
                "exit_date": session_date,
                "entry_price": round(entry_price or 0.0, 4),
                "exit_price": round(open_price, 4),
                "shares": shares,
                "profit": round(profit, 2),
                "return_percent": round(profit / entry_total_cost * 100 if entry_total_cost else 0.0, 4),
                "entry_reason": entry_reason,
                "exit_reason": pending_exit,
                "entry_commission": round(entry_commission, 2),
                "exit_commission": round(sale["commission"], 2),
                "transaction_tax": round(sale["transaction_tax"], 2),
                "dividends": round(position_dividends, 2),
                "stop_price": round(stop_price or 0.0, 4),
                "target_price": round(target_price or 0.0, 4),
            })
            total_commission += sale["commission"]
            total_transaction_tax += sale["transaction_tax"]
            shares = 0
            entry_price = None
            entry_date = None
            entry_total_cost = 0.0
            entry_commission = 0.0
            entry_frame_position = None
            stop_price = None
            target_price = None
            pending_exit = None
            position_dividends = 0.0

        if pending_entry and shares == 0:
            reason, signal_atr = pending_entry
            purchasable = _calculate_purchasable_shares(
                cash=cash,
                price=open_price,
                commission_rate=commission_rate,
            )
            if purchasable > 0:
                purchase = _calculate_buy_cost(
                    price=open_price,
                    shares=purchasable,
                    commission_rate=commission_rate,
                )
                cash -= purchase["total_cost"]
                shares = purchasable
                entry_price = open_price
                entry_date = session_date
                entry_reason = reason
                entry_total_cost = purchase["total_cost"]
                entry_commission = purchase["commission"]
                entry_frame_position = position
                stop_price = max(0.01, open_price - STOP_ATR_MULTIPLE * signal_atr)
                target_price = open_price + TARGET_ATR_MULTIPLE * signal_atr
                total_commission += purchase["commission"]
            pending_entry = None

        intraday_exit: tuple[float, str] | None = None
        if shares > 0 and stop_price is not None and target_price is not None:
            if low_price <= stop_price:
                intraday_exit = (min(open_price, stop_price), "2atr_stop")
            elif high_price >= target_price:
                intraday_exit = (max(open_price, target_price), "4atr_target")

        if intraday_exit is not None and shares > 0:
            exit_price, exit_reason = intraday_exit
            cash, sale = _close_position(
                cash=cash,
                shares=shares,
                price=exit_price,
                commission_rate=commission_rate,
                transaction_tax_rate=transaction_tax_rate,
            )
            profit = sale["net_amount"] + position_dividends - entry_total_cost
            trades.append({
                "robot_id": robot_id,
                "stock_code": stock_code,
                "segment": "forward",
                "entry_date": entry_date,
                "exit_date": session_date,
                "entry_price": round(entry_price or 0.0, 4),
                "exit_price": round(exit_price, 4),
                "shares": shares,
                "profit": round(profit, 2),
                "return_percent": round(profit / entry_total_cost * 100 if entry_total_cost else 0.0, 4),
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
                "entry_commission": round(entry_commission, 2),
                "exit_commission": round(sale["commission"], 2),
                "transaction_tax": round(sale["transaction_tax"], 2),
                "dividends": round(position_dividends, 2),
                "stop_price": round(stop_price, 4),
                "target_price": round(target_price, 4),
            })
            total_commission += sale["commission"]
            total_transaction_tax += sale["transaction_tax"]
            shares = 0
            entry_price = None
            entry_date = None
            entry_total_cost = 0.0
            entry_commission = 0.0
            entry_frame_position = None
            stop_price = None
            target_price = None
            position_dividends = 0.0

        equity_curve.append({
            "date": session_date,
            "equity": round(cash + shares * close_price, 2),
        })

        score = score_series[position]
        if shares > 0:
            held_sessions = (
                max(0, position - entry_frame_position + 1)
                if entry_frame_position is not None
                else 0
            )
            reason = _exit_reason(row, score, parameters, held_sessions=held_sessions)
            if reason:
                pending_exit = f"strategy_exit:{reason}"
                pending_entry = None
        elif _entry_allowed(row, score, parameters):
            atr = _number(row, "ATR")
            if math.isfinite(atr) and atr > 0:
                pending_entry = ("research_score_entry", atr)
            pending_exit = None
        else:
            pending_entry = None
            pending_exit = None

    if shares > 0:
        final_row = frame.iloc[positions[-1]]
        final_price = _number(final_row, "Close")
        final_date = _date_text(frame.index[positions[-1]])
        cash, sale = _close_position(
            cash=cash,
            shares=shares,
            price=final_price,
            commission_rate=commission_rate,
            transaction_tax_rate=transaction_tax_rate,
        )
        profit = sale["net_amount"] + position_dividends - entry_total_cost
        trades.append({
            "robot_id": robot_id,
            "stock_code": stock_code,
            "segment": "forward",
            "entry_date": entry_date,
            "exit_date": final_date,
            "entry_price": round(entry_price or 0.0, 4),
            "exit_price": round(final_price, 4),
            "shares": shares,
            "profit": round(profit, 2),
            "return_percent": round(profit / entry_total_cost * 100 if entry_total_cost else 0.0, 4),
            "entry_reason": entry_reason,
            "exit_reason": "segment_end",
            "entry_commission": round(entry_commission, 2),
            "exit_commission": round(sale["commission"], 2),
            "transaction_tax": round(sale["transaction_tax"], 2),
            "dividends": round(position_dividends, 2),
            "stop_price": round(stop_price or 0.0, 4),
            "target_price": round(target_price or 0.0, 4),
        })
        total_commission += sale["commission"]
        total_transaction_tax += sale["transaction_tax"]
        if equity_curve:
            equity_curve[-1]["equity"] = round(cash, 2)

    return {
        "stock_code": stock_code,
        "data_available": True,
        "actual_start": _date_text(frame.index[positions[0]]),
        "actual_end": _date_text(frame.index[positions[-1]]),
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(cash, 2),
        "total_commission": round(total_commission, 2),
        "total_transaction_tax": round(total_transaction_tax, 2),
        "total_dividends": round(total_dividends, 2),
        "trades": trades,
        "equity_curve": equity_curve,
    }


def _incumbent_ranking_rows(incumbent: dict[str, Any]) -> list[dict[str, Any]]:
    start = incumbent["periods"]["forward"]["start"]
    end = incumbent["periods"]["forward"]["end"]
    capital = float(incumbent["fairness"]["initial_capital"])
    return [
        {
            "robot_id": robot["robot_id"],
            "robot_version": "1",
            "rule_fingerprint": robot["rule_fingerprint"],
            "initial_capital": capital,
            "period_start": start,
            "period_end": end,
            "cost_model_id": COST_MODEL_ID,
            "risk_model_id": RISK_MODEL_ID,
            "market_universe_id": MARKET_UNIVERSE_ID,
            "trade_count": robot["forward"]["trade_count"],
            "winning_trade_count": robot["forward"]["winning_trade_count"],
            "total_return_percent": robot["forward"]["total_return_percent"],
            "max_drawdown_percent": robot["forward"]["max_drawdown_percent"],
        }
        for robot in incumbent["robots"]
    ]


def run_challenger_tournament_on_frames(
    frames: dict[str, pd.DataFrame],
    challenger_roster: dict[str, Any],
    *,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    sources: dict[str, str] | None = None,
    coverage: dict[str, dict[str, Any]] | None = None,
    score_fn: ScoreFn = calculate_score,
) -> dict[str, Any]:
    if challenger_roster.get("schema_version") != CHALLENGER_SCHEMA_VERSION:
        raise ValueError("Unsupported challenger roster schema")
    challengers = challenger_roster.get("challengers")
    if not isinstance(challengers, list):
        raise ValueError("Challenger roster must contain a list")
    if int(challenger_roster.get("challenger_count", -1)) != len(challengers):
        raise ValueError("Challenger roster count mismatch")
    if not challengers:
        return {
            "schema_version": TOURNAMENT_SCHEMA_VERSION,
            "status": "WAITING_FOR_CERTIFIED_ROBOT",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "challenger_count": 0,
            "promotion": {
                "challenger_replaced_incumbent": False,
                "reason": "No Final-Holdout-certified challenger exists yet.",
            },
        }
    if any(challenger.get("status") != QUEUE_STATUS for challenger in challengers):
        raise ValueError("Only queued certified challengers may compete")

    incumbent = run_competition_on_frames(
        frames,
        initial_capital=initial_capital,
        sources=sources,
        coverage=coverage,
    )
    start = pd.Timestamp(incumbent["periods"]["forward"]["start"])
    end = pd.Timestamp(incumbent["periods"]["forward"]["end"])
    capital = float(incumbent["fairness"]["initial_capital"])
    per_symbol_capital = capital / len(COMPETITION_UNIVERSE)

    score_series_by_symbol = {
        code: build_causal_score_series(frames[code], score_fn=score_fn)
        for code in COMPETITION_UNIVERSE
    }
    challenger_outputs: list[dict[str, Any]] = []
    ranking_rows = _incumbent_ranking_rows(incumbent)

    for challenger in challengers:
        symbol_results = [
            simulate_challenger_symbol(
                frame=frames[code],
                score_series=score_series_by_symbol[code],
                stock_code=code,
                challenger=challenger,
                start=start,
                end=end,
                initial_capital=per_symbol_capital,
            )
            for code in COMPETITION_UNIVERSE
        ]
        forward = _aggregate_portfolio(symbol_results, initial_capital=capital)
        spec = challenger.get("spec") or {}
        robot_id = str(challenger["robot_id"])
        ranking_rows.append({
            "robot_id": robot_id,
            "robot_version": str(challenger.get("challenger_id") or "1"),
            "rule_fingerprint": challenger["rule_fingerprint"],
            "initial_capital": capital,
            "period_start": _date_text(start),
            "period_end": _date_text(end),
            "cost_model_id": COST_MODEL_ID,
            "risk_model_id": RISK_MODEL_ID,
            "market_universe_id": MARKET_UNIVERSE_ID,
            "trade_count": forward["trade_count"],
            "winning_trade_count": forward["winning_trade_count"],
            "total_return_percent": forward["total_return_percent"],
            "max_drawdown_percent": forward["max_drawdown_percent"],
        })
        challenger_outputs.append({
            "origin": "research_lab_certified",
            "robot_id": robot_id,
            "name": spec.get("name"),
            "family": spec.get("family"),
            "challenger_id": challenger.get("challenger_id"),
            "rule_fingerprint": challenger.get("rule_fingerprint"),
            "research_provenance": challenger.get("research_provenance") or {},
            "forward": forward,
        })

    ranking = rank_robot_results(ranking_rows)
    rank_by_id = {row["robot_id"]: row for row in ranking["robots"]}
    for robot in challenger_outputs:
        row = rank_by_id[robot["robot_id"]]
        robot["rank"] = row["rank"]
        robot["wilson_lower_percent"] = row["wilson_lower_percent"]
        robot["wilson_upper_percent"] = row["wilson_upper_percent"]
    challenger_outputs.sort(key=lambda item: int(item["rank"]))

    incumbent_leader_id = str(incumbent["leader"]["robot_id"])
    overall_leader = ranking["robots"][0]
    challenger_ids = {item["robot_id"] for item in challenger_outputs}
    challenger_won = overall_leader["robot_id"] in challenger_ids
    leader_trades = int(overall_leader["trade_count"])
    leader_qualified = leader_trades >= MIN_FORWARD_TRADES_FOR_CHAMPION
    replaced = challenger_won and leader_qualified

    return {
        "schema_version": TOURNAMENT_SCHEMA_VERSION,
        "status": "completed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "incumbent_run_id": incumbent.get("run_id"),
        "challenger_count": len(challenger_outputs),
        "fairness": incumbent.get("fairness"),
        "periods": incumbent.get("periods"),
        "ranking": {
            "primary_metric": "forward Wilson 95% win-rate lower bound",
            "minimum_forward_trades_for_champion": MIN_FORWARD_TRADES_FOR_CHAMPION,
            "all_robot_count": len(ranking["robots"]),
            "robots": ranking["robots"],
        },
        "incumbent_leader": {
            "robot_id": incumbent_leader_id,
            "name": incumbent["leader"].get("name"),
        },
        "overall_leader": {
            "robot_id": overall_leader["robot_id"],
            "rank": overall_leader["rank"],
            "trade_count": leader_trades,
            "wilson_lower_percent": overall_leader["wilson_lower_percent"],
            "qualified": leader_qualified,
            "origin": (
                "research_lab_certified"
                if overall_leader["robot_id"] in challenger_ids
                else "incumbent_competition"
            ),
        },
        "promotion": {
            "challenger_replaced_incumbent": replaced,
            "promoted_robot_id": overall_leader["robot_id"] if replaced else None,
            "defeated_incumbent_robot_id": incumbent_leader_id if replaced else None,
            "reason": (
                "Certified challenger ranked first and met the minimum forward-trade gate."
                if replaced
                else (
                    "Challenger ranked first but remains provisional because the forward-trade gate is not met."
                    if challenger_won
                    else "Incumbent competition leader retained the title."
                )
            ),
            "competition_feedback_to_same_campaign_train": False,
        },
        "challengers": challenger_outputs,
        "incumbent_competition": {
            "leader": incumbent.get("leader"),
            "robot_count": len(incumbent.get("robots") or []),
        },
    }


def run_certified_challenger_tournament(
    challenger_roster: dict[str, Any],
    *,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
) -> dict[str, Any]:
    challengers = challenger_roster.get("challengers") or []
    if not challengers:
        return run_challenger_tournament_on_frames({}, challenger_roster, initial_capital=initial_capital)
    frames, sources, coverage = _download_competition_frames()
    return run_challenger_tournament_on_frames(
        frames,
        challenger_roster,
        initial_capital=initial_capital,
        sources=sources,
        coverage=coverage,
    )
