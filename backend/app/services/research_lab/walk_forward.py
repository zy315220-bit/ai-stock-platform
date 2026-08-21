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


def build_validation_slices(split: ResearchSplit, *, slice_count: int = 3) -> tuple[ValidationSlice, ...]:
    """Partition validation chronologically; holdout is never included."""
    if slice_count < 2:
        raise ValueError("slice_count must be at least 2")
    start = pd.Timestamp(split.validation_start).normalize()
    end = pd.Timestamp(split.validation_end).normalize()
    if start >= end:
        raise ValueError("validation range must contain multiple dates")
    boundaries = pd.date_range(start=start, end=end + pd.Timedelta(days=1), periods=slice_count + 1)
    slices: list[ValidationSlice] = []
    for index in range(slice_count):
        slice_start = boundaries[index].normalize()
        slice_end = (boundaries[index + 1] - pd.Timedelta(days=1)).normalize()
        if index == slice_count - 1:
            slice_end = end
        if slice_end < slice_start:
            continue
        slices.append(ValidationSlice(f"V{index + 1}", slice_start.strftime("%Y-%m-%d"), slice_end.strftime("%Y-%m-%d")))
    return tuple(slices)


def run_walk_forward_validation(stock_code: str, split: ResearchSplit, candidate: ResearchCandidate, *, backtest_fn: BacktestFn, slice_count: int = 3, min_total_completed_trades: int = 8) -> WalkForwardEvidence:
    """Build an auditable cross-time performance matrix from validation only.

    Each slice is independently backtested so evidence cannot be borrowed from
    holdout. Completed trades are accumulated as evidence; open positions remain
    separately marked-to-market and never count toward the trade requirement.
    """
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")

    rows: list[dict[str, Any]] = []
    completed_total = 0
    open_total = 0
    returns: list[float] = []
    sharpes: list[float] = []
    drawdowns: list[float] = []
    positive_slices = 0

    for validation_slice in build_validation_slices(split, slice_count=slice_count):
        report = backtest_fn(stock_code=stock_code, start_date=validation_slice.start_date, end_date=validation_slice.end_date, **candidate.parameters)
        metrics = _validation_metrics(report)
        completed = int(metrics.get("completed_trades", 0))
        open_positions = int(metrics.get("open_position_count", 0))
        total_return = float(metrics.get("total_return_percent", 0.0))
        sharpe = float(metrics.get("sharpe_ratio", 0.0) or 0.0)
        max_dd = abs(float(metrics.get("max_drawdown_percent", 0.0) or 0.0))
        slice_evidence = assess_validation_evidence(
            {"completed_trades": completed, "open_position_count": open_positions},
            min_trades=min_total_completed_trades,
        )
        completed_total += completed
        open_total += open_positions
        returns.append(total_return)
        sharpes.append(sharpe)
        drawdowns.append(max_dd)
        if total_return > 0:
            positive_slices += 1
        rows.append({
            **asdict(validation_slice),
            "total_return_percent": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown_percent": max_dd,
            "completed_trades": completed,
            "open_position_count": open_positions,
            "evidence_quality": asdict(slice_evidence),
            "evidence_label": slice_evidence.evidence_label,
        })

    evidence = assess_validation_evidence({"completed_trades": completed_total, "open_position_count": open_total}, min_trades=min_total_completed_trades)
    n = max(1, len(rows))
    aggregate = {
        "slice_count": len(rows),
        "positive_slice_count": positive_slices,
        "positive_slice_ratio": round(positive_slices / n, 4),
        "mean_return_percent": round(sum(returns) / n, 4),
        "mean_sharpe_ratio": round(sum(sharpes) / n, 4),
        "worst_slice_drawdown_percent": round(max(drawdowns, default=0.0), 4),
        "completed_trades": completed_total,
        "open_position_count": open_total,
        "evidence_quality": asdict(evidence),
        "holdout_used": False,
    }
    return WalkForwardEvidence(candidate_id=candidate.candidate_id, slices=tuple(rows), aggregate=aggregate)
