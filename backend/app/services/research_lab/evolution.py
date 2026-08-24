from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import product
import json
from typing import Iterable

from .models import ExperimentDecision, ExperimentResult, ResearchCandidate, ResearchSplit
from .runner import BacktestFn, run_research_batch


@dataclass(frozen=True)
class EvolutionRound:
    generation: int
    evaluated: tuple[ExperimentResult, ...]
    survivors: tuple[ResearchCandidate, ...]


RESEARCH_STRUCTURES = (
    (
        False,
        "EMA20",
        "EMA60",
        "score",
        60,
        "score-only baseline",
    ),
    (
        False,
        "EMA20",
        "EMA60",
        "score_or_time",
        40,
        "score with 40-session risk exit",
    ),
    (
        True,
        "EMA5",
        "EMA20",
        "score_or_ema_reversal",
        60,
        "fast EMA trend and reversal exit",
    ),
    (
        True,
        "EMA5",
        "EMA20",
        "score_or_time_or_ema_reversal",
        40,
        "fast EMA trend with time and reversal exits",
    ),
    (
        True,
        "EMA5",
        "EMA60",
        "score_or_ema_reversal",
        80,
        "wide EMA trend and reversal exit",
    ),
    (
        True,
        "EMA5",
        "EMA60",
        "score_or_time_or_ema_reversal",
        80,
        "wide EMA trend with time and reversal exits",
    ),
    (
        True,
        "EMA20",
        "EMA60",
        "score_or_ema_reversal",
        120,
        "medium/long EMA trend and reversal exit",
    ),
    (
        True,
        "EMA20",
        "EMA60",
        "score_or_time_or_ema_reversal",
        120,
        "medium/long EMA trend with time and reversal exits",
    ),
)


def generate_parameter_candidates(
    *,
    entry_scores: Iterable[int] = (55, 60, 65, 70),
    exit_scores: Iterable[int] = (35, 40, 45, 50),
    initial_capital: float = 1_000_000.0,
    strategy_family: str = "score_engine",
) -> list[ResearchCandidate]:
    """Generate deterministic, executable entry, exit and risk hypotheses."""
    candidates: list[ResearchCandidate] = []
    for entry_score, exit_score, structure in product(
        entry_scores,
        exit_scores,
        RESEARCH_STRUCTURES,
    ):
        if exit_score >= entry_score:
            continue
        (
            require_ema_trend,
            fast,
            slow,
            exit_mode,
            max_holding_days,
            label,
        ) = structure
        structure_id = "base" if not require_ema_trend else f"{fast.lower()}-{slow.lower()}"
        candidates.append(
            ResearchCandidate(
                candidate_id=(
                    f"grid-{entry_score}-{exit_score}-{structure_id}-"
                    f"{exit_mode}-{max_holding_days}"
                ),
                strategy_family=strategy_family,
                parameters={
                    "entry_score": entry_score,
                    "exit_score": exit_score,
                    "initial_capital": initial_capital,
                    "require_ema_trend": require_ema_trend,
                    "ema_fast_column": fast,
                    "ema_slow_column": slow,
                    "exit_mode": exit_mode,
                    "max_holding_days": max_holding_days,
                },
                hypothesis=(
                    "Systematic score-threshold search with "
                    f"{label}"
                ),
            )
        )
    # A stable hash avoids spending a bounded first generation on adjacent grid
    # points only. The sample remains deterministic while spanning thresholds,
    # EMA filters and risk exits early in the budget.
    candidates.sort(
        key=lambda candidate: sha256(
            candidate.candidate_id.encode("utf-8")
        ).hexdigest()
    )
    return candidates


def mutate_survivor(
    parent: ResearchCandidate,
    *,
    entry_delta: int,
    exit_delta: int,
    hypothesis_suffix: str = "local",
    strategy_structure: tuple[bool, str, str, str, int, str] | None = None,
) -> ResearchCandidate:
    params = dict(parent.parameters)
    params["entry_score"] = max(1, min(99, int(params["entry_score"]) + entry_delta))
    params["exit_score"] = max(0, min(98, int(params["exit_score"]) + exit_delta))
    if params["exit_score"] >= params["entry_score"]:
        params["exit_score"] = params["entry_score"] - 1
    structure_note = ""
    if strategy_structure is not None:
        require, fast, slow, exit_mode, max_holding_days, label = (
            strategy_structure
        )
        params.update(
            require_ema_trend=require,
            ema_fast_column=fast,
            ema_slow_column=slow,
            exit_mode=exit_mode,
            max_holding_days=max_holding_days,
        )
        structure_note = f"; structure={label}"
    identity_payload = json.dumps(
        {
            "parent_id": parent.candidate_id,
            "parameters": params,
            "hypothesis_suffix": hypothesis_suffix,
            "entry_delta": entry_delta,
            "exit_delta": exit_delta,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    mutation_id = sha256(identity_payload.encode("utf-8")).hexdigest()[:12]
    return ResearchCandidate(
        candidate_id=f"mut-{mutation_id}",
        strategy_family=parent.strategy_family,
        parameters=params,
        parent_id=parent.candidate_id,
        hypothesis=f"Adaptive {hypothesis_suffix} mutation of {parent.candidate_id}: entry {entry_delta:+d}, exit {exit_delta:+d}{structure_note}",
    )


def _mutation_neighborhood(result: ExperimentResult) -> tuple[tuple[int, int, str], ...]:
    score = result.research_score
    if result.decision is ExperimentDecision.HOLDOUT_READY or score >= 60:
        return ((-2, 0, "fine"), (2, 0, "fine"), (0, -2, "fine"), (0, 2, "fine"), (-2, -2, "fine"), (2, 2, "fine"))
    if score >= 25:
        return ((-5, 0, "local"), (5, 0, "local"), (0, -5, "local"), (0, 5, "local"), (-5, -5, "local"), (5, 5, "local"))
    return ((-10, 0, "broad"), (10, 0, "broad"), (0, -10, "broad"), (0, 10, "broad"))


def evolve_candidates(results: Iterable[ExperimentResult], *, top_k: int = 3) -> list[ResearchCandidate]:
    """Evolve thresholds and executable entry/exit/risk structure."""
    ranked = sorted((r for r in results if r.decision is not ExperimentDecision.DISCARD), key=lambda r: r.research_score, reverse=True)[:top_k]
    children: list[ResearchCandidate] = []
    seen: set[tuple[int, int, bool, str, str, str, int]] = set()
    for result in ranked:
        parent = result.candidate
        mutations = [(entry_delta, exit_delta, label, None) for entry_delta, exit_delta, label in _mutation_neighborhood(result)]
        # Structural mutations keep the parent's numeric thresholds fixed so the
        # validation comparison isolates the effect of changing the EMA rule.
        mutations.extend(
            (0, 0, "structure", structure)
            for structure in RESEARCH_STRUCTURES
        )
        for entry_delta, exit_delta, label, structure in mutations:
            child = mutate_survivor(
                parent,
                entry_delta=entry_delta,
                exit_delta=exit_delta,
                hypothesis_suffix=label,
                strategy_structure=structure,
            )
            key = (
                int(child.parameters["entry_score"]), int(child.parameters["exit_score"]),
                bool(child.parameters.get("require_ema_trend", False)),
                str(child.parameters.get("ema_fast_column", "EMA20")), str(child.parameters.get("ema_slow_column", "EMA60")),
                str(child.parameters.get("exit_mode", "score")),
                int(child.parameters.get("max_holding_days", 60)),
            )
            if key not in seen:
                seen.add(key); children.append(child)
    return children


def run_evolution_round(stock_code: str, split: ResearchSplit, candidates: Iterable[ResearchCandidate], *, generation: int, backtest_fn: BacktestFn, top_k: int = 3) -> EvolutionRound:
    evaluated = tuple(run_research_batch(stock_code, split, candidates, backtest_fn=backtest_fn))
    survivors = tuple(evolve_candidates(evaluated, top_k=top_k))
    return EvolutionRound(generation=generation, evaluated=evaluated, survivors=survivors)
