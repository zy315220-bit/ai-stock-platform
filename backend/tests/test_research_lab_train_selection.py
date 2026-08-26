from __future__ import annotations

from app.services.research_lab.models import (
    ExperimentDecision,
    ExperimentResult,
    ResearchCandidate,
)
from app.services.research_lab.train_selection import (
    select_train_multiobjective,
    train_target_reached,
)


def _result(
    candidate_id: str,
    *,
    score: float,
    active_t: float,
    annualized_alpha: float,
    positive_ratio: float,
    worst_ir: float,
    family: str = "score_engine",
    phase: str = "train",
    decision: ExperimentDecision = ExperimentDecision.KEEP,
) -> ExperimentResult:
    candidate = ResearchCandidate(
        candidate_id,
        family,
        {
            "entry_score": 60,
            "exit_score": 40,
            "initial_capital": 1_000_000.0,
        },
    )
    return ExperimentResult(
        candidate=candidate,
        validation_metrics={
            "train_active_robustness_proxy": {
                "available": True,
                "dependence_adjusted_active_t_statistic": active_t,
                "annualized_mean_excess_percent": annualized_alpha,
                "positive_slice_ratio": positive_ratio,
                "overall_information_ratio": active_t / 2.0,
                "median_slice_information_ratio": active_t / 3.0,
                "worst_slice_information_ratio": worst_ir,
            }
        },
        decision=decision,
        research_score=score,
        evaluation_phase=phase,
    )


def test_multiobjective_frontier_keeps_active_evidence_not_only_top_score() -> None:
    scalar_winner = _result(
        "scalar",
        score=90.0,
        active_t=0.1,
        annualized_alpha=0.2,
        positive_ratio=0.5,
        worst_ir=-1.0,
    )
    active_winner = _result(
        "active",
        score=72.0,
        active_t=3.0,
        annualized_alpha=18.0,
        positive_ratio=1.0,
        worst_ir=0.4,
        family="score_engine_volume_confirmed",
    )
    persistent = _result(
        "persistent",
        score=70.0,
        active_t=1.7,
        annualized_alpha=12.0,
        positive_ratio=1.0,
        worst_ir=0.8,
        family="score_engine_bollinger_breakout",
    )

    selected = select_train_multiobjective(
        [scalar_winner, active_winner, persistent],
        limit=3,
    )
    identities = [result.candidate.candidate_id for result in selected]

    assert identities[0] == "scalar"
    assert "active" in identities
    assert "persistent" in identities


def test_multiobjective_frontier_never_uses_validation_results() -> None:
    train = _result(
        "train",
        score=50.0,
        active_t=1.0,
        annualized_alpha=5.0,
        positive_ratio=0.8,
        worst_ir=0.0,
    )
    validation = _result(
        "validation",
        score=999.0,
        active_t=99.0,
        annualized_alpha=999.0,
        positive_ratio=1.0,
        worst_ir=9.0,
        phase="validation",
    )

    selected = select_train_multiobjective([validation, train], limit=2)

    assert [item.candidate.candidate_id for item in selected] == ["train"]


def test_train_target_does_not_stop_on_high_scalar_score_alone() -> None:
    weak_active = _result(
        "weak-active",
        score=95.0,
        active_t=0.2,
        annualized_alpha=-1.0,
        positive_ratio=0.5,
        worst_ir=-1.0,
        decision=ExperimentDecision.HOLDOUT_READY,
    )
    robust_active = _result(
        "robust-active",
        score=80.0,
        active_t=2.2,
        annualized_alpha=10.0,
        positive_ratio=1.0,
        worst_ir=0.1,
        decision=ExperimentDecision.HOLDOUT_READY,
    )

    assert train_target_reached(weak_active, target_score=75.0) is False
    assert train_target_reached(robust_active, target_score=75.0) is True
