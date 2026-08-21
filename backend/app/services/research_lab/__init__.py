"""Autonomous strategy research primitives.

Research candidates live outside the production competition. A candidate may
only be promoted after validation and untouched holdout checks pass.
"""

from .models import ExperimentDecision, ExperimentResult, ResearchCandidate, ResearchSplit
from .promotion import PromotionResult, run_holdout_gate
from .runner import run_candidate_validation, run_research_batch, serialize_result
from .scoring import evaluate_candidate
from .splits import build_research_split

__all__ = [
    "ExperimentDecision",
    "ExperimentResult",
    "PromotionResult",
    "ResearchCandidate",
    "ResearchSplit",
    "build_research_split",
    "evaluate_candidate",
    "run_candidate_validation",
    "run_holdout_gate",
    "run_research_batch",
    "serialize_result",
]
