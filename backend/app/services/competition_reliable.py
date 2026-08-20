from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

import pandas as pd

from app.services import competition_runner as legacy
from app.services.research_dataset import load_shared_research_dataset
from app.services.selection_bias import selection_bias_diagnostics
from app.services.trading_costs import TAIWAN_ETF_COST_MODEL

DEFAULT_INITIAL_CAPITAL = legacy.DEFAULT_INITIAL_CAPITAL
MAX_INITIAL_CAPITAL = legacy.MAX_INITIAL_CAPITAL
_ORIGINAL_SIMULATE_SYMBOL = legacy._simulate_symbol


def _remove_synthetic_segment_end_exit(result: dict[str, Any]) -> dict[str, Any]:
    trades = list(result.get("trades") or [])
    boundary_trades = [trade for trade in trades if trade.get("exit_reason") == "segment_end"]
    if not boundary_trades:
        result["open_positions"] = []
        return result
    open_positions: list[dict[str, Any]] = []
    commission_reversal = tax_reversal = 0.0
    for trade in boundary_trades:
        exit_commission = float(trade.get("exit_commission") or 0.0)
        transaction_tax = float(trade.get("transaction_tax") or 0.0)
        shares = int(trade.get("shares") or 0)
        mark_price = float(trade.get("exit_price") or 0.0)
        commission_reversal += exit_commission
        tax_reversal += transaction_tax
        open_positions.append({
            "robot_id": trade.get("robot_id"), "stock_code": trade.get("stock_code"), "segment": trade.get("segment"),
            "entry_date": trade.get("entry_date"), "entry_price": trade.get("entry_price"), "shares": shares,
            "mark_price": round(mark_price, 4), "market_value": round(shares * mark_price, 2),
            "unrealized_profit": round(float(trade.get("profit") or 0.0) + exit_commission + transaction_tax, 2),
            "entry_reason": trade.get("entry_reason"), "entry_commission": trade.get("entry_commission"),
            "stop_price": trade.get("stop_price"), "target_price": trade.get("target_price"), "valuation": "mark_to_market",
        })
    result["trades"] = [trade for trade in trades if trade.get("exit_reason") != "segment_end"]
    result["open_positions"] = open_positions
    result["final_capital"] = round(float(result["final_capital"]) + commission_reversal + tax_reversal, 2)
    result["total_commission"] = round(max(0.0, float(result["total_commission"]) - commission_reversal), 2)
    result["total_transaction_tax"] = round(max(0.0, float(result["total_transaction_tax"]) - tax_reversal), 2)
    if result.get("equity_curve"):
        result["equity_curve"][-1]["equity"] = round(float(result["equity_curve"][-1]["equity"]) + commission_reversal + tax_reversal, 2)
    return result


def _simulate_symbol_mark_to_market(**kwargs: Any) -> dict[str, Any]:
    return _remove_synthetic_segment_end_exit(_ORIGINAL_SIMULATE_SYMBOL(**kwargs))


def run_competition_on_frames(frames: dict[str, pd.DataFrame], *, initial_capital: float = DEFAULT_INITIAL_CAPITAL, sources: dict[str, str] | None = None) -> dict[str, Any]:
    capital = float(initial_capital)
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("競賽初始資金必須大於 0。")
    if capital > MAX_INITIAL_CAPITAL:
        raise ValueError("競賽初始資金不能超過 2,000,000 元。")
    missing = [code for code in legacy.COMPETITION_UNIVERSE if code not in frames]
    if missing:
        raise ValueError("競賽缺少股票資料：" + "、".join(missing))

    cost_model = TAIWAN_ETF_COST_MODEL
    latest_date = min(pd.Timestamp(frames[code].index.max()) for code in legacy.COMPETITION_UNIVERSE)
    forward_start = (latest_date - pd.DateOffset(months=1)).normalize()
    backtest_start = (forward_start - pd.DateOffset(months=2)).normalize()
    backtest_end = forward_start - pd.Timedelta(days=1)
    per_symbol_capital = capital / len(legacy.COMPETITION_UNIVERSE)
    robot_outputs, ranking_rows = [], []

    for spec in legacy.ROBOT_SPECS:
        frozen = legacy.freeze_robot_spec(spec)
        robot_id = str(spec["robot_id"])
        segment_outputs = {}
        for segment, start, end in (("backtest", backtest_start, backtest_end), ("forward", forward_start, latest_date)):
            symbol_results = [_simulate_symbol_mark_to_market(frame=frames[code], stock_code=code, robot_id=robot_id, segment=segment, start=start, end=end, initial_capital=per_symbol_capital, commission_rate=cost_model.commission_rate, transaction_tax_rate=cost_model.transaction_tax_rate) for code in legacy.COMPETITION_UNIVERSE]
            segment_outputs[segment] = legacy._aggregate_portfolio(symbol_results, initial_capital=capital)
            segment_outputs[segment]["open_positions"] = [position for result in symbol_results for position in result.get("open_positions", [])]
        forward = segment_outputs["forward"]
        ranking_rows.append({"robot_id": robot_id, "robot_version": "1", "rule_fingerprint": frozen["rule_fingerprint"], "initial_capital": capital, "period_start": legacy._date_text(forward_start), "period_end": legacy._date_text(latest_date), "cost_model_id": cost_model.model_id, "risk_model_id": "ATR-2R-STOP-4R-TARGET-v1", "market_universe_id": "TW-ETF-CORE-4-v1", "trade_count": forward["trade_count"], "winning_trade_count": forward["winning_trade_count"], "total_return_percent": forward["total_return_percent"], "max_drawdown_percent": forward["max_drawdown_percent"]})
        robot_outputs.append({"robot_id": robot_id, "name": spec["name"], "family": spec["family"], "rule_fingerprint": frozen["rule_fingerprint"], "spec": spec, "backtest": segment_outputs["backtest"], "forward": forward})

    ranking = legacy.rank_robot_results(ranking_rows)
    rank_by_id = {row["robot_id"]: row for row in ranking["robots"]}
    for output in robot_outputs:
        row = rank_by_id[output["robot_id"]]
        output.update(rank=row["rank"], wilson_lower_percent=row["wilson_lower_percent"], wilson_upper_percent=row["wilson_upper_percent"])
    robot_outputs.sort(key=lambda item: int(item["rank"]))
    leader = robot_outputs[0]
    forward_trades = int(leader["forward"]["trade_count"])
    qualified = forward_trades >= legacy.MIN_FORWARD_TRADES_FOR_CHAMPION
    selection_bias = selection_bias_diagnostics(len(robot_outputs), observed_trade_counts=[int(robot["forward"]["trade_count"]) for robot in robot_outputs])
    run_basis = {"latest_date": legacy._date_text(latest_date), "capital": capital, "universe": list(legacy.COMPETITION_UNIVERSE), "fingerprints": [robot["rule_fingerprint"] for robot in robot_outputs], "cost_model_id": cost_model.model_id}
    run_id = hashlib.sha256(json.dumps(run_basis, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    return {
        "run_id": run_id, "status": "completed", "executed_at": datetime.now(timezone.utc).isoformat(), "data_sources": sources or {},
        "periods": {"backtest": {"start": legacy._date_text(backtest_start), "end": legacy._date_text(backtest_end), "purpose": "固定規則的 2 個月歷史檢查，不在執行中調參。"}, "forward": {"start": legacy._date_text(forward_start), "end": legacy._date_text(latest_date), "purpose": "最後 1 個月 walk-forward 模擬；正式排名只使用此區間。"}},
        "fairness": {"initial_capital": round(capital, 2), "capital_per_symbol": round(per_symbol_capital, 2), "market_universe": list(legacy.COMPETITION_UNIVERSE), "cost_model_id": cost_model.model_id, "instrument_type": cost_model.instrument_type, "commission_rate": cost_model.commission_rate, "transaction_tax_rate": cost_model.transaction_tax_rate, "execution": "signal at close, execute next session open", "stop_model": f"{legacy.STOP_ATR_MULTIPLE:g} ATR", "target_model": f"{legacy.TARGET_ATR_MULTIPLE:g} ATR", "same_bar_stop_target_policy": "stop first (conservative)", "segment_end_policy": "mark_to_market_open_position", "runner_isolation": "no_global_monkeypatch"},
        "ranking": {"primary_metric": "forward Wilson 95% win-rate lower bound", "minimum_forward_trades_for_champion": legacy.MIN_FORWARD_TRADES_FOR_CHAMPION, "leader_status": "qualified" if qualified else "provisional", "selection_bias": selection_bias},
        "leader": {"robot_id": leader["robot_id"], "name": leader["name"], "rank": 1, "qualified": qualified, "reason": "已達最低前瞻交易樣本門檻。" if qualified else f"目前僅 {forward_trades} 筆前瞻交易，未達 {legacy.MIN_FORWARD_TRADES_FOR_CHAMPION} 筆門檻。"},
        "robots": robot_outputs,
        "disclosures": ["目前的 1 個月區間是 walk-forward 歷史模擬，不冒充部署後累積的真實實盤前瞻紀錄。", "EMA、RSI、MACD、布林通道、KD、成交量與 ATR 的具體期間／門檻是固定的 v1 實證參數，不代表論文證明其為最優值。", "現階段只做多、無槓桿，且每檔 ETF 使用固定等額資金；所有已完成交易均保存進出場與成本。", "交易成本由共用 TradingCostModel 提供，競賽 ETF 使用 TW-ETF-0.1425-0.1-v1。", "區間結束時仍持有的部位採收盤價 mark-to-market；不建立人工賣出交易，因此不計入勝率或 Wilson 樣本。", "16 個策略同時選冠軍存在 multiple-testing selection bias；目前顯示 Šidák/獨立假設診斷，尚未冒充 CSCV/PBO。"],
        "references": [legacy.BROCK_REFERENCE, legacy.MOMENTUM_REFERENCE, legacy.TIME_SERIES_MOMENTUM_REFERENCE, legacy.REVERSAL_REFERENCE, legacy.VOLUME_MOMENTUM_REFERENCE, legacy.VOLATILITY_REFERENCE, legacy.TECHNICAL_PATTERN_REFERENCE],
    }


def run_competition(initial_capital: float = DEFAULT_INITIAL_CAPITAL) -> dict[str, Any]:
    dataset = load_shared_research_dataset()
    result = run_competition_on_frames(
        dataset["frames"],
        initial_capital=initial_capital,
        sources=dataset["sources"],
    )
    result["research_history"] = dataset["universe_coverage"]
    return result
