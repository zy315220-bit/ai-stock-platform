from app.services.research_lab.models import ResearchCandidate, ResearchSplit
from app.services.research_lab.runner import run_research_batch


def _split():
    return ResearchSplit(
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-01",
        validation_end="2024-12-31",
        holdout_start="2025-01-01",
        holdout_end="2025-12-31",
    )


def test_runner_never_passes_holdout_to_backtest():
    calls = []

    def fake_backtest(**kwargs):
        calls.append(kwargs)
        return {
            "total_return_percent": 18.0,
            "max_drawdown_percent": 8.0,
            "total_trades": 20,
            "performance_metrics": {
                "sharpe_ratio": 1.4,
                "sortino_ratio": 2.0,
                "calmar_ratio": 1.6,
            },
        }

    candidate = ResearchCandidate("a", "score_threshold", {"entry_score": 75, "exit_score": 55})
    run_research_batch("0050", _split(), [candidate], backtest_fn=fake_backtest)

    assert calls[0]["start_date"] == "2023-01-01"
    assert calls[0]["end_date"] == "2024-12-31"
    assert "2025-01-01" not in str(calls[0])


def test_batch_ranks_stronger_candidate_first():
    def fake_backtest(**kwargs):
        strong = kwargs["entry_score"] == 80
        return {
            "total_return_percent": 22.0 if strong else 5.0,
            "max_drawdown_percent": 7.0 if strong else 18.0,
            "total_trades": 20,
            "performance_metrics": {
                "sharpe_ratio": 1.8 if strong else 0.3,
                "sortino_ratio": 2.4 if strong else 0.4,
                "calmar_ratio": 1.9 if strong else 0.3,
            },
        }

    weak = ResearchCandidate("weak", "score_threshold", {"entry_score": 70, "exit_score": 50})
    strong = ResearchCandidate("strong", "score_threshold", {"entry_score": 80, "exit_score": 55})
    results = run_research_batch("0050", _split(), [weak, strong], backtest_fn=fake_backtest)

    assert results[0].candidate.candidate_id == "strong"
    assert results[0].research_score > results[1].research_score
