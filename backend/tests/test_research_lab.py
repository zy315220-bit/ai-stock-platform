from app.services.research_lab import (
    ExperimentDecision,
    ResearchCandidate,
    build_research_split,
    evaluate_candidate,
)


def test_split_leaves_final_holdout():
    split = build_research_split("2020-01-01", "2025-12-31")
    assert split.train_end < split.validation_start
    assert split.validation_end < split.holdout_start
    assert split.holdout_end == "2025-12-31"


def test_weak_candidate_is_discarded():
    candidate = ResearchCandidate("c1", "score_threshold", {"entry": 75, "exit": 55})
    result = evaluate_candidate(candidate, {
        "sharpe_ratio": -0.2,
        "sortino_ratio": -0.1,
        "calmar_ratio": -0.1,
        "total_return_percent": -5,
        "max_drawdown_percent": 12,
        "total_trades": 20,
    })
    assert result.decision is ExperimentDecision.DISCARD


def test_strong_candidate_can_reach_holdout_gate():
    candidate = ResearchCandidate("c2", "score_threshold", {"entry": 78, "exit": 52})
    result = evaluate_candidate(candidate, {
        "sharpe_ratio": 1.6,
        "sortino_ratio": 2.2,
        "calmar_ratio": 1.5,
        "total_return_percent": 24,
        "max_drawdown_percent": 9,
        "total_trades": 30,
    })
    assert result.decision is ExperimentDecision.HOLDOUT_READY
