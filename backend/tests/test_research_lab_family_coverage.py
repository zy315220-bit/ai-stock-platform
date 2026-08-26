from __future__ import annotations

from app.services.research_lab.evolution import (
    candidate_parameter_signature,
    generate_parameter_candidates,
)
from app.services.research_lab.training_memory import (
    FAMILY_COVERAGE_BUCKETS,
    _family_coverage_bucket,
    prepare_daily_candidate_plan,
)


TRAIN_WINDOW = ("2020-01-01", "2023-11-04")
TRAIN_IDENTITY = "canonical-train-v1"


def _plan(grid, prior_memory=None):
    return prepare_daily_candidate_plan(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        rotated_grid=grid,
        prior_memory=prior_memory,
    )


def test_daily_first_generation_reserves_cross_family_coverage() -> None:
    grid = generate_parameter_candidates()
    # Deliberately bury every alpha family behind the legacy score candidates.
    # The coverage prefix must still pull representative families forward.
    score_first = sorted(
        grid,
        key=lambda candidate: candidate.strategy_family.startswith("alpha_"),
    )

    plan = _plan(score_first)
    first_generation_budget = list(plan.candidates[:8])
    first_buckets = {
        _family_coverage_bucket(candidate)
        for candidate in first_generation_budget
    }

    assert set(FAMILY_COVERAGE_BUCKETS) <= first_buckets
    assert plan.audit["family_coverage_enabled"] is True
    assert plan.audit["family_coverage_prefix_count"] == len(
        FAMILY_COVERAGE_BUCKETS
    )
    assert plan.audit["family_coverage_missing_buckets"] == []
    assert [
        item["bucket"] for item in plan.audit["family_coverage_prefix"]
    ] == list(FAMILY_COVERAGE_BUCKETS)
    assert plan.audit["validation_feedback_used"] is False
    assert plan.audit["holdout_feedback_used"] is False


def test_family_coverage_prefix_is_deterministic_and_unique() -> None:
    grid = generate_parameter_candidates()
    first = _plan(grid)
    second = _plan(grid)

    first_ids = [candidate.candidate_id for candidate in first.candidates[:8]]
    second_ids = [candidate.candidate_id for candidate in second.candidates[:8]]
    assert first_ids == second_ids

    signatures = [
        candidate_parameter_signature(candidate)
        for candidate in first.candidates
    ]
    assert len(signatures) == len(set(signatures))


def test_seen_family_seed_is_not_repeated_and_missing_bucket_is_audited() -> None:
    grid = generate_parameter_candidates()
    pure_mean_reversion = next(
        candidate
        for candidate in grid
        if _family_coverage_bucket(candidate) == "mean_reversion"
    )
    seen_signature = candidate_parameter_signature(pure_mean_reversion)
    prior_memory = {
        "schema_version": 1,
        "search_space_schema": "alpha-family-diversity-v5",
        "provenance": "TRAIN_ONLY",
        "stock_code": "2330",
        "campaign_id": "2026-Q3",
        "train_window": list(TRAIN_WINDOW),
        "train_data_identity_schema": "canonical-train-score-series-v1",
        "train_data_identity": TRAIN_IDENTITY,
        "validation_feedback_used": False,
        "holdout_feedback_used": False,
        "seen_parameter_signatures": [seen_signature],
        "frontier": [],
        "elites": [],
        "train_trial_period_sharpes": [],
    }

    plan = _plan(grid, prior_memory=prior_memory)
    planned_signatures = {
        candidate_parameter_signature(candidate)
        for candidate in plan.candidates
    }

    assert seen_signature not in planned_signatures
    assert "mean_reversion" in plan.audit["family_coverage_missing_buckets"]
    assert plan.audit["prior_memory_loaded"] is True
    assert plan.audit["validation_feedback_used"] is False
    assert plan.audit["holdout_feedback_used"] is False
