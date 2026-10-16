from dataclasses import asdict
from datetime import date

import pytest

from app.services.research_lab.evolution import (
    SEARCH_SPACE_SCHEMA,
    candidate_parameter_signature,
    generate_parameter_candidates,
    generate_signal_dominant_candidates,
)
from app.services.research_lab.exploration import (
    generate_alpha_exploration,
    iter_alpha_continuation,
)
from app.services.research_lab.training_memory import (
    TRAIN_DATA_IDENTITY_SCHEMA,
    DailyCandidatePlan,
    build_training_memory,
    prepare_daily_candidate_plan,
)
import scripts.run_daily_autoresearch as daily


def _exhausted_memory():
    legacy = generate_parameter_candidates() + generate_alpha_exploration(
        generate_signal_dominant_candidates(),
    )
    return {
        "schema_version": 1, "search_space_schema": SEARCH_SPACE_SCHEMA,
        "provenance": "TRAIN_ONLY", "stock_code": "3037", "campaign_id": "2026-Q4",
        "train_window": ["2020-01-01", "2024-01-18"],
        "train_data_identity_schema": TRAIN_DATA_IDENTITY_SCHEMA,
        "train_data_identity": "unchanged-real-inputs",
        "seen_parameter_signatures": sorted({candidate_parameter_signature(c) for c in legacy}),
        "frontier": [], "elites": [], "train_trial_period_sharpes": [0.1, 0.2],
        "lifetime_experiment_count": len(legacy), "lifetime_run_count": 25,
        "consecutive_no_new_experiment_runs": 3,
        "validation_feedback_used": False, "holdout_feedback_used": False,
    }


def _plan(memory, budget=64):
    return prepare_daily_candidate_plan(
        stock_code="3037", campaign_id=memory["campaign_id"],
        train_window=tuple(memory["train_window"]),
        train_data_identity=memory["train_data_identity"],
        rotated_grid=generate_parameter_candidates(), prior_memory=memory,
        minimum_candidate_count=budget,
    )


def _result(candidates):
    return {
        "research_run_id": "continuation-test",
        "research_audit": {
            "validation_used_during_adaptive_search": False,
            "holdout_used_during_search": False,
        },
        "rounds": [{
            "evaluation_phase": "train", "survivors": [],
            "evaluated": [{
                "candidate": asdict(c), "decision": "DISCARD", "research_score": 0,
                "evaluation_phase": "train", "reasons": [],
                "validation_metrics": {"statistical_evidence": {"period_sharpe_ratio": 0.01}},
            } for c in candidates],
        }],
    }


def test_exhausted_search_resumes_across_runs_without_reset_or_feedback():
    memory = _exhausted_memory()
    original_seen = set(memory["seen_parameter_signatures"])
    initial_trials = len(memory["train_trial_period_sharpes"])
    for run in range(8):
        before = set(memory["seen_parameter_signatures"])
        plan = _plan(memory)
        assert len(plan.candidates) >= 64
        assert plan.audit["memory_reset_reason"] is None
        assert plan.audit["continuation"]["novel_candidate_count"] > 0
        signatures = [candidate_parameter_signature(c) for c in plan.candidates]
        assert len(set(signatures)) == len(signatures)
        assert before.isdisjoint(signatures)
        assert _plan({**memory, "validation_results": {"preferred_duration": 17},
                      "holdout_results": {"profit": 999}}).candidates == plan.candidates
        memory = build_training_memory(
            stock_code="3037", campaign_id=memory["campaign_id"],
            train_window=tuple(memory["train_window"]),
            train_data_identity=memory["train_data_identity"], as_of_date="2026-10-16",
            result=_result(plan.candidates[:64]), prior_memory=memory,
        )
        assert original_seen <= set(memory["seen_parameter_signatures"])
        assert len(memory["train_trial_period_sharpes"]) == initial_trials + (run + 1) * 64
        assert memory["consecutive_no_new_experiment_runs"] == 0
        assert memory["search_state"] == "ADVANCING"


def test_history_beyond_ten_thousand_is_not_forgotten():
    memory = _exhausted_memory()
    memory["seen_parameter_signatures"] = [f"past-{i:024d}" for i in range(10_001)]
    memory["train_trial_period_sharpes"] = [0.1] * 10_001
    result = build_training_memory(
        stock_code="3037", campaign_id=memory["campaign_id"],
        train_window=tuple(memory["train_window"]),
        train_data_identity=memory["train_data_identity"], as_of_date="2026-10-16",
        result=_result(generate_parameter_candidates()[:1]), prior_memory=memory,
    )
    assert set(memory["seen_parameter_signatures"]) <= set(result["seen_parameter_signatures"])
    assert len(result["seen_parameter_signatures"]) == 10_002
    assert len(result["train_trial_period_sharpes"]) == 10_002


def test_small_continuation_budget_covers_multiple_horizons_and_risk_settings():
    candidates = _plan(_exhausted_memory()).candidates[:64]
    durations = {c.parameters["max_holding_days"] for c in candidates}
    assert len(durations) >= 3
    assert any(days <= 20 for days in durations)
    assert any(20 < days <= 80 for days in durations)
    assert any(days > 80 for days in durations)
    risk_settings = {
        (c.parameters["atr_target_percent"], c.parameters["max_position_fraction"])
        for c in candidates if c.parameters.get("atr_target_percent") is not None
    }
    assert len(risk_settings) >= 3


def test_continuation_preserves_execution_limits_and_has_a_finite_end():
    memory = _exhausted_memory()
    seen = set(memory["seen_parameter_signatures"])
    for c in iter_alpha_continuation(generate_signal_dominant_candidates()):
        p = c.parameters
        assert p["entry_score"] == 1 and p["exit_score"] == 0
        assert 2 <= p["max_holding_days"] <= 252
        assert 0 < p.get("min_position_fraction", 1) <= p.get("max_position_fraction", 1) <= 1
        seen.add(candidate_parameter_signature(c))
    memory["seen_parameter_signatures"] = sorted(seen)
    plan = _plan(memory)
    assert not plan.candidates
    assert plan.audit["continuation"]["catalog_exhausted"] is True


def test_daily_runner_refuses_to_publish_exhaustion_as_success(monkeypatch):
    monkeypatch.setattr(daily, "prepare_daily_candidate_plan", lambda **_: DailyCandidatePlan(
        candidates=(), excluded_parameter_signatures=frozenset(),
        prior_train_trial_sharpes=(), audit={},
    ))
    called = []
    with pytest.raises(RuntimeError, match="SEARCH_SPACE_EXHAUSTED"):
        daily.execute_daily_stock_research(
            "3037", date(2026, 10, 16),
            train_identity_resolver=lambda **_: "fixed",
            research_runner=lambda **_: called.append(True),
        )
    assert not called


def test_daily_runner_refuses_a_zero_experiment_engine_result():
    with pytest.raises(RuntimeError, match="SEARCH_STALLED"):
        daily.execute_daily_stock_research(
            "3037", date(2026, 10, 16),
            train_identity_resolver=lambda **_: "fixed",
            research_runner=lambda **_: {
                "experiments_run": 0,
                "holdout_status": "LOCKED_REQUIRES_PROMOTION_GATE",
                "promotion_eligibility": {"holdout_opened": False},
                "research_audit": {
                    "holdout_used_during_search": False,
                    "training_memory": {
                        "validation_feedback_used": False,
                        "holdout_feedback_used": False,
                    },
                },
            },
        )
