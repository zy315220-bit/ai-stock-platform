"""Run the archived strongest candidate without changing its trading rules.

Inference is observational. It cannot certify a candidate, read Final Holdout,
or write evidence back into the autonomous search.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time
import math
from threading import Lock
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from score_engine.calculate import calculate_score
from app.services.strategy_rules import entry_predicates


ARCHIVE_URL = (
    "https://raw.githubusercontent.com/zy315220-bit/ai-stock-platform/"
    "research-data/daily/all-time-incumbent.json"
)
_ARCHIVE_LOCK = Lock()
_ARCHIVE_CACHE: tuple[float, dict[str, Any]] | None = None
_TAIPEI = ZoneInfo("Asia/Taipei")


def unavailable(reason: str) -> dict[str, Any]:
    return {"status": "UNAVAILABLE", "reason": reason, "certified": False}


def load_strongest_archive() -> dict[str, Any]:
    global _ARCHIVE_CACHE
    with _ARCHIVE_LOCK:
        if _ARCHIVE_CACHE and monotonic() < _ARCHIVE_CACHE[0]:
            return deepcopy(_ARCHIVE_CACHE[1])
    try:
        response = requests.get(
            ARCHIVE_URL,
            headers={"Accept": "application/json"},
            timeout=(10, 10),
        )
        response.raise_for_status()
        archive = response.json()
        if not isinstance(archive, dict) or not isinstance(archive.get("candidate"), dict):
            raise ValueError("invalid candidate archive")
    except (requests.RequestException, ValueError):
        return {"error": "歷史最強版本暫時無法取得，這次沒有以通用分數冒充該版本。"}
    with _ARCHIVE_LOCK:
        _ARCHIVE_CACHE = (monotonic() + 300, archive)
    return deepcopy(archive)


def _parameters(candidate: dict[str, Any]) -> dict[str, Any]:
    params = dict(candidate["parameters"])
    if not candidate.get("robot_version_id") or not candidate.get("stock_code"):
        raise ValueError("candidate identity is missing")
    entry = float(params["entry_score"])
    exit_score = float(params["exit_score"])
    if not (math.isfinite(entry) and math.isfinite(exit_score) and 0 <= exit_score < entry <= 100):
        raise ValueError("invalid score thresholds")
    if params.get("exit_mode", "score") not in {
        "score", "score_or_time", "score_or_ema_reversal",
        "score_or_time_or_ema_reversal", "mean_reversion_or_time",
    }:
        raise ValueError("unsupported exit mode")
    holding_days = params.get("max_holding_days", 60)
    if type(holding_days) is not int or not 2 <= holding_days <= 252:
        raise ValueError("invalid holding period")
    for name in ("ema_fast_column", "ema_slow_column"):
        if params.get(name, "EMA20" if name == "ema_fast_column" else "EMA60") not in {
            "EMA5", "EMA20", "EMA60",
        }:
            raise ValueError("unsupported EMA column")
    params.update(entry_score=entry, exit_score=exit_score)
    return params


def analyze_strongest_candidate(
    stock_code: str,
    indicator_frame: pd.DataFrame,
    archive: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate the same 60-session, daily-close input used by the backtest.

    No live quote or hourly gate is substituted for the archived daily rule.
    During a trading session, today's incomplete candle is excluded.
    """
    if archive.get("error"):
        return unavailable(str(archive["error"]))
    clock = now or datetime.now(_TAIPEI)
    if clock.tzinfo is None:
        raise ValueError("now must include a timezone")
    clock = clock.astimezone(_TAIPEI)
    try:
        candidate = archive["candidate"]
        params = _parameters(candidate)
        frame = indicator_frame.copy()
        dates = pd.to_datetime(frame["Date"] if "Date" in frame else frame.index)
        dates = pd.DatetimeIndex(dates)
        if dates.tz is not None:
            dates = dates.tz_convert(_TAIPEI).tz_localize(None)
        frame = frame.reset_index(drop=True)
        frame["Date"] = dates.normalize()
        cutoff = pd.Timestamp(clock.date())
        if clock.time().replace(tzinfo=None) < time(13, 30):
            cutoff -= pd.Timedelta(days=1)
        frame = frame.loc[frame["Date"] <= cutoff].sort_values("Date")
        frame = frame.drop_duplicates("Date", keep="last")
        if len(frame) < 60:
            return unavailable("完整收盤資料不足 60 筆，無法重現研究版本的輸入。")
        latest = frame.iloc[-1]
        signal_date = pd.Timestamp(latest["Date"])
        if (pd.Timestamp(clock.date()) - signal_date).days > 4:
            return unavailable("收盤行情已過期，暫停產生研究版本訊號。")
        selected_at = pd.Timestamp(archive["source_generated_at_utc"])
        if selected_at.tzinfo is None:
            raise ValueError("missing archive timezone")
        if selected_at > pd.Timestamp(clock):
            raise ValueError("candidate was not available as of inference time")
        score_result = calculate_score(frame.tail(60), return_details=True)
        score = float(score_result.total_score)
        if not math.isfinite(score):
            raise ValueError("invalid score")
        checks = entry_predicates(
            latest,
            score,
            entry_score=params["entry_score"],
            require_ema_trend=params.get("require_ema_trend", False),
            ema_fast_column=params.get("ema_fast_column", "EMA20"),
            ema_slow_column=params.get("ema_slow_column", "EMA60"),
            entry_mode=params.get("entry_mode", "score"),
        )
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return unavailable("候選版本或行情欄位不完整，這次無法執行該版本。")

    cross_asset = str(candidate["stock_code"]).upper() != stock_code.upper()
    entry_signal = all(checks.values())
    validation = candidate.get("validation") or {}
    return {
        "status": "READY",
        "selection": "ALL_TIME_STRONGEST_ARCHIVED_EVIDENCE",
        "model_id": candidate["robot_version_id"],
        "candidate_id": candidate["candidate_id"],
        "strategy_family": candidate["strategy_family"],
        "source_stock_code": candidate["stock_code"],
        "target_stock_code": stock_code,
        "source_campaign": archive.get("campaign_id"),
        "selected_at": archive["source_generated_at_utc"],
        "parameters": params,
        "certified": False,
        "gate_pass_count": candidate.get("confirmation_gate_pass_count"),
        "gate_total": candidate.get("confirmation_gate_total"),
        "gate_failures": candidate.get("gate_reasons") or [],
        "source_validation": validation,
        "target_validation": None,
        "cross_asset_transfer": cross_asset,
        "evidence_note": (
            f"歷史成績來自 {candidate['stock_code']}；此固定版本在 {stock_code} 尚無獨立驗證成績。"
            if cross_asset else
            "歷史成績屬於原研究期間，未完成本期驗證及最終認證。"
        ),
        "signal": {
            "action": "ENTRY_SIGNAL" if entry_signal else "NO_ENTRY",
            "title": "最強版本出現試驗進場訊號" if entry_signal else "最強版本目前沒有進場訊號",
            "as_of_date": signal_date.strftime("%Y-%m-%d"),
            "close": float(latest["Close"]),
            "score": round(score, 4),
            "entry_threshold": params["entry_score"],
            "score_gap": round(max(0.0, params["entry_score"] - score), 4),
            "entry_checks": checks,
            "input_rows": 60,
            "timeframe": "DAILY_CLOSE",
            "execution": "NEXT_SESSION_OPEN",
            "holding_exit_requires_entry_date": True,
        },
        "inference_only": True,
        "feeds_train_memory": False,
        "opens_final_holdout": False,
    }
