from app.services.research_lab import (
    ExperimentDecision,
    ResearchCandidate,
    build_research_split,
    evaluate_candidate,
)
from app.services.research_lab.scoring import wilson_lower_bound


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


def test_wilson_win_rate_rewards_real_sample_size() -> None:
    assert wilson_lower_bound(60, 100) > wilson_lower_bound(6, 10)


def test_profit_and_conservative_win_rate_improve_research_score() -> None:
    candidate = ResearchCandidate(
        "score-quality",
        "score_threshold",
        {"entry": 70, "exit": 40},
    )
    base = {
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.7,
        "calmar_ratio": 1.1,
        "max_drawdown_percent": 10,
        "completed_trades": 40,
    }
    weak = evaluate_candidate(
        candidate,
        {**base, "winning_trades": 18, "total_return_percent": 5, "alpha_percent": 1},
    )
    strong = evaluate_candidate(
        candidate,
        {**base, "winning_trades": 26, "total_return_percent": 20, "alpha_percent": 8},
    )
    assert strong.research_score > weak.research_score
