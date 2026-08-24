from __future__ import annotations

from dataclasses import asdict
import json

import pytest

from app.services.research_lab.evolution import (
    candidate_parameter_signature,
    generate_parameter_candidates,
    mutate_survivor,
)
from app.services.research_lab.models import ResearchCandidate
from app.services.research_lab.training_memory import (
    build_training_memory,
    prepare_daily_candidate_plan,
    training_memory_summary,
)


TRAIN_WINDOW = ("2020-01-01", "2023-11-04")
TRAIN_IDENTITY = "canonical-train-v1"


def _pipeline_result(
    candidates: list[ResearchCandidate],
    *,
    run_id: str,
    fingerprint: str = "train-data-v1",
    frontier: list[ResearchCandidate] | None = None,
    validation_feedback: bool = False,
) -> dict[str, object]:
    return {
        "research_run_id": run_id,
        "skipped_duplicate_count": 0,
        "research_audit": {
            "validation_used_during_adaptive_search": validation_feedback,
            "holdout_used_during_search": False,
        },
        "rounds": [
            {
                "generation": 1,
                "evaluation_phase": "train",
                "evaluated": [
                    {
                        "candidate": asdict(candidate),
                        "validation_metrics": {
                            "data_fingerprint": fingerprint,
                            "total_return_percent": 999.0,
                            "statistical_evidence": {
                                "period_sharpe_ratio": 0.1 + index / 100,
                            },
                        },
                        "decision": "KEEP",
                        "research_score": 50.0 + index,
                        "reasons": [],
                        "evaluation_phase": "train",
                    }
                    for index, candidate in enumerate(candidates)
                ],
                "survivors": [
                    asdict(candidate) for candidate in (frontier or [])
                ],
            }
        ],
    }


def test_training_memory_continues_with_novel_train_only_candidates() -> None:
    grid = generate_parameter_candidates(
        entry_scores=(60, 70),
        exit_scores=(40,),
    )
    first_plan = prepare_daily_candidate_plan(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        rotated_grid=grid,
        prior_memory=None,
    )
    assert first_plan.audit["prior_memory_loaded"] is False
    assert first_plan.audit["memory_reset_reason"] == "missing"

    evaluated_day_one = list(first_plan.candidates[:2])
    frontier = mutate_survivor(
        evaluated_day_one[0],
        entry_delta=3,
        exit_delta=-3,
    )
    first_memory = build_training_memory(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        as_of_date="2026-08-25",
        result=_pipeline_result(
            evaluated_day_one,
            run_id="day-one",
            frontier=[frontier],
        ),
        prior_memory=None,
    )
    first_seen = set(first_memory["seen_parameter_signatures"])
    assert len(first_seen) == 2
    assert first_memory["provenance"] == "TRAIN_ONLY"
    assert first_memory["validation_feedback_used"] is False
    assert "validation_metrics" not in json.dumps(first_memory)

    second_plan = prepare_daily_candidate_plan(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        rotated_grid=grid,
        prior_memory=first_memory,
    )
    second_signatures = {
        candidate_parameter_signature(candidate)
        for candidate in second_plan.candidates
    }
    assert second_plan.audit["prior_memory_loaded"] is True
    assert second_plan.audit["memory_reset_reason"] is None
    assert second_plan.audit["seed_source_counts"]["frontier"] == 1
    assert second_signatures
    assert second_signatures.isdisjoint(first_seen)

    evaluated_day_two = list(second_plan.candidates[:2])
    second_memory = build_training_memory(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        as_of_date="2026-08-26",
        result=_pipeline_result(
            evaluated_day_two,
            run_id="day-two",
            fingerprint="strategy-specific-frame-v2",
        ),
        prior_memory=first_memory,
    )
    summary = training_memory_summary(second_memory)
    assert summary["prior_memory_continued"] is True
    assert summary["lifetime_run_count"] == 2
    assert summary["lifetime_experiment_count"] == 4
    assert summary["unique_experiment_count"] == 4
    assert summary["last_run_new_experiment_count"] == 2
    assert summary["train_trial_count"] == 4
    assert summary["train_data_identity_verified"] is True
    assert summary["validation_feedback_used"] is False
    assert summary["holdout_feedback_used"] is False


def test_training_memory_refuses_validation_feedback() -> None:
    candidate = generate_parameter_candidates()[0]
    with pytest.raises(RuntimeError, match="validation feedback"):
        build_training_memory(
            stock_code="2330",
            campaign_id="2026-Q3",
            train_window=TRAIN_WINDOW,
            train_data_identity=TRAIN_IDENTITY,
            as_of_date="2026-08-25",
            result=_pipeline_result(
                [candidate],
                run_id="unsafe",
                validation_feedback=True,
            ),
            prior_memory=None,
        )


def test_training_memory_refuses_non_train_rounds() -> None:
    candidate = generate_parameter_candidates()[0]
    result = _pipeline_result([candidate], run_id="unsafe-phase")
    result["rounds"][0]["evaluation_phase"] = "validation"
    with pytest.raises(RuntimeError, match="non-train"):
        build_training_memory(
            stock_code="2330",
            campaign_id="2026-Q3",
            train_window=TRAIN_WINDOW,
            train_data_identity=TRAIN_IDENTITY,
            as_of_date="2026-08-25",
            result=result,
            prior_memory=None,
        )


def test_campaign_or_train_data_revision_resets_adaptive_memory() -> None:
    grid = generate_parameter_candidates()
    first_memory = build_training_memory(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        as_of_date="2026-08-25",
        result=_pipeline_result([grid[0]], run_id="first"),
        prior_memory=None,
    )
    new_campaign_plan = prepare_daily_candidate_plan(
        stock_code="2330",
        campaign_id="2026-Q4",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        rotated_grid=grid,
        prior_memory=first_memory,
    )
    assert new_campaign_plan.audit["prior_memory_loaded"] is False
    assert new_campaign_plan.audit["memory_reset_reason"] == "campaign_changed"

    revised_plan = prepare_daily_candidate_plan(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity="canonical-train-v2",
        rotated_grid=grid,
        prior_memory=first_memory,
    )
    assert revised_plan.audit["prior_memory_loaded"] is False
    assert revised_plan.audit["memory_reset_reason"] == "train_data_revision"

    revised_memory = build_training_memory(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity="canonical-train-v2",
        as_of_date="2026-08-26",
        result=_pipeline_result(
            [grid[1]],
            run_id="revised",
            fingerprint="train-data-v1",
        ),
        prior_memory=first_memory,
    )
    assert revised_memory["memory_reset_reason"] == "train_data_revision"
    assert revised_memory["lifetime_run_count"] == 1
    assert revised_memory["lifetime_experiment_count"] == 1


def test_existing_memory_migrates_to_canonical_identity_without_reset() -> None:
    grid = generate_parameter_candidates()
    first_memory = build_training_memory(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        as_of_date="2026-08-25",
        result=_pipeline_result([grid[0]], run_id="first"),
        prior_memory=None,
    )
    first_memory.pop("train_data_identity")
    first_memory.pop("train_data_identity_schema")
    first_memory.pop("train_data_identity_verified")
    first_memory.pop("train_data_identity_migrated")

    plan = prepare_daily_candidate_plan(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        rotated_grid=grid,
        prior_memory=first_memory,
    )
    assert plan.audit["prior_memory_loaded"] is True
    assert plan.audit["train_data_identity_migrated"] is True

    migrated = build_training_memory(
        stock_code="2330",
        campaign_id="2026-Q3",
        train_window=TRAIN_WINDOW,
        train_data_identity=TRAIN_IDENTITY,
        as_of_date="2026-08-26",
        result=_pipeline_result([grid[1]], run_id="second"),
        prior_memory=first_memory,
    )
    assert migrated["memory_reset_reason"] is None
    assert migrated["train_data_identity_migrated"] is True
    assert migrated["train_data_identity_verified"] is False
    assert migrated["lifetime_run_count"] == 2
    assert migrated["lifetime_experiment_count"] == 2
