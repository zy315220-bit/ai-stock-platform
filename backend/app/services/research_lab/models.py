from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExperimentDecision(str, Enum):
    KEEP = "KEEP"
    DISCARD = "DISCARD"
    HOLDOUT_READY = "HOLDOUT_READY"


@dataclass(frozen=True)
class ResearchSplit:
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    holdout_start: str
    holdout_end: str


@dataclass(frozen=True)
class ResearchCandidate:
    candidate_id: str
    strategy_family: str
    parameters: dict[str, Any]
    parent_id: str | None = None
    hypothesis: str = ""


@dataclass(frozen=True)
class ExperimentResult:
    candidate: ResearchCandidate
    validation_metrics: dict[str, Any]
    decision: ExperimentDecision
    research_score: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    evaluation_phase: str = "validation"
