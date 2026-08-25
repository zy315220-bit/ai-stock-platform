from __future__ import annotations

from app.services.research_lab.models import ResearchCandidate, ResearchSplit
from app.services.research_lab.walk_forward import (
    build_validation_slices,
    run_walk_forward_validation,
)


def _candidate() -> ResearchCandidate:
    return ResearchCandidate(
        candidate_id="test-candidate",
        strategy_family="score_engine",
        parameters={
            "entry_score": 55,
            "exit_score": 35,
            "initial_capital": 100000,
        },
        hypothesis="test",
    )


def _split() -> ResearchSplit:
    return ResearchSplit(
        train_start="2023-01-01",
        train_end="2023-12-31",
        validation_start="2024-01-01",
        validation_end="2024-06-30",
        holdout_start="2024-07-01",
        holdout_end="2024-12-31",
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
        "2330",
        _split(),
        _candidate(),
        backtest_fn=fake_backtest,
        slice_count=3,
        min_total_completed_trades=1,
    )
    assert len(calls) == 4
    assert calls[-1] == (
        _split().validation_start,
        _split().validation_end,
    )
    assert result.aggregate["completed_trades"] == 0
    assert result.aggregate["open_position_count"] == 1
    assert result.aggregate["independent_slice_open_position_count"] == 3
    assert result.aggregate["evidence_quality"]["sample_sufficient"] is False
    assert result.aggregate["evidence_quality"]["evidence_label"] == (
        "MARK_TO_MARKET_ONLY"
    )
    assert all(
        row["evidence_label"] == "MARK_TO_MARKET_ONLY"
        for row in result.slices
    )
    assert result.aggregate["holdout_used"] is False


def test_completed_trade_evidence_uses_continuous_validation_sample() -> None:
    def fake_backtest(**kwargs):
        is_full_validation = (
            kwargs["start_date"] == _split().validation_start
            and kwargs["end_date"] == _split().validation_end
        )
        completed = 4 if is_full_validation else 1
        return {
            "performance_metrics": {"sharpe_ratio": 0.8},
            "total_return_percent": 1.0,
            "max_drawdown_percent": 2.0,
            "completed_trades": completed,
            "total_trades": completed,
            "open_position_count": 0,
        }

    result = run_walk_forward_validation(
        "2330",
        _split(),
        _candidate(),
        backtest_fn=fake_backtest,
        slice_count=3,
        min_total_completed_trades=4,
    )
    assert result.aggregate["independent_slice_completed_trades"] == 3
    assert result.aggregate["completed_trades"] == 4
    assert result.aggregate["boundary_recovered_completed_trades"] == 1
    assert result.aggregate["continuous_validation_used_for_sample_gate"] is True
    assert result.aggregate["sample_gate_policy"] == (
        "continuous_validation_completed_trades_only"
    )
    assert result.aggregate["evidence_quality"]["sample_sufficient"] is True
    assert result.aggregate["evidence_quality"]["evidence_label"] == (
        "SUFFICIENT_COMPLETED_SAMPLE"
    )
