from app.services.research_lab.autoresearch import run_autoresearch
from app.services.research_lab.evolution import (
    candidate_parameter_signature,
    generate_parameter_candidates,
)
from app.services.research_lab.models import ResearchSplit


def split():
    return ResearchSplit("2020-01-01", "2022-12-31", "2023-01-01", "2024-12-31", "2025-01-01", "2025-12-31")


def report_for_score(**kwargs):
    entry = kwargs["entry_score"]
    return {
        "performance_metrics": {"sharpe_ratio": entry / 40, "sortino_ratio": entry / 30, "calmar_ratio": entry / 45},
        "total_return_percent": entry / 2,
        "max_drawdown_percent": 8,
        "total_trades": 20,
    }


def weak_report(**kwargs):
    return {
        "performance_metrics": {"sharpe_ratio": -0.5, "sortino_ratio": -0.5, "calmar_ratio": -0.2},
        "total_return_percent": -5,
        "max_drawdown_percent": 12,
        "total_trades": 20,
    }


def test_autoresearch_respects_experiment_budget():
    session = run_autoresearch(
        "2330", split(), generate_parameter_candidates(entry_scores=(55, 60, 65), exit_scores=(40,)),
        backtest_fn=report_for_score, max_generations=10, max_experiments=4, target_score=999,
    )
    assert session.experiments_run == 4
    assert session.stopped_reason == "experiment_budget_reached"


def test_autoresearch_stops_when_every_candidate_dies():
    candidates = generate_parameter_candidates(entry_scores=(55, 60), exit_scores=(40,))
    session = run_autoresearch(
        "2330", split(), candidates,
        backtest_fn=weak_report, max_generations=10, max_experiments=100,
    )
    assert session.experiments_run == 10
    assert len(session.rounds) == 1
    assert session.stopped_reason == "no_surviving_candidates"


def test_autoresearch_never_calls_holdout_dates():
    calls = []
    def recording_backtest(**kwargs):
        calls.append((kwargs["start_date"], kwargs["end_date"]))
        return report_for_score(**kwargs)

    session = run_autoresearch(
        "2330", split(), generate_parameter_candidates(entry_scores=(55, 60), exit_scores=(40,)),
        backtest_fn=recording_backtest, max_generations=2, max_experiments=5, target_score=999,
    )
    assert calls
    assert all(start == "2020-01-01" and end == "2022-12-31" for start, end in calls)
    assert all(start != "2025-01-01" for start, _ in calls)
    assert all(result.evaluation_phase == "train" for round_ in session.rounds for result in round_.evaluated)


def test_autoresearch_skips_signatures_seen_on_prior_days():
    candidates = generate_parameter_candidates(
        entry_scores=(55, 60),
        exit_scores=(40,),
    )
    excluded = {
        candidate_parameter_signature(candidate)
        for candidate in candidates[:2]
    }
    session = run_autoresearch(
        "2330",
        split(),
        candidates,
        backtest_fn=report_for_score,
        max_generations=1,
        max_experiments=3,
        target_score=999,
        excluded_parameter_signatures=excluded,
    )
    assert session.experiments_run == 3
    assert session.skipped_duplicate_count == 2
    assert set(session.evaluated_parameter_signatures).isdisjoint(excluded)
