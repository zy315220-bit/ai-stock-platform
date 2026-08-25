from app.services.research_lab.evolution import evolve_candidates
from app.services.research_lab.models import (
    ExperimentDecision,
    ExperimentResult,
    ResearchCandidate,
)


def _result(*, exit_mode: str, max_holding_days: int) -> ExperimentResult:
    candidate = ResearchCandidate(
        candidate_id="parent",
        strategy_family="score_engine",
        parameters={
            "entry_score": 55,
            "exit_score": 40,
            "initial_capital": 1_000_000.0,
            "require_ema_trend": False,
            "ema_fast_column": "EMA20",
            "ema_slow_column": "EMA60",
            "entry_mode": "score",
            "exit_mode": exit_mode,
            "max_holding_days": max_holding_days,
        },
    )
    return ExperimentResult(
        candidate=candidate,
        validation_metrics={},
        decision=ExperimentDecision.HOLDOUT_READY,
        research_score=70.0,
        evaluation_phase="train",
    )


def test_time_exit_survivor_explores_shorter_duration_hypotheses() -> None:
    children = evolve_candidates(
        [_result(exit_mode="score_or_time", max_holding_days=40)],
        top_k=1,
    )

    durations = {
        int(child.parameters["max_holding_days"])
        for child in children
        if child.parameters.get("exit_mode") == "score_or_time"
        and int(child.parameters.get("entry_score", 0)) == 55
        and int(child.parameters.get("exit_score", 0)) == 40
    }

    assert {20, 30, 40}.issubset(durations)
    assert any(
        "duration" in child.hypothesis and "max_hold=20 sessions" in child.hypothesis
        for child in children
    )


def test_non_time_exit_does_not_invent_duration_mutations() -> None:
    children = evolve_candidates(
        [_result(exit_mode="score", max_holding_days=60)],
        top_k=1,
    )

    duration_children = [
        child for child in children if "Adaptive duration mutation" in child.hypothesis
    ]

    assert duration_children == []
