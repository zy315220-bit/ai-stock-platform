from app.services.research_lab.evolution import (
    RESEARCH_STRUCTURES,
    SIGNAL_DOMINANT_FAMILIES,
    SIGNAL_DOMINANT_STRUCTURES,
    candidate_parameter_signature,
    evolve_candidates,
    generate_parameter_candidates,
    generate_signal_dominant_candidates,
    mutate_survivor,
)
from app.services.research_lab.models import (
    ExperimentDecision,
    ExperimentResult,
    ResearchCandidate,
)


def _result(candidate, score, decision=ExperimentDecision.KEEP):
    return ExperimentResult(candidate, {}, decision, score, ())


def _signature(candidate):
    p = candidate.parameters
    return (
        p["entry_score"],
        p["exit_score"],
        bool(p.get("require_ema_trend", False)),
        p.get("ema_fast_column", "EMA20"),
        p.get("ema_slow_column", "EMA60"),
        p.get("entry_mode", "score"),
        p.get("exit_mode", "score"),
        p.get("max_holding_days", 60),
    )


def test_grid_generation_is_deterministic_and_structurally_unique():
    candidates = generate_parameter_candidates(
        entry_scores=(60, 70),
        exit_scores=(40, 65),
    )
    score_candidates = [
        candidate
        for candidate in candidates
        if candidate.strategy_family not in SIGNAL_DOMINANT_FAMILIES
    ]
    signal_candidates = [
        candidate
        for candidate in candidates
        if candidate.strategy_family in SIGNAL_DOMINANT_FAMILIES
    ]

    assert len(score_candidates) == 3 * len(RESEARCH_STRUCTURES)
    assert len(signal_candidates) == len(SIGNAL_DOMINANT_STRUCTURES)
    assert all(
        candidate.parameters["exit_score"]
        < candidate.parameters["entry_score"]
        for candidate in candidates
    )
    signatures = [_signature(candidate) for candidate in candidates]
    assert len(signatures) == len(set(signatures))
    assert {
        (
            candidate.parameters["entry_score"],
            candidate.parameters["exit_score"],
        )
        for candidate in score_candidates
    } == {(60, 40), (70, 40), (70, 65)}
    assert {
        candidate.strategy_family for candidate in score_candidates
    } == {
        "score_engine",
        "score_engine_rsi_confirmed",
        "score_engine_bollinger_breakout",
        "score_engine_volume_confirmed",
    }
    assert {
        candidate.strategy_family for candidate in signal_candidates
    } == SIGNAL_DOMINANT_FAMILIES
    assert all(
        candidate.parameters["entry_score"] == 1
        and candidate.parameters["exit_score"] == 0
        for candidate in signal_candidates
    )
    assert len(
        {
            candidate_parameter_signature(candidate)
            for candidate in candidates
        }
    ) == len(candidates)


def test_signal_dominant_generation_is_deterministic_and_family_complete():
    first = generate_signal_dominant_candidates()
    second = generate_signal_dominant_candidates()
    assert [candidate.candidate_id for candidate in first] == [
        candidate.candidate_id for candidate in second
    ]
    assert {candidate.strategy_family for candidate in first} == (
        SIGNAL_DOMINANT_FAMILIES
    )
    assert all(
        candidate.parameters["entry_score"] == 1
        and candidate.parameters["exit_score"] == 0
        for candidate in first
    )


def test_signal_dominant_parent_preserves_neutral_score_gate_during_evolution():
    parent = generate_signal_dominant_candidates()[0]
    children = evolve_candidates([_result(parent, 70)], top_k=1)
    assert children
    assert all(
        child.strategy_family == parent.strategy_family
        for child in children
    )
    assert all(
        child.parameters["entry_score"] == 1
        and child.parameters["exit_score"] == 0
        for child in children
    )


def test_evolution_ignores_discarded_and_uses_best_parent():
    best = ResearchCandidate(
        "best",
        "score_engine",
        {
            "entry_score": 60,
            "exit_score": 40,
            "initial_capital": 1_000_000,
        },
    )
    discarded = ResearchCandidate(
        "bad",
        "score_engine",
        {
            "entry_score": 80,
            "exit_score": 20,
            "initial_capital": 1_000_000,
        },
    )
    children = evolve_candidates(
        [
            _result(discarded, 99, ExperimentDecision.DISCARD),
            _result(best, 70),
        ],
        top_k=1,
    )
    assert children
    assert all(child.parent_id == "best" for child in children)
    assert all(
        child.parameters["exit_score"]
        < child.parameters["entry_score"]
        for child in children
    )
    signatures = [_signature(child) for child in children]
    assert len(signatures) == len(set(signatures))
    assert any(child.parameters.get("require_ema_trend") for child in children)


def test_evolution_deduplicates_full_strategy_parameters():
    a = ResearchCandidate(
        "a",
        "score_engine",
        {
            "entry_score": 60,
            "exit_score": 40,
            "initial_capital": 1_000_000,
        },
    )
    b = ResearchCandidate(
        "b",
        "score_engine",
        {
            "entry_score": 70,
            "exit_score": 40,
            "initial_capital": 1_000_000,
        },
    )
    children = evolve_candidates(
        [_result(a, 80), _result(b, 70)],
        top_k=2,
    )
    signatures = [_signature(child) for child in children]
    assert len(signatures) == len(set(signatures))


def test_mutation_identity_is_reproducible() -> None:
    parent = ResearchCandidate(
        "parent",
        "score_engine",
        {
            "entry_score": 60,
            "exit_score": 40,
            "initial_capital": 1_000_000,
        },
    )
    first = mutate_survivor(parent, entry_delta=5, exit_delta=-5)
    second = mutate_survivor(parent, entry_delta=5, exit_delta=-5)
    assert first.candidate_id == second.candidate_id
    assert first.parameters == second.parameters
