from __future__ import annotations

from app.services.research_lab.models import ResearchCandidate, ResearchSplit
from app.services.research_lab.walk_forward import build_validation_slices, run_walk_forward_validation


def _candidate() -> ResearchCandidate:
    return ResearchCandidate(
        candidate_id="test-candidate",
        strategy_family="score_engine",
        parameters={"entry_score": 55, "exit_score": 35, "initial_capital": 100000},
        hypothesis="test",
    )


def _split() -> ResearchSplit:
    return ResearchSplit(
        train_start="2023-01-01", train_end="2023-12-31",
        validation_start="2024-01-01", validation_end="2024-06-30",
        holdout_start="2024-07-01", holdout_end="2024-12-31",
    )


def test_validation_slices_never_cross_into_holdout() -> None:
    slices = build_validation_slices(_split(), slice_count=3)
    assert len(slices) == 3
    assert slices[0].start_date == "2024-01-01"
    assert slices[-1].end_date == "2024-06-30"
    assert all(row.end_date < _split().holdout_start for row in slices)


def test_open_positions_are_not_counted_as_completed_trades() -> None:
    calls: list[tuple[str, str]] = []

    def fake_backtest(**kwargs):
        calls.append((kwargs["start_date"], kwargs["end_date"]))
        return {
            "performance_metrics": {"sharpe_ratio": 1.2},
            "total_return_percent": 5.0,
            "max_drawdown_percent": 3.0,
            "completed_trades": 0,
            "total_trades": 0,
            "open_position_count": 1,
            "open_position": {"unrealized_return_percent": 5.0},
        }

    result = run_walk_forward_validation(
        "2330", _split(), _candidate(), backtest_fn=fake_backtest,
        slice_count=3, min_total_completed_trades=1,
    )
    assert len(calls) == 3
    assert result.aggregate["completed_trades"] == 0
    assert result.aggregate["open_position_count"] == 3
    assert result.aggregate["evidence_quality"]["sample_sufficient"] is False
    assert result.aggregate["evidence_quality"]["evidence_label"] == "MARK_TO_MARKET_ONLY"
    assert all(row["evidence_label"] == "MARK_TO_MARKET_ONLY" for row in result.slices)
    assert result.aggregate["holdout_used"] is False


def test_completed_trade_evidence_accumulates_across_slices() -> None:
    def fake_backtest(**kwargs):
        return {
            "performance_metrics": {"sharpe_ratio": 0.8},
            "total_return_percent": 1.0,
            "max_drawdown_percent": 2.0,
            "completed_trades": 1,
            "total_trades": 1,
            "open_position_count": 0,
        }

    result = run_walk_forward_validation(
        "2330", _split(), _candidate(), backtest_fn=fake_backtest,
        slice_count=3, min_total_completed_trades=3,
    )
    assert result.aggregate["completed_trades"] == 3
    assert result.aggregate["evidence_quality"]["sample_sufficient"] is True
    assert result.aggregate["evidence_quality"]["evidence_label"] == "SUFFICIENT_COMPLETED_SAMPLE"
