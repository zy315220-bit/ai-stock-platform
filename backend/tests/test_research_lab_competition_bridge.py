from __future__ import annotations

import pytest

from app.services.research_lab.competition_bridge import (
    QUEUE_STATUS,
    WAITING_STATUS,
    build_competition_challenger,
    build_competition_challenger_roster,
)


def _certified_robot() -> dict:
    return {
        "certification_id": "holdout-eval-001",
        "campaign_id": "2026-Q3",
        "stock_code": "2882",
        "candidate_id": "candidate-strong",
        "strategy_family": "score_engine_rsi_confirmed",
        "parameters": {
            "entry_score": 65,
            "exit_score": 40,
            "initial_capital": 1_000_000.0,
            "require_ema_trend": True,
            "ema_fast_column": "EMA20",
            "ema_slow_column": "EMA60",
            "entry_mode": "score_and_rsi_momentum",
            "exit_mode": "score_or_time_or_ema_reversal",
            "max_holding_days": 40,
        },
        "holdout_window": ["2025-03-13", "2026-06-30"],
        "opened_at_utc": "2026-08-25T16:40:00+00:00",
        "pre_holdout_research_run_id": "research-run-123",
        "candidate": {"research_score": 88.0},
        "status": "CERTIFIED_FINAL_HOLDOUT_PASS",
    }


def _registry(*robots: dict) -> dict:
    return {
        "schema_version": 2,
        "generated_at_utc": "2026-08-25T16:42:14+00:00",
        "certified_robot_count": len(robots),
        "robots": list(robots),
    }


def test_empty_certified_registry_publishes_explicit_waiting_queue() -> None:
    roster = build_competition_challenger_roster(_registry())

    assert roster["status"] == WAITING_STATUS
    assert roster["challenger_count"] == 0
    assert roster["challengers"] == []
    assert roster["policy"]["automatic_activation_when_certified"] is True
    assert roster["policy"]["same_campaign_competition_feedback_to_train"] is False


def test_certified_robot_becomes_immutable_challenger_with_competition_rebinding() -> None:
    robot = _certified_robot()
    first = build_competition_challenger(robot)
    second = build_competition_challenger(robot)

    assert first == second
    assert first["status"] == QUEUE_STATUS
    assert first["immutable"] is True
    assert first["rule_fingerprint"]
    assert first["challenger_id"].startswith("CH-")
    assert first["robot_id"].startswith("RESEARCH-2882-")

    spec = first["spec"]
    assert "initial_capital" not in spec["parameters"]
    assert first["research_provenance"]["research_initial_capital"] == 1_000_000.0
    assert spec["competition_contract"]["competition_sets_initial_capital"] is True
    assert spec["competition_contract"]["competition_sets_cost_model"] is True
    assert spec["competition_contract"]["competition_sets_risk_model"] is True
    assert spec["competition_contract"]["competition_sets_market_universe"] is True
    assert (
        spec["competition_contract"]["final_holdout_score_used_for_competition_ranking"]
        is False
    )
    assert (
        spec["competition_contract"]["same_campaign_competition_feedback_to_train"]
        is False
    )


def test_roster_contains_only_certified_final_holdout_passes() -> None:
    robot = _certified_robot()
    roster = build_competition_challenger_roster(_registry(robot))

    assert roster["status"] == "READY"
    assert roster["challenger_count"] == 1
    assert roster["challengers"][0]["research_provenance"]["certification_id"] == (
        "holdout-eval-001"
    )

    robot["status"] = "FINAL_HOLDOUT_FAIL"
    with pytest.raises(ValueError, match="CERTIFIED_FINAL_HOLDOUT_PASS"):
        build_competition_challenger_roster(_registry(robot))


def test_bridge_rejects_unknown_research_parameters() -> None:
    robot = _certified_robot()
    robot["parameters"]["look_at_holdout"] = True

    with pytest.raises(ValueError, match="unsupported research parameters"):
        build_competition_challenger(robot)


def test_bridge_fails_closed_on_registry_count_mismatch() -> None:
    registry = _registry(_certified_robot())
    registry["certified_robot_count"] = 2

    with pytest.raises(ValueError, match="count does not match"):
        build_competition_challenger_roster(registry)
