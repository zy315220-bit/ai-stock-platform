from app.services.research_lab.evolution import (
    candidate_parameter_signature, evolve_candidates, generate_parameter_candidates,
    generate_signal_dominant_candidates,
)
from app.services.research_lab.exploration import generate_alpha_exploration
from app.services.research_lab.models import ExperimentDecision, ExperimentResult
from app.services.research_lab.training_memory import (
    FAMILY_COVERAGE_BUCKETS, TRAIN_DATA_IDENTITY_SCHEMA, prepare_daily_candidate_plan,
)


def test_exhausted_base_grid_still_has_novel_alpha_candidates_without_reset():
    grid = generate_parameter_candidates()
    seen = {candidate_parameter_signature(candidate) for candidate in grid}
    memory = {
        "schema_version": 1, "search_space_schema": "alpha-family-diversity-v5",
        "provenance": "TRAIN_ONLY", "stock_code": "3037", "campaign_id": "2026-Q3",
        "train_window": ["2020-01-01", "2023-11-24"], "train_data_identity": "fixed",
        "train_data_identity_schema": TRAIN_DATA_IDENTITY_SCHEMA,
        "validation_feedback_used": False, "holdout_feedback_used": False,
        "seen_parameter_signatures": sorted(seen), "frontier": [], "elites": [],
        "train_trial_period_sharpes": [0.1, 0.2],
    }
    kwargs = dict(stock_code="3037", campaign_id="2026-Q3", train_window=tuple(memory["train_window"]), train_data_identity="fixed", rotated_grid=grid, prior_memory=memory)
    plan = prepare_daily_candidate_plan(**kwargs)
    assert plan.candidates
    assert plan.audit["prior_memory_loaded"] is True
    assert plan.prior_train_trial_sharpes == (0.1, 0.2)
    assert plan.audit["seed_source_counts"]["alpha_exploration"] > 0
    assert set(plan.audit["family_coverage_missing_buckets"]) == {"score_control"}
    signatures = [candidate_parameter_signature(candidate) for candidate in plan.candidates]
    assert len(signatures) == len(set(signatures))
    assert set(signatures).isdisjoint(seen)
    # Observational validation fields must not steer the seed queue.
    memory["validation_results"] = {"best_family": "mean_reversion", "score": 999}
    memory["holdout_results"] = {"score": -999}
    assert prepare_daily_candidate_plan(**kwargs).candidates == plan.candidates


def test_alpha_neighbors_change_executed_parameters_instead_of_cloning_parent():
    for parent in generate_signal_dominant_candidates():
        result = ExperimentResult(parent, {}, ExperimentDecision.KEEP, 60.0, evaluation_phase="train")
        children = evolve_candidates([result])
        assert children
        assert all(candidate_parameter_signature(child) != candidate_parameter_signature(parent) for child in children)
        assert all(child.strategy_family == parent.strategy_family for child in children)
        assert all(child.parameters["entry_score"] == 1 and child.parameters["exit_score"] == 0 for child in children)
        assert all(2 <= child.parameters["max_holding_days"] <= 252 for child in children)


def test_exploration_is_bounded_reproducible_and_within_execution_risk_limits():
    seeds = generate_signal_dominant_candidates()
    first = generate_alpha_exploration(seeds)
    assert first == generate_alpha_exploration(seeds)
    assert 100 < len(first) < 1000
    assert len({candidate_parameter_signature(candidate) for candidate in first}) == len(first)
    for candidate in first:
        p = candidate.parameters
        assert 2 <= p["max_holding_days"] <= 252
        assert 0 < p.get("min_position_fraction", 1) <= p.get("max_position_fraction", 1) <= 1
        if p.get("atr_target_percent") is not None:
            assert 0.1 <= p["atr_target_percent"] <= 20
