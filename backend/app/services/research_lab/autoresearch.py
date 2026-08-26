from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .evolution import (
    EvolutionRound,
    candidate_parameter_signature,
    evolve_candidates,
)
from .models import ExperimentResult, ResearchCandidate, ResearchSplit
from .runner import BacktestFn, run_research_batch
from .train_selection import select_train_multiobjective, train_target_reached


@dataclass(frozen=True)
class ResearchSession:
    stock_code: str
    rounds: tuple[EvolutionRound, ...]
    best_result: ExperimentResult | None
    experiments_run: int
    stopped_reason: str
    evaluated_parameter_signatures: tuple[str, ...] = ()
    skipped_duplicate_count: int = 0


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
    excluded_parameter_signatures: Iterable[str] = (),
) -> ResearchSession:
    """Bounded Train-only keep/discard/evolve loop with a compute budget.

    Adaptive search never reads Validation or Final Holdout evidence. Rather
    than letting one scalar score monopolize every parent slot, each generation
    now preserves a small deterministic frontier spanning score, persistent
    active return, dependence-adjusted active evidence, and strategy-family
    diversity. This is a search policy only; independent promotion gates remain
    unchanged.
    """
    candidates = list(initial_candidates)
    rounds: list[EvolutionRound] = []
    best: ExperimentResult | None = None
    experiments = 0
    stopped_reason = "no_candidates"
    seen_signatures = {
        str(signature) for signature in excluded_parameter_signatures
    }
    evaluated_signatures: list[str] = []
    skipped_duplicates = 0

    for generation in range(1, max_generations + 1):
        remaining = max_experiments - experiments
        if remaining <= 0:
            stopped_reason = "experiment_budget_reached"
            break

        generations_left = max_generations - generation + 1
        generation_budget = max(1, remaining // generations_left)
        batch: list[ResearchCandidate] = []
        for candidate in candidates:
            signature = candidate_parameter_signature(candidate)
            if signature in seen_signatures:
                skipped_duplicates += 1
                continue
            seen_signatures.add(signature)
            evaluated_signatures.append(signature)
            batch.append(candidate)
            if len(batch) >= generation_budget:
                break
        if not batch:
            stopped_reason = (
                "no_novel_candidates"
                if candidates
                else "no_surviving_candidates"
            )
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
        if evaluated and (
            best is None
            or evaluated[0].research_score > best.research_score
        ):
            best = evaluated[0]

        parent_results = select_train_multiobjective(
            evaluated,
            limit=max(1, top_k),
        )
        children = tuple(
            evolve_candidates(
                parent_results,
                top_k=len(parent_results),
                preserve_input_order=True,
            )
        )
        rounds.append(
            EvolutionRound(
                generation=generation,
                evaluated=evaluated,
                survivors=children,
            )
        )

        if train_target_reached(best, target_score=target_score):
            stopped_reason = "train_active_target_reached"
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

    return ResearchSession(
        stock_code=stock_code,
        rounds=tuple(rounds),
        best_result=best,
        experiments_run=experiments,
        stopped_reason=stopped_reason,
        evaluated_parameter_signatures=tuple(evaluated_signatures),
        skipped_duplicate_count=skipped_duplicates,
    )
