from __future__ import annotations

from datetime import date

import pandas as pd

from app.api import research_lab as api
from app.services.research_lab.autoresearch import ResearchSession
from app.services.research_lab.evolution import EvolutionRound
from app.services.research_lab.market_regimes import MarketRegimeMatrix
from app.services.research_lab.models import (
    ExperimentDecision,
    ExperimentResult,
    ResearchCandidate,
)
from app.services.research_lab.walk_forward import WalkForwardEvidence


def _candidate() -> ResearchCandidate:
    return ResearchCandidate(
        "candidate-1",
        "score_engine",
        {"entry_score": 60, "exit_score": 40},
        hypothesis="test candidate",
    )


def _statistics() -> dict[str, object]:
    return {
        "available": True,
        "period_sharpe_ratio": 0.2,
        "observations": 300,
        "skewness": 0.0,
        "kurtosis": 3.0,
        "statistical_quality_pass": True,
        "probabilistic_sharpe_ratio_percent": 99.0,
        "minimum_track_record_observations": 100,
        "track_record_sufficient": True,
    }


def test_api_exposes_full_gate_without_opening_holdout(monkeypatch) -> None:
    candidate = _candidate()
    training = ExperimentResult(
        candidate,
        {
            "statistical_evidence": _statistics(),
            "_daily_excess_returns": [0.01] * 300,
        },
        ExperimentDecision.KEEP,
        60.0,
        evaluation_phase="train",
    )
    validation = ExperimentResult(
        candidate,
        {
            "statistical_evidence": _statistics(),
            "_daily_excess_returns": [0.01] * 300,
            "completed_trades": 12,
        },
        ExperimentDecision.HOLDOUT_READY,
        70.0,
        evaluation_phase="validation",
    )
    session = ResearchSession(
        stock_code="2330",
        rounds=(EvolutionRound(1, (training,), (candidate,)),),
        best_result=training,
        experiments_run=1,
        stopped_reason="generation_budget_reached",
    )
    robustness = {
        "robust_across_required_regimes": True,
        "robustness_score": 80.0,
        "reasons": [],
        "holdout_used": False,
    }
    matrix = MarketRegimeMatrix(
        candidate_id=candidate.candidate_id,
        benchmark_code="0050",
        slices=(),
        by_regime={
            key: {
                "slice_count": 1,
                "completed_trades": 4,
                "winning_trades": 3,
                "win_rate_percent": 75.0,
                "wilson_win_rate_lower_bound_percent": 30.0,
                "mean_return_percent": 5.0,
                "mean_benchmark_return_percent": 1.0,
                "mean_alpha_percent": 4.0,
                "positive_alpha_slice_ratio": 1.0,
                "worst_drawdown_percent": 5.0,
            }
            for key in ("BULL", "BEAR", "SIDEWAYS")
        },
        robustness=robustness,
    )
    walk_forward = WalkForwardEvidence(
        candidate_id=candidate.candidate_id,
        slices=(),
        aggregate={
            "positive_slice_ratio": 1.0,
            "evidence_quality": {"sample_sufficient": True},
            "holdout_used": False,
        },
    )

    monkeypatch.setattr(api, "run_autoresearch", lambda *args, **kwargs: session)
    monkeypatch.setattr(api, "run_research_batch", lambda *args, **kwargs: [validation])
    monkeypatch.setattr(
        api,
        "load_point_in_time_benchmark_returns",
        lambda *args, **kwargs: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        api,
        "run_market_regime_validation",
        lambda *args, **kwargs: matrix,
    )
    monkeypatch.setattr(
        api,
        "run_walk_forward_validation",
        lambda *args, **kwargs: walk_forward,
    )
    monkeypatch.setattr(
        api,
        "deflated_sharpe_evidence",
        lambda *args, **kwargs: {
            "available": True,
            "multiple_testing_pass": True,
        },
    )
    monkeypatch.setattr(
        api,
        "cscv_probability_of_backtest_overfitting",
        lambda *args, **kwargs: {
            "available": True,
            "overfitting_risk_pass": True,
        },
    )
    monkeypatch.setattr(
        api,
        "hansen_spa_test",
        lambda *args, **kwargs: {
            "available": True,
            "superior_predictive_ability_pass": True,
        },
    )

    payload = api.run_research(
        stock_code="2330",
        start_date=date(2020, 1, 1),
        end_date=date(2025, 12, 31),
        max_generations=1,
        max_experiments=1,
        min_validation_trades=1,
        validation_finalists=1,
        walk_forward_slices=2,
        regime_candidate_count=1,
        regime_slices=3,
        min_regime_trades=1,
    )

    assert payload["best_result"]["candidate"]["candidate_id"] == "candidate-1"
    assert payload["promotion_eligibility"] == {
        "eligible_for_one_shot_holdout": True,
        "reasons": [],
        "holdout_opened": False,
    }
    assert payload["research_audit"]["validation_used_during_adaptive_search"] is False
    assert payload["research_audit"]["holdout_used_during_search"] is False
    assert payload["holdout_status"] == "LOCKED_REQUIRES_PROMOTION_GATE"


def test_spa_failure_is_set_level_diagnostic_not_individual_blocker(monkeypatch) -> None:
    candidate = _candidate()
    training = ExperimentResult(
        candidate,
        {
            "statistical_evidence": _statistics(),
            "_daily_excess_returns": [0.01] * 300,
        },
        ExperimentDecision.KEEP,
        60.0,
        evaluation_phase="train",
    )
    validation = ExperimentResult(
        candidate,
        {
            "statistical_evidence": _statistics(),
            "_daily_excess_returns": [0.01] * 300,
            "completed_trades": 12,
        },
        ExperimentDecision.HOLDOUT_READY,
        70.0,
        evaluation_phase="validation",
    )
    session = ResearchSession(
        stock_code="2330",
        rounds=(EvolutionRound(1, (training,), (candidate,)),),
        best_result=training,
        experiments_run=1,
        stopped_reason="generation_budget_reached",
    )
    matrix = MarketRegimeMatrix(
        candidate_id=candidate.candidate_id,
        benchmark_code="0050",
        slices=(),
        by_regime={},
        robustness={
            "robust_across_required_regimes": True,
            "robustness_score": 80.0,
            "reasons": [],
            "holdout_used": False,
        },
    )
    walk_forward = WalkForwardEvidence(
        candidate_id=candidate.candidate_id,
        slices=(),
        aggregate={
            "positive_slice_ratio": 1.0,
            "evidence_quality": {"sample_sufficient": True},
            "holdout_used": False,
        },
    )

    monkeypatch.setattr(api, "run_autoresearch", lambda *args, **kwargs: session)
    monkeypatch.setattr(api, "run_research_batch", lambda *args, **kwargs: [validation])
    monkeypatch.setattr(
        api,
        "load_point_in_time_benchmark_returns",
        lambda *args, **kwargs: pd.Series(dtype=float),
    )
    monkeypatch.setattr(api, "run_market_regime_validation", lambda *args, **kwargs: matrix)
    monkeypatch.setattr(api, "run_walk_forward_validation", lambda *args, **kwargs: walk_forward)
    monkeypatch.setattr(
        api,
        "deflated_sharpe_evidence",
        lambda *args, **kwargs: {"available": True, "multiple_testing_pass": True},
    )
    monkeypatch.setattr(
        api,
        "cscv_probability_of_backtest_overfitting",
        lambda *args, **kwargs: {"available": True, "overfitting_risk_pass": True},
    )
    monkeypatch.setattr(
        api,
        "hansen_spa_test",
        lambda *args, **kwargs: {
            "available": True,
            "superior_predictive_ability_pass": False,
            "spa_p_value": 0.60,
        },
    )

    payload = api.execute_research_pipeline(
        stock_code="2330",
        start_date=date(2020, 1, 1),
        end_date=date(2025, 12, 31),
        max_generations=1,
        max_experiments=1,
        min_validation_trades=1,
        validation_finalists=1,
        walk_forward_slices=2,
        regime_candidate_count=1,
        regime_slices=3,
        min_regime_trades=1,
    )

    assert payload["promotion_eligibility"]["eligible_for_one_shot_holdout"] is True
    assert payload["promotion_eligibility"]["reasons"] == []
    assert payload["model_selection_evidence"]["hansen_spa_hard_gate"] is False
    assert payload["model_selection_evidence"]["hansen_spa"]["spa_p_value"] == 0.60
