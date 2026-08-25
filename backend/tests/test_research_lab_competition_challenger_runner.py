from __future__ import annotations

import math

import pandas as pd

from app.services.competition_runner import COMPETITION_UNIVERSE, _prepare_frame
from app.services.research_lab.competition_bridge import build_competition_challenger_roster
from app.services.research_lab.competition_challenger_runner import build_causal_score_series
from app.services.research_lab.competition_challenger_runner_v2 import (
    run_challenger_tournament_on_frames_v2,
)


def _synthetic_frame(offset: float) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-08-25", periods=1_500)
    prices = [
        50.0 + offset + index * 0.05 + math.sin(index / 5.0) * 2.0
        for index in range(len(dates))
    ]
    return pd.DataFrame(
        {
            "Open": [price * 0.999 for price in prices],
            "High": [price * 1.02 for price in prices],
            "Low": [price * 0.98 for price in prices],
            "Close": prices,
            "Volume": [1_000_000 + (index % 20) * 50_000 for index in range(len(dates))],
        },
        index=dates,
    )


def _certified_registry(opened_at_utc: str = "2026-08-20T00:00:00+00:00") -> dict:
    return {
        "schema_version": 2,
        "generated_at_utc": "2026-08-25T00:00:00+00:00",
        "certified_robot_count": 1,
        "robots": [
            {
                "certification_id": "cert-2882-001",
                "campaign_id": "2026-Q3",
                "stock_code": "2882",
                "candidate_id": "candidate-strong",
                "strategy_family": "score_engine",
                "parameters": {
                    "entry_score": 60,
                    "exit_score": 40,
                    "initial_capital": 100000,
                    "require_ema_trend": False,
                    "ema_fast_column": "EMA20",
                    "ema_slow_column": "EMA60",
                    "entry_mode": "score",
                    "exit_mode": "score_or_time",
                    "max_holding_days": 20,
                },
                "holdout_window": ["2025-03-13", "2026-06-30"],
                "opened_at_utc": opened_at_utc,
                "pre_holdout_research_run_id": "run-123",
                "status": "CERTIFIED_FINAL_HOLDOUT_PASS",
            }
        ],
    }


def test_causal_score_series_never_receives_future_rows() -> None:
    frame = _prepare_frame(_synthetic_frame(0.0))
    seen: list[tuple[pd.Timestamp, pd.Timestamp, int]] = []

    def fake_score(window: pd.DataFrame):
        seen.append((window.index[0], window.index[-1], len(window)))
        return 70.0, []

    values = build_causal_score_series(frame, score_fn=fake_score)

    assert len(values) == len(frame)
    assert all(length == 60 for _, _, length in seen)
    assert seen[0][1] == frame.index[59]
    assert seen[-1][1] == frame.index[-1]


def test_empty_roster_waits_without_downloading_or_competing() -> None:
    roster = build_competition_challenger_roster(
        {
            "schema_version": 2,
            "generated_at_utc": "2026-08-25T00:00:00+00:00",
            "certified_robot_count": 0,
            "robots": [],
        }
    )
    result = run_challenger_tournament_on_frames_v2({}, roster)
    assert result["status"] == "WAITING_FOR_CERTIFIED_ROBOT"
    assert result["challenger_count"] == 0
    assert result["promotion"]["challenger_replaced_incumbent"] is False


def test_newly_certified_challenger_is_quarantined_until_fresh_data_exists() -> None:
    frames = {
        code: _prepare_frame(_synthetic_frame(index * 3.0))
        for index, code in enumerate(COMPETITION_UNIVERSE)
    }
    roster = build_competition_challenger_roster(
        _certified_registry("2026-08-25T16:40:00+00:00")
    )

    result = run_challenger_tournament_on_frames_v2(
        frames,
        roster,
        initial_capital=100_000,
        score_fn=lambda _: (80.0, []),
    )

    assert result["status"] == "ACCUMULATING_POST_CERTIFICATION_EVIDENCE"
    assert result["common_fresh_window"]["start"] == "2026-08-27"
    assert result["common_fresh_window"]["available"] is False
    assert result["promotion"]["challenger_replaced_incumbent"] is False


def test_certified_challenger_and_incumbents_use_same_fresh_window() -> None:
    frames = {
        code: _prepare_frame(_synthetic_frame(index * 3.0))
        for index, code in enumerate(COMPETITION_UNIVERSE)
    }
    roster = build_competition_challenger_roster(_certified_registry())

    result = run_challenger_tournament_on_frames_v2(
        frames,
        roster,
        initial_capital=100_000,
        score_fn=lambda _: (80.0, []),
    )

    assert result["status"] == "completed"
    assert result["challenger_count"] == 1
    assert result["ranking"]["all_robot_count"] == 17
    assert result["common_fresh_window"]["start"] == "2026-08-21"
    assert result["evaluation_policy"]["post_certification_evidence_only"] is True
    assert result["evaluation_policy"]["final_holdout_overlap_forbidden"] is True
    periods = {
        (row["period_start"], row["period_end"])
        for row in result["ranking"]["robots"]
    }
    assert periods == {("2026-08-21", "2026-08-25")}
    challenger = result["challengers"][0]
    assert challenger["origin"] == "research_lab_certified"
    assert challenger["rank"] >= 1
    assert challenger["forward"]["initial_capital"] == 100_000
    assert result["promotion"]["competition_feedback_to_same_campaign_train"] is False
