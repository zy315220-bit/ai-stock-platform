"""Autonomous strategy research primitives.

Research candidates live outside the production competition. A candidate may
only be promoted after validation and untouched holdout checks pass.
"""

from .models import ExperimentDecision, ExperimentResult, ResearchCandidate, ResearchSplit
from .scoring import evaluate_candidate
from .splits import build_research_split

__all__ = [
    "ExperimentDecision",
    "ExperimentResult",
    "ResearchCandidate",
    "ResearchSplit",
    "build_research_split",
    "evaluate_candidate",
]
