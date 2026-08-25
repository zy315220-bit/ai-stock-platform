from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from .evidence import assess_validation_evidence
from .models import ResearchCandidate, ResearchSplit
from .runner import BacktestFn, _ALLOWED_PARAMETERS, _validation_metrics


@dataclass(frozen=True)
class ValidationSlice:
    slice_id: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class WalkForwardEvidence:
    candidate_id: str
    slices: tuple[dict[str, Any], ...]
    aggregate: dict[str, Any]


def build_validation_slices(
    split: ResearchSplit,
    *,
    slice_count: int = 3,
) -> tuple[ValidationSlice, ...]:
    """Partition validation chronologically; holdout is never included."""
    if slice_count < 2:
        raise ValueError("slice_count must be at least 2")
    start = pd.Timestamp(split.validation_start).normalize()
    end = pd.Timestamp(split.validation_end).normalize()
    if start >= end:
        raise ValueError("validation range must contain multiple dates")
    boundaries = pd.date_range(
        start=start,
        end=end + pd.Timedelta(days=1),
        periods=slice_count + 1,
    )
    slices: list[ValidationSlice] = []
    for index in range(slice_count):
        slice_start = boundaries[index].normalize()
        slice_end = (
            boundaries[index + 1] - pd.Timedelta(days=1)
        ).normalize()
        if index == slice_count - 1:
            slice_end = end
        if slice_end < slice_start:
            continue
        slices.append(
            ValidationSlice(
                f"V{index + 1}",
                slice_start.strftime("%Y-%m-%d"),
                slice_end.strftime("%Y-%m-%d"),
            )
        )
    return tuple(slices)


def run_walk_forward_validation(
    stock_code: str,
    split: ResearchSplit,
    candidate: ResearchCandidate,
    *,
    backtest_fn: BacktestFn,
    slice_count: int = 3,
    min_total_completed_trades: int = 8,
) -> WalkForwardEvidence:
    """Build an auditable cross-time performance matrix from validation only.

    Chronological slices remain independently backtested to expose time-local
    stability. The sample-size gate, however, uses one continuous validation
    backtest so a trade opened near a slice boundary and closed in the next
    slice is not accidentally discarded. This removes a boundary artifact
    without lowering the completed-trade requirement or touching holdout data.
    """
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")

    rows: list[dict[str, Any]] = []
    independent_completed_total = 0
    independent_open_total = 0
    returns: list[float] = []
    sharpes: list[float] = []
    drawdowns: list[float] = []
    positive_slices = 0

    validation_slices = build_validation_slices(
        split,
        slice_count=slice_count,
    )
    for validation_slice in validation_slices:
        report = backtest_fn(
            stock_code=stock_code,
            start_date=validation_slice.start_date,
            end_date=validation_slice.end_date,
            liquidate_at_end=False,
            **candidate.parameters,
        )
        metrics = _validation_metrics(report)
        completed = int(metrics.get("completed_trades", 0))
        open_positions = int(metrics.get("open_position_count", 0))
        total_return = float(metrics.get("total_return_percent", 0.0))
        sharpe = float(metrics.get("sharpe_ratio", 0.0) or 0.0)
        max_dd = abs(
            float(metrics.get("max_drawdown_percent", 0.0) or 0.0)
        )
        win_rate = float(metrics.get("win_rate_percent", 0.0) or 0.0)
        alpha = float(metrics.get("alpha_percent", 0.0) or 0.0)
        slice_evidence = assess_validation_evidence(
            {
                "completed_trades": completed,
                "open_position_count": open_positions,
            },
            min_trades=min_total_completed_trades,
        )
        independent_completed_total += completed
        independent_open_total += open_positions
        returns.append(total_return)
        sharpes.append(sharpe)
        drawdowns.append(max_dd)
        if total_return > 0:
            positive_slices += 1
        rows.append(
            {
                **asdict(validation_slice),
                "total_return_percent": total_return,
                "sharpe_ratio": sharpe,
                "max_drawdown_percent": max_dd,
                "win_rate_percent": win_rate,
                "alpha_percent": alpha,
                "completed_trades": completed,
                "open_position_count": open_positions,
                "evidence_quality": asdict(slice_evidence),
                "evidence_label": slice_evidence.evidence_label,
            }
        )

    continuous_report = backtest_fn(
        stock_code=stock_code,
        start_date=split.validation_start,
        end_date=split.validation_end,
        liquidate_at_end=False,
        **candidate.parameters,
    )
    continuous_metrics = _validation_metrics(continuous_report)
    continuous_completed = int(
        continuous_metrics.get("completed_trades", 0)
    )
    continuous_open = int(
        continuous_metrics.get("open_position_count", 0)
    )
    evidence = assess_validation_evidence(
        {
            "completed_trades": continuous_completed,
            "open_position_count": continuous_open,
        },
        min_trades=min_total_completed_trades,
    )

    n = max(1, len(rows))
    aggregate = {
        "slice_count": len(rows),
        "positive_slice_count": positive_slices,
        "positive_slice_ratio": round(positive_slices / n, 4),
        "mean_return_percent": round(sum(returns) / n, 4),
        "mean_sharpe_ratio": round(sum(sharpes) / n, 4),
        "worst_slice_drawdown_percent": round(
            max(drawdowns, default=0.0),
            4,
        ),
        "completed_trades": continuous_completed,
        "open_position_count": continuous_open,
        "independent_slice_completed_trades": independent_completed_total,
        "independent_slice_open_position_count": independent_open_total,
        "boundary_recovered_completed_trades": max(
            0,
            continuous_completed - independent_completed_total,
        ),
        "continuous_validation_used_for_sample_gate": True,
        "sample_gate_policy": "continuous_validation_completed_trades_only",
        "evidence_quality": asdict(evidence),
        "holdout_used": False,
    }
    return WalkForwardEvidence(
        candidate_id=candidate.candidate_id,
        slices=tuple(rows),
        aggregate=aggregate,
    )
