from app.services.research_lab.evolution import (
    RESEARCH_STRUCTURES,
    candidate_parameter_signature,
    evolve_candidates,
    generate_parameter_candidates,
    mutate_survivor,
)
from app.services.research_lab.models import ExperimentDecision, ExperimentResult, ResearchCandidate


def _result(candidate, score, decision=ExperimentDecision.KEEP):
    return ExperimentResult(candidate, {}, decision, score, ())


def _signature(candidate):
    p = candidate.parameters
    return (
        p["entry_score"], p["exit_score"],
        bool(p.get("require_ema_trend", False)),
        p.get("ema_fast_column", "EMA20"),
        p.get("ema_slow_column", "EMA60"),
        p.get("entry_mode", "score"),
        p.get("exit_mode", "score"),
        p.get("max_holding_days", 60),
    )


def test_grid_generation_is_deterministic_and_structurally_unique():
    candidates = generate_parameter_candidates(entry_scores=(60, 70), exit_scores=(40, 65))
    assert len(candidates) == 3 * len(RESEARCH_STRUCTURES)
    assert all(c.parameters["exit_score"] < c.parameters["entry_score"] for c in candidates)
    signatures = [_signature(c) for c in candidates]
    assert len(signatures) == len(set(signatures))
    assert {(c.parameters["entry_score"], c.parameters["exit_score"]) for c in candidates} == {(60, 40), (70, 40), (70, 65)}
    assert {candidate.strategy_family for candidate in candidates} == {
        "score_engine",
        "score_engine_rsi_confirmed",
        "score_engine_bollinger_breakout",
        "score_engine_volume_confirmed",
    }
    assert len({candidate_parameter_signature(candidate) for candidate in candidates}) == len(candidates)


def test_evolution_ignores_discarded_and_uses_best_parent():
    best = ResearchCandidate("best", "score_engine", {"entry_score": 60, "exit_score": 40, "initial_capital": 1_000_000})
    discarded = ResearchCandidate("bad", "score_engine", {"entry_score": 80, "exit_score": 20, "initial_capital": 1_000_000})
    children = evolve_candidates([_result(discarded, 99, ExperimentDecision.DISCARD), _result(best, 70)], top_k=1)
    assert children
    assert all(c.parent_id == "best" for c in children)
    assert all(c.parameters["exit_score"] < c.parameters["entry_score"] for c in children)
    signatures = [_signature(c) for c in children]
    assert len(signatures) == len(set(signatures))
    assert any(c.parameters.get("require_ema_trend") for c in children)


def test_evolution_deduplicates_full_strategy_parameters():
    a = ResearchCandidate("a", "score_engine", {"entry_score": 60, "exit_score": 40, "initial_capital": 1_000_000})
    b = ResearchCandidate("b", "score_engine", {"entry_score": 70, "exit_score": 40, "initial_capital": 1_000_000})
    children = evolve_candidates([_result(a, 80), _result(b, 70)], top_k=2)
    signatures = [_signature(c) for c in children]
    assert len(signatures) == len(set(signatures))


def test_mutation_identity_is_reproducible() -> None:
    parent = ResearchCandidate(
        "parent",
        "score_engine",
        {"entry_score": 60, "exit_score": 40, "initial_capital": 1_000_000},
    )
    first = mutate_survivor(parent, entry_delta=5, exit_delta=-5)
    second = mutate_survivor(parent, entry_delta=5, exit_delta=-5)
    assert first.candidate_id == second.candidate_id
    assert first.parameters == second.parameters
