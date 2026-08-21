from app.services.research_lab.evolution import evolve_candidates, generate_parameter_candidates
from app.services.research_lab.models import ExperimentDecision, ExperimentResult, ResearchCandidate


def _result(candidate, score, decision=ExperimentDecision.KEEP):
    return ExperimentResult(candidate, {}, decision, score, ())


def test_grid_generation_is_deterministic_and_valid():
    candidates = generate_parameter_candidates(entry_scores=(60, 70), exit_scores=(40, 65))
    pairs = [(c.parameters["entry_score"], c.parameters["exit_score"]) for c in candidates]
    assert pairs == [(60, 40), (70, 40), (70, 65)]
    assert all(c.parameters["exit_score"] < c.parameters["entry_score"] for c in candidates)


def test_evolution_ignores_discarded_and_uses_best_parent():
    best = ResearchCandidate("best", "score_engine", {"entry_score": 60, "exit_score": 40, "initial_capital": 1_000_000})
    discarded = ResearchCandidate("bad", "score_engine", {"entry_score": 80, "exit_score": 20, "initial_capital": 1_000_000})
    children = evolve_candidates([
        _result(discarded, 99, ExperimentDecision.DISCARD),
        _result(best, 70),
    ], top_k=1)
    assert len(children) == 4
    assert all(c.parent_id == "best" for c in children)
    assert all(c.parameters["exit_score"] < c.parameters["entry_score"] for c in children)


def test_evolution_deduplicates_neighbor_parameters():
    a = ResearchCandidate("a", "score_engine", {"entry_score": 60, "exit_score": 40, "initial_capital": 1_000_000})
    b = ResearchCandidate("b", "score_engine", {"entry_score": 70, "exit_score": 40, "initial_capital": 1_000_000})
    children = evolve_candidates([_result(a, 80), _result(b, 70)], top_k=2)
    pairs = [(c.parameters["entry_score"], c.parameters["exit_score"]) for c in children]
    assert len(pairs) == len(set(pairs))
