from __future__ import annotations

from datetime import date

import pytest
import scripts.run_daily_autoresearch as daily_runner

from app.api.research_lab import _rotated_parameter_candidates
from app.services.research_lab.evolution import SEARCH_SPACE_SCHEMA
from app.services.research_lab.training_memory import (
    TRAIN_DATA_IDENTITY_SCHEMA,
    TRAINING_MEMORY_SCHEMA_VERSION,
)
from scripts.aggregate_daily_autoresearch import aggregate_payloads
from scripts.run_daily_autoresearch import (
    campaign_window,
    candidate_offset_for,
    execute_daily_stock_research,
    resolve_train_data_identity,
)


def _research_result(
    stock_code: str,
    *,
    eligible: bool,
    score: float,
) -> dict[str, object]:
    candidate = {
        "candidate_id": f"candidate-{stock_code}",
        "parent_id": "parent-1",
        "strategy_family": "score_engine",
        "hypothesis": "test hypothesis",
        "parameters": {
            "entry_score": 60,
            "exit_score": 40,
            "initial_capital": 1_000_000,
            "entry_mode": "score",
        },
    }
    return {
        "research_run_id": f"run-{stock_code}",
        "data_fingerprints": [f"data-{stock_code}"],
        "stock_code": stock_code,
        "experiments_run": 24,
        "selected_candidate": candidate,
        "best_result": {
            "decision": "HOLDOUT_READY" if eligible else "KEEP",
            "research_score": score,
            "validation_metrics": {
                "completed_trades": 12,
                "win_rate_percent": 66.7,
                "wilson_win_rate_lower_bound_percent": 40.0,
                "total_return_percent": 12.0,
                "alpha_percent": 4.0,
                "max_drawdown_percent": 8.0,
                "statistical_evidence": {
                    "probabilistic_sharpe_ratio_percent": 96.0,
                },
                "deflated_sharpe": {
                    "deflated_sharpe_probability_percent": 94.0,
                },
            },
        },
        "market_regime_tournament": [
            {
                "market_regime_matrix": {
                    "robustness": {
                        "robust_across_required_regimes": eligible,
                        "robustness_score": 75.0 if eligible else 35.0,
                    }
                }
            }
        ],
        "walk_forward_matrix": {
            "aggregate": {"positive_slice_ratio": 0.75 if eligible else 0.5}
        },
        "promotion_eligibility": {
            "eligible_for_one_shot_holdout": eligible,
            "reasons": [] if eligible else ["hansen_spa_failed_or_unavailable"],
            "holdout_opened": False,
        },
        "research_audit": {
            "validation_used_during_adaptive_search": False,
            "holdout_used_during_search": False,
            "training_memory": {
                "validation_feedback_used": False,
                "holdout_feedback_used": False,
            },
        },
        "holdout_status": "LOCKED_REQUIRES_PROMOTION_GATE",
        "rounds": [
            {
                "generation": 1,
                "evaluation_phase": "train",
                "evaluated": [
                    {
                        "candidate": candidate,
                        "validation_metrics": {
                            "data_fingerprint": f"data-{stock_code}",
                        },
                        "decision": "KEEP",
                        "research_score": score,
                        "reasons": [],
                        "evaluation_phase": "train",
                    }
                ],
                "survivors": [],
            }
        ],
    }


def _training_memory(stock_code: str) -> dict[str, object]:
    return {
        "schema_version": TRAINING_MEMORY_SCHEMA_VERSION,
        "search_space_schema": SEARCH_SPACE_SCHEMA,
        "provenance": "TRAIN_ONLY",
        "stock_code": stock_code,
        "campaign_id": "2026-Q3",
        "train_window": ["2020-01-01", "2023-11-04"],
        "as_of_date": "2026-08-25",
        "memory_id": f"memory-{stock_code}",
        "train_data_identity_schema": TRAIN_DATA_IDENTITY_SCHEMA,
        "train_data_identity": f"canonical-data-{stock_code}",
        "train_data_identity_verified": True,
        "train_data_identity_migrated": False,
        "seen_parameter_signatures": [f"signature-{stock_code}"],
        "elites": [],
        "frontier": [],
        "strategy_families": ["score_engine"],
        "train_trial_period_sharpes": [0.1],
        "lifetime_experiment_count": 1,
        "lifetime_run_count": 1,
        "last_run_new_experiment_count": 1,
        "last_run_duplicate_skip_count": 0,
        "memory_reset_reason": "missing",
        "validation_feedback_used": False,
        "holdout_feedback_used": False,
    }


def _daily_payload(stock_code: str, *, eligible: bool, score: float) -> dict[str, object]:
    return {
        "schema_version": 2,
        "automation": {"candidate_offset": 3},
        "as_of_date": "2026-08-25",
        "campaign": {
            "campaign_id": "2026-Q3",
            "start_date": "2020-01-01",
            "end_date": "2026-06-30",
        },
        "generated_at_utc": "2026-08-25T10:30:00+00:00",
        "stock_code": stock_code,
        "result": _research_result(stock_code, eligible=eligible, score=score),
        "training_memory": _training_memory(stock_code),
    }


def test_campaign_window_is_frozen_for_the_quarter() -> None:
    first = campaign_window(date(2026, 7, 1))
    last = campaign_window(date(2026, 9, 30))
    assert first == last == {
        "campaign_id": "2026-Q3",
        "start_date": "2020-01-01",
        "end_date": "2026-06-30",
    }


def test_daily_candidate_rotation_is_reproducible_and_bounded() -> None:
    research_date = date(2026, 8, 25)
    offset = candidate_offset_for("2330", research_date)
    assert offset == candidate_offset_for("2330", research_date)
    candidates = _rotated_parameter_candidates(offset)
    assert candidates
    assert len({candidate.candidate_id for candidate in candidates}) == len(candidates)


def test_train_data_identity_uses_one_fixed_train_only_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_backtest(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "actual_start_date": "2020-01-02",
            "actual_end_date": "2023-11-24",
            "score_series_cache": {
                "schema": "score-series-v1",
                "fingerprint": "stable-frame-fingerprint",
            },
        }

    monkeypatch.setattr(daily_runner, "backtest_stock", fake_backtest)
    identity = resolve_train_data_identity(
        stock_code="00878",
        train_start="2020-01-01",
        train_end="2023-11-24",
    )
    assert len(identity) == 24
    assert captured["start_date"] == "2020-01-01"
    assert captured["end_date"] == "2023-11-24"
    assert captured["entry_mode"] == "score"
    assert captured["require_ema_trend"] is False
    assert captured["include_research_series"] is False


def test_daily_runner_never_opens_holdout() -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return _research_result("2330", eligible=False, score=30.0)

    payload = execute_daily_stock_research(
        "2330",
        date(2026, 8, 25),
        research_runner=fake_runner,
        train_identity_resolver=lambda **_: "canonical-train-v1",
    )
    assert captured["candidate_offset"] == payload["automation"]["candidate_offset"]
    assert captured["end_date"] == date(2026, 6, 30)
    assert captured["initial_candidates"]
    assert payload["training_memory"]["provenance"] == "TRAIN_ONLY"
    assert payload["result"]["promotion_eligibility"]["holdout_opened"] is False


def test_daily_runner_fails_closed_if_holdout_is_opened() -> None:
    def unsafe_runner(**_: object) -> dict[str, object]:
        result = _research_result("2330", eligible=True, score=80.0)
        result["promotion_eligibility"]["holdout_opened"] = True
        return result

    with pytest.raises(RuntimeError, match="holdout was opened"):
        execute_daily_stock_research(
            "2330",
            date(2026, 8, 25),
            research_runner=unsafe_runner,
            train_identity_resolver=lambda **_: "canonical-train-v1",
        )


def test_daily_runner_blocks_promotion_when_train_data_revision_resets_memory() -> None:
    call_count = 0

    def changing_identity(**_: object) -> str:
        nonlocal call_count
        call_count += 1
        return f"canonical-train-v{call_count}"

    def eligible_runner(**_: object) -> dict[str, object]:
        return _research_result("2330", eligible=True, score=80.0)

    first = execute_daily_stock_research(
        "2330",
        date(2026, 8, 25),
        research_runner=eligible_runner,
        train_identity_resolver=changing_identity,
    )
    second = execute_daily_stock_research(
        "2330",
        date(2026, 8, 26),
        prior_training_memory=first["training_memory"],
        research_runner=eligible_runner,
        train_identity_resolver=changing_identity,
    )
    assert second["training_memory"]["memory_reset_reason"] == (
        "train_data_revision"
    )
    assert second["result"]["promotion_eligibility"][
        "eligible_for_one_shot_holdout"
    ] is False
    assert (
        "train_data_revision_requires_fresh_cumulative_evidence"
        in second["result"]["promotion_eligibility"]["reasons"]
    )


def test_daily_runner_requires_two_matching_train_data_identities() -> None:
    def eligible_runner(**_: object) -> dict[str, object]:
        return _research_result("2330", eligible=True, score=80.0)

    def stable_identity(**_: object) -> str:
        return "canonical-train-v1"

    first = execute_daily_stock_research(
        "2330",
        date(2026, 8, 25),
        research_runner=eligible_runner,
        train_identity_resolver=stable_identity,
    )
    assert first["training_memory"]["train_data_identity_verified"] is False
    assert first["result"]["promotion_eligibility"][
        "eligible_for_one_shot_holdout"
    ] is False
    assert (
        "train_data_identity_requires_consecutive_confirmation"
        in first["result"]["promotion_eligibility"]["reasons"]
    )

    second = execute_daily_stock_research(
        "2330",
        date(2026, 8, 26),
        prior_training_memory=first["training_memory"],
        research_runner=eligible_runner,
        train_identity_resolver=stable_identity,
    )
    assert second["training_memory"]["train_data_identity_verified"] is True
    assert second["result"]["promotion_eligibility"][
        "eligible_for_one_shot_holdout"
    ] is True


def test_aggregate_requires_every_symbol_and_versions_candidates() -> None:
    payload = aggregate_payloads(
        [
            _daily_payload("0050", eligible=False, score=90.0),
            _daily_payload("2330", eligible=True, score=60.0),
        ],
        as_of_date=date(2026, 8, 25),
        expected_universe=("0050", "2330"),
    )
    assert payload["integrity_status"] == "PASS"
    assert payload["holdout_opened"] is False
    assert payload["eligible_candidate_count"] == 1
    assert payload["top_candidate"]["stock_code"] == "2330"
    assert payload["training_memory"]["completed_symbol_count"] == 2
    assert payload["training_memory"][
        "verified_data_identity_symbol_count"
    ] == 2
    assert payload["training_memory"]["validation_feedback_used"] is False
    assert len(payload["top_candidate"]["robot_version_id"]) == 24

    repeated = aggregate_payloads(
        [
            _daily_payload("0050", eligible=False, score=90.0),
            _daily_payload("2330", eligible=True, score=60.0),
        ],
        as_of_date=date(2026, 8, 25),
        expected_universe=("0050", "2330"),
    )
    assert (
        repeated["top_candidate"]["robot_version_id"]
        == payload["top_candidate"]["robot_version_id"]
    )


def test_aggregate_refuses_partial_daily_universe() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        aggregate_payloads(
            [_daily_payload("0050", eligible=False, score=10.0)],
            as_of_date=date(2026, 8, 25),
            expected_universe=("0050", "2330"),
        )
