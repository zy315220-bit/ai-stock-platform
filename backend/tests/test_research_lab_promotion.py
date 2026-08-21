from app.services.research_lab.models import (
    ExperimentDecision,
    ExperimentResult,
    ResearchCandidate,
    ResearchSplit,
)
from app.services.research_lab.promotion import run_holdout_gate


def _split():
    return ResearchSplit(
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-01",
        validation_end="2024-12-31",
        holdout_start="2025-01-01",
        holdout_end="2025-12-31",
    )


def _qualified():
    candidate = ResearchCandidate("ema-1", "score_threshold", {"entry_score": 70, "exit_score": 40})
    return ExperimentResult(candidate, {}, ExperimentDecision.HOLDOUT_READY, 60.0)


def test_holdout_gate_uses_only_holdout_dates():
    calls = []

    def fake_backtest(**kwargs):
        calls.append(kwargs)
        return {
            "performance_metrics": {"sharpe_ratio": 1.8, "sortino_ratio": 2.5, "calmar_ratio": 1.6},
            "total_return_percent": 20,
            "max_drawdown_percent": 10,
            "total_trades": 20,
        }

    result = run_holdout_gate("2330", _split(), _qualified(), backtest_fn=fake_backtest)
    assert result.promoted is True
    assert len(calls) == 1
    assert calls[0]["start_date"] == "2025-01-01"
    assert calls[0]["end_date"] == "2025-12-31"


def test_unqualified_candidate_cannot_touch_holdout():
    called = False

    def fake_backtest(**kwargs):
        nonlocal called
        called = True
        return {}

    weak = ExperimentResult(_qualified().candidate, {}, ExperimentDecision.KEEP, 30.0)
    try:
        run_holdout_gate("2330", _split(), weak, backtest_fn=fake_backtest)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    assert called is False


def test_holdout_degradation_blocks_promotion():
    def fake_backtest(**kwargs):
        return {
            "performance_metrics": {"sharpe_ratio": 0.3, "sortino_ratio": 0.5, "calmar_ratio": 0.3},
            "total_return_percent": 3,
            "max_drawdown_percent": 20,
            "total_trades": 20,
        }

    result = run_holdout_gate("2330", _split(), _qualified(), backtest_fn=fake_backtest)
    assert result.promoted is False
    assert result.reasons
