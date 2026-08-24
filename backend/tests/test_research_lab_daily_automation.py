from __future__ import annotations

from datetime import date

import pytest

from app.api.research_lab import _rotated_parameter_candidates
from scripts.aggregate_daily_autoresearch import aggregate_payloads
from scripts.run_daily_autoresearch import (
    campaign_window,
    candidate_offset_for,
    execute_daily_stock_research,
)


def _research_result(
    stock_code: str,
    *,
    eligible: bool,
    score: float,
) -> dict[str, object]:
    return {
        "research_run_id": f"run-{stock_code}",
        "data_fingerprints": [f"data-{stock_code}"],
        "stock_code": stock_code,
        "experiments_run": 24,
        "selected_candidate": {
            "candidate_id": f"candidate-{stock_code}",
            "parent_id": "parent-1",
            "strategy_family": "score_engine",
            "hypothesis": "test hypothesis",
            "parameters": {"entry_score": 60, "exit_score": 40},
        },
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
            "holdout_used_during_search": False,
        },
        "holdout_status": "LOCKED_REQUIRES_PROMOTION_GATE",
    }


def _daily_payload(stock_code: str, *, eligible: bool, score: float) -> dict[str, object]:
    return {
        "schema_version": 1,
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


def test_daily_runner_never_opens_holdout() -> None:
    captured: dict[str, object] = {}

    def fake_runner(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return _research_result("2330", eligible=False, score=30.0)

    payload = execute_daily_stock_research(
        "2330",
        date(2026, 8, 25),
        research_runner=fake_runner,
    )
    assert captured["candidate_offset"] == payload["automation"]["candidate_offset"]
    assert captured["end_date"] == date(2026, 6, 30)
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
        )


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
