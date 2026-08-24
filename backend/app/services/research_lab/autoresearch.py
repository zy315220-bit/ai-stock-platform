from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .evolution import EvolutionRound, evolve_candidates
from .models import ExperimentDecision, ExperimentResult, ResearchCandidate, ResearchSplit
from .runner import BacktestFn, run_research_batch


@dataclass(frozen=True)
class ResearchSession:
    stock_code: str
    rounds: tuple[EvolutionRound, ...]
    best_result: ExperimentResult | None
    experiments_run: int
    stopped_reason: str


def run_autoresearch(
    stock_code: str,
    split: ResearchSplit,
    initial_candidates: Iterable[ResearchCandidate],
    *,
    backtest_fn: BacktestFn,
    max_generations: int = 5,
    max_experiments: int = 100,
    top_k: int = 3,
    target_score: float = 75.0,
    min_validation_trades: int = 8,
) -> ResearchSession:
    """Bounded train-only keep/discard/evolve loop with a compute budget.

    The experiment budget is shared fairly across remaining generations instead
    of allowing generation 1 to consume everything. Validation and holdout are
    deliberately absent from adaptive search. Validation is a separate finalist
    gate and holdout is handled only by the one-shot promotion gate.
    """
    candidates = list(initial_candidates)
    rounds: list[EvolutionRound] = []
    best: ExperimentResult | None = None
    experiments = 0
    stopped_reason = "no_candidates"

    for generation in range(1, max_generations + 1):
        remaining = max_experiments - experiments
        if remaining <= 0:
            stopped_reason = "experiment_budget_reached"
            break

        generations_left = max_generations - generation + 1
        # Reserve a fair share for every generation still allowed to run. This
        # guarantees that, when survivors exist, later generations can actually
        # be evaluated rather than merely generated at the end of the budget.
        generation_budget = max(1, remaining // generations_left)
        batch = candidates[:generation_budget]
        if not batch:
            stopped_reason = "no_surviving_candidates"
            break

        evaluated = tuple(
            run_research_batch(
                stock_code,
                split,
                batch,
                backtest_fn=backtest_fn,
                min_validation_trades=min_validation_trades,
                evaluation_phase="train",
            )
        )
        experiments += len(evaluated)
        if evaluated and (best is None or evaluated[0].research_score > best.research_score):
            best = evaluated[0]

        children = tuple(evolve_candidates(evaluated, top_k=top_k))
        rounds.append(EvolutionRound(generation=generation, evaluated=evaluated, survivors=children))

        if best and best.decision is ExperimentDecision.HOLDOUT_READY and best.research_score >= target_score:
            stopped_reason = "target_validation_score_reached"
            break
        if experiments >= max_experiments:
            stopped_reason = "experiment_budget_reached"
            break
        if not children:
            stopped_reason = "no_surviving_candidates"
            break
        candidates = list(children)
    else:
        stopped_reason = "generation_budget_reached"

    return ResearchSession(stock_code=stock_code, rounds=tuple(rounds), best_result=best, experiments_run=experiments, stopped_reason=stopped_reason)
