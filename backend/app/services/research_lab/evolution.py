from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable
from uuid import uuid4

from .models import ExperimentDecision, ExperimentResult, ResearchCandidate, ResearchSplit
from .runner import BacktestFn, run_research_batch


@dataclass(frozen=True)
class EvolutionRound:
    generation: int
    evaluated: tuple[ExperimentResult, ...]
    survivors: tuple[ResearchCandidate, ...]


def generate_parameter_candidates(*, entry_scores: Iterable[int] = (55, 60, 65, 70), exit_scores: Iterable[int] = (35, 40, 45, 50), initial_capital: float = 1_000_000.0, strategy_family: str = "score_engine") -> list[ResearchCandidate]:
    candidates: list[ResearchCandidate] = []
    for entry_score, exit_score in product(entry_scores, exit_scores):
        if exit_score >= entry_score: continue
        candidates.append(ResearchCandidate(candidate_id=f"grid-{entry_score}-{exit_score}", strategy_family=strategy_family, parameters={"entry_score": entry_score, "exit_score": exit_score, "initial_capital": initial_capital}, hypothesis="Systematic score-threshold search"))
    return candidates


def mutate_survivor(parent: ResearchCandidate, *, entry_delta: int, exit_delta: int, hypothesis_suffix: str = "local") -> ResearchCandidate:
    params = dict(parent.parameters)
    params["entry_score"] = max(1, min(99, int(params["entry_score"]) + entry_delta))
    params["exit_score"] = max(0, min(98, int(params["exit_score"]) + exit_delta))
    if params["exit_score"] >= params["entry_score"]: params["exit_score"] = params["entry_score"] - 1
    return ResearchCandidate(candidate_id=f"mut-{uuid4().hex[:12]}", strategy_family=parent.strategy_family, parameters=params, parent_id=parent.candidate_id, hypothesis=f"Adaptive {hypothesis_suffix} mutation of {parent.candidate_id}: entry {entry_delta:+d}, exit {exit_delta:+d}")


def _mutation_neighborhood(result: ExperimentResult) -> tuple[tuple[int, int, str], ...]:
    """Choose exploration radius from validation evidence, without holdout access."""
    score = result.research_score
    decision = result.decision
    if decision is ExperimentDecision.HOLDOUT_READY or score >= 60:
        # Strong candidates: exploit nearby values with fine steps.
        return ((-2, 0, "fine"), (2, 0, "fine"), (0, -2, "fine"), (0, 2, "fine"), (-2, -2, "fine"), (2, 2, "fine"))
    if score >= 25:
        # Promising but uncertain: normal local search plus two diagonals.
        return ((-5, 0, "local"), (5, 0, "local"), (0, -5, "local"), (0, 5, "local"), (-5, -5, "local"), (5, 5, "local"))
    # Weak-but-not-discarded candidates need broader exploration to escape a poor basin.
    return ((-10, 0, "broad"), (10, 0, "broad"), (0, -10, "broad"), (0, 10, "broad"))


def evolve_candidates(results: Iterable[ExperimentResult], *, top_k: int = 3) -> list[ResearchCandidate]:
    """Rank survivors and adapt mutation radius to validation quality."""
    ranked = sorted((r for r in results if r.decision is not ExperimentDecision.DISCARD), key=lambda r: r.research_score, reverse=True)[:top_k]
    children: list[ResearchCandidate] = []
    seen: set[tuple[int, int]] = set()
    for result in ranked:
        parent = result.candidate
        for entry_delta, exit_delta, label in _mutation_neighborhood(result):
            child = mutate_survivor(parent, entry_delta=entry_delta, exit_delta=exit_delta, hypothesis_suffix=label)
            key = (int(child.parameters["entry_score"]), int(child.parameters["exit_score"]))
            if key not in seen:
                seen.add(key); children.append(child)
    return children


def run_evolution_round(stock_code: str, split: ResearchSplit, candidates: Iterable[ResearchCandidate], *, generation: int, backtest_fn: BacktestFn, top_k: int = 3) -> EvolutionRound:
    evaluated = tuple(run_research_batch(stock_code, split, candidates, backtest_fn=backtest_fn))
    survivors = tuple(evolve_candidates(evaluated, top_k=top_k))
    return EvolutionRound(generation=generation, evaluated=evaluated, survivors=survivors)
