from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceQuality:
    completed_trades: int
    open_positions: int
    minimum_required_trades: int
    trade_sample_ratio: float
    sample_sufficient: bool
    mark_to_market_only: bool
    evidence_label: str


def assess_validation_evidence(metrics: dict[str, Any], *, min_trades: int) -> EvidenceQuality:
    """Describe evidence quality without relaxing the completed-trade gate."""
    try:
        completed = max(0, int(metrics.get("completed_trades", metrics.get("total_trades", 0))))
    except (TypeError, ValueError):
        completed = 0
    try:
        open_positions = max(0, int(metrics.get("open_position_count", 0)))
    except (TypeError, ValueError):
        open_positions = 0

    required = max(1, int(min_trades))
    ratio = min(completed / required, 1.0)
    sufficient = completed >= required
    mark_only = completed == 0 and open_positions > 0

    if sufficient:
        label = "SUFFICIENT_COMPLETED_SAMPLE"
    elif mark_only:
        label = "MARK_TO_MARKET_ONLY"
    elif completed > 0:
        label = "PARTIAL_COMPLETED_SAMPLE"
    else:
        label = "NO_TRADE_EVIDENCE"

    return EvidenceQuality(
        completed_trades=completed,
        open_positions=open_positions,
        minimum_required_trades=required,
        trade_sample_ratio=round(ratio, 4),
        sample_sufficient=sufficient,
        mark_to_market_only=mark_only,
        evidence_label=label,
    )
