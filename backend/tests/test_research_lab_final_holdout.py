from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.research_lab.final_holdout import (
    evaluate_final_holdout_once,
    ledger_path_for,
    load_existing_ledger,
)
from scripts.run_final_holdout_gate import build_certified_registry


def _eligible_payload() -> dict:
    return {
        "stock_code": "2882",
        "campaign": {"campaign_id": "2026-Q3"},
        "result": {
            "research_run_id": "run-123",
            "data_fingerprints": ["abc"],
            "selected_candidate": {
                "candidate_id": "candidate-strong",
                "strategy_family": "score_engine",
                "parameters": {
                    "entry_score": 60,
                    "exit_score": 40,
                    "initial_capital": 100000,
                    "require_ema_trend": False,
                    "entry_mode": "score",
                    "exit_mode": "score_or_time",
                    "max_holding_days": 40,
                },
                "parent_id": None,
                "hypothesis": "test",
            },
            "best_result": {"decision": "HOLDOUT_READY"},
            "split": {
                "train": ["2020-01-01", "2023-11-24"],
                "validation": ["2023-11-25", "2025-03-12"],
                "holdout": ["2025-03-13", "2026-06-30"],
            },
            "promotion_eligibility": {
                "eligible_for_one_shot_holdout": True,
                "reasons": [],
                "holdout_opened": False,
            },
            "holdout_status": "LOCKED_REQUIRES_PROMOTION_GATE",
            "research_audit": {
                "holdout_used_during_search": False,
                "training_memory": {"holdout_feedback_used": False},
            },
        },
    }


def _passing_report() -> dict:
    return {
        "performance_metrics": {
            "sharpe_ratio": 2.0,
            "sortino_ratio": 3.0,
            "calmar_ratio": 2.0,
        },
        "completed_trades": 4,
        "winning_trade_count": 4,
        "total_return_percent": 30.0,
        "max_drawdown_percent": 5.0,
        "win_rate_percent": 100.0,
        "alpha_percent": 20.0,
        "buy_and_hold": {"return_percent": 10.0},
        "research_return_series": {
            "strategy_daily_returns": [0.001] * 50,
            "benchmark_daily_returns": [0.0] * 50,
        },
        "score_series_cache": {"fingerprint": "holdout-fp", "schema": "v1"},
    }


def test_final_holdout_uses_only_declared_holdout_window_and_fixed_rubric() -> None:
    calls = []

    def fake_backtest(**kwargs):
        calls.append(kwargs)
        return _passing_report()

    record = evaluate_final_holdout_once(_eligible_payload(), backtest_fn=fake_backtest)

    assert len(calls) == 1
    assert calls[0]["start_date"] == "2025-03-13"
    assert calls[0]["end_date"] == "2026-06-30"
    assert calls[0]["liquidate_at_end"] is False
    assert calls[0]["include_research_series"] is True
    assert record["opened_once"] is True
    assert record["policy"]["holdout_feedback_to_train"] is False
    assert record["policy"]["candidate_generation_after_open"] is False
    assert record["result"]["status"] == "FINAL_HOLDOUT_PASS"
    assert record["result"]["passed"] is True


def test_final_holdout_refuses_candidate_before_all_promotion_gates_pass() -> None:
    payload = _eligible_payload()
    payload["result"]["promotion_eligibility"]["eligible_for_one_shot_holdout"] = False
    payload["result"]["promotion_eligibility"]["reasons"] = ["deflated_sharpe_failed"]

    with pytest.raises(ValueError, match="not eligible"):
        evaluate_final_holdout_once(payload, backtest_fn=lambda **_: _passing_report())


def test_existing_ledger_blocks_second_holdout_open(tmp_path: Path) -> None:
    payload = _eligible_payload()
    calls = []

    def fake_backtest(**kwargs):
        calls.append(kwargs)
        return _passing_report()

    record = evaluate_final_holdout_once(payload, backtest_fn=fake_backtest)
    path = ledger_path_for(payload, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    existing = load_existing_ledger(path, payload)

    assert existing is not None
    assert existing["evaluation_id"] == record["evaluation_id"]
    assert len(calls) == 1


def test_ledger_identity_collision_is_fail_closed(tmp_path: Path) -> None:
    payload = _eligible_payload()
    path = ledger_path_for(payload, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"evaluation_id":"wrong","identity":{},"opened_once":true}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identity collision"):
        load_existing_ledger(path, payload)


def test_certified_registry_contains_only_final_holdout_passes(tmp_path: Path) -> None:
    passing_payload = _eligible_payload()
    passing_record = evaluate_final_holdout_once(
        passing_payload,
        backtest_fn=lambda **_: _passing_report(),
    )
    passing_path = ledger_path_for(passing_payload, tmp_path)
    passing_path.parent.mkdir(parents=True, exist_ok=True)
    passing_path.write_text(json.dumps(passing_record), encoding="utf-8")

    failing_payload = _eligible_payload()
    failing_payload["stock_code"] = "00919"
    failing_payload["result"]["selected_candidate"]["candidate_id"] = "candidate-fail"
    failing_record = evaluate_final_holdout_once(
        failing_payload,
        backtest_fn=lambda **_: {
            **_passing_report(),
            "completed_trades": 1,
            "winning_trade_count": 0,
            "total_return_percent": -2.0,
            "max_drawdown_percent": 12.0,
            "win_rate_percent": 0.0,
            "alpha_percent": -3.0,
        },
    )
    failing_path = ledger_path_for(failing_payload, tmp_path)
    failing_path.parent.mkdir(parents=True, exist_ok=True)
    failing_path.write_text(json.dumps(failing_record), encoding="utf-8")

    registry = build_certified_registry(tmp_path)

    assert registry["certified_robot_count"] == 1
    assert registry["robots"][0]["stock_code"] == "2882"
    assert registry["robots"][0]["status"] == "CERTIFIED_FINAL_HOLDOUT_PASS"
    assert "Holdout scores are not used to rank" in registry["selection_policy"]
