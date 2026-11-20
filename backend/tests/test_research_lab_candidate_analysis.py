from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.services.research_lab.candidate_analysis import analyze_strongest_candidate
from app.services.strategy_rules import entry_predicates


TAIPEI = ZoneInfo("Asia/Taipei")


def archive() -> dict:
    return {
        "campaign_id": "2026-Q3",
        "source_generated_at_utc": "2026-09-22T15:22:24+00:00",
        "candidate": {
            "candidate_id": "frozen-best",
            "robot_version_id": "frozen-version-1",
            "stock_code": "2882",
            "strategy_family": "score_engine",
            "parameters": {
                "entry_score": 71,
                "exit_score": 2,
                "require_ema_trend": False,
                "entry_mode": "score",
                "exit_mode": "score_or_time",
                "max_holding_days": 20,
            },
            "confirmation_gate_pass_count": 5,
            "confirmation_gate_total": 6,
            "validation": {"total_return_percent": 55.55, "completed_trades": 6},
            "gate_reasons": ["bull_bear_robustness_failed"],
        },
    }


def frame() -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-11-20", periods=90, name="Date")
    return pd.DataFrame({
        "Open": 84.0, "High": 85.0, "Low": 83.0, "Close": 84.45,
        "Volume": 1000.0, "EMA20": 99.0, "EMA60": 103.0,
        "ATR": 3.7, "RSI": 25.0, "VolumeRatio": 1.0,
    }, index=dates)


def clock(hour: int = 16) -> datetime:
    return datetime(2026, 11, 20, hour, 0, tzinfo=TAIPEI)


@patch("app.services.research_lab.candidate_analysis.calculate_score")
def test_frozen_threshold_is_used_even_when_generic_hourly_gate_would_block(score):
    score.return_value = SimpleNamespace(total_score=73.0, trade_eligible=False)
    result = analyze_strongest_candidate("0050", frame(), archive(), now=clock())
    assert result["signal"]["action"] == "ENTRY_SIGNAL"
    assert result["signal"]["entry_threshold"] == 71
    assert result["parameters"]["exit_score"] == 2
    assert result["parameters"]["max_holding_days"] == 20
    # The archived model has no EMA gate and uses daily-only input.
    assert result["signal"]["entry_checks"]["ema_trend"] is True
    assert "hourly_df" not in score.call_args.kwargs
    assert len(score.call_args.args[0]) == 60


@patch("app.services.research_lab.candidate_analysis.calculate_score")
def test_source_return_is_never_relabelled_as_target_validation(score):
    score.return_value = SimpleNamespace(total_score=29.0)
    result = analyze_strongest_candidate("0050", frame(), archive(), now=clock())
    assert result["signal"]["action"] == "NO_ENTRY"
    assert result["signal"]["score_gap"] == 42
    assert result["source_validation"]["total_return_percent"] == 55.55
    assert result["source_stock_code"] == "2882"
    assert result["target_validation"] is None
    assert result["cross_asset_transfer"] is True
    assert result["certified"] is False
    assert result["opens_final_holdout"] is False
    assert result["feeds_train_memory"] is False


@patch("app.services.research_lab.candidate_analysis.calculate_score")
def test_incomplete_today_and_future_rows_never_reach_inference(score):
    score.return_value = SimpleNamespace(total_score=29.0)
    data = frame()
    future = data.iloc[[-1]].copy()
    future.index = pd.DatetimeIndex(["2026-11-23"], name="Date")
    future["Close"] = 9999
    result = analyze_strongest_candidate("0050", pd.concat([data, future]), archive(), now=clock(12))
    assert result["signal"]["as_of_date"] == "2026-11-19"
    assert score.call_args.args[0]["Date"].max() == pd.Timestamp("2026-11-19")
    result = analyze_strongest_candidate("0050", pd.concat([data, future]), archive(), now=clock(16))
    assert result["signal"]["as_of_date"] == "2026-11-20"
    assert result["signal"]["close"] == 84.45


@pytest.mark.parametrize("change", ["future_archive", "unsupported_rule", "missing_identity", "nan_threshold"])
def test_invalid_archive_cannot_silently_fall_back_to_generic_rules(change):
    record = deepcopy(archive())
    if change == "future_archive":
        record["source_generated_at_utc"] = "2027-01-01T00:00:00+00:00"
    elif change == "unsupported_rule":
        record["candidate"]["parameters"]["exit_mode"] = "invented"
    elif change == "missing_identity":
        del record["candidate"]["robot_version_id"]
    else:
        record["candidate"]["parameters"]["entry_score"] = float("nan")
    result = analyze_strongest_candidate("0050", frame(), record, now=clock())
    assert result["status"] == "UNAVAILABLE"
    assert "signal" not in result


def test_missing_or_stale_prices_stop_candidate_inference():
    assert analyze_strongest_candidate("0050", frame().head(20), archive(), now=clock())["status"] == "UNAVAILABLE"
    stale = frame().loc[:"2026-11-13"]
    assert analyze_strongest_candidate("0050", stale, archive(), now=clock())["status"] == "UNAVAILABLE"
    assert analyze_strongest_candidate("0050", frame(), {"error": "archive unavailable"}, now=clock())["status"] == "UNAVAILABLE"


def test_optional_volume_and_ema_rules_are_not_lost_during_transfer():
    row = frame().iloc[-1]
    checks = entry_predicates(row, 95, entry_score=71, entry_mode="score_and_volume_confirmation")
    assert checks["score_threshold"] is True
    assert checks["entry_structure"] is False
    checks = entry_predicates(row, 95, entry_score=71, require_ema_trend=True)
    assert checks["ema_trend"] is False
    with pytest.raises(ValueError, match="Unsupported entry_mode"):
        entry_predicates(row, 95, entry_score=71, entry_mode="unknown")
