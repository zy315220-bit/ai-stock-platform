from app.services.research_lab.models import (
    ExperimentDecision,
    ExperimentResult,
    ResearchCandidate,
    ResearchSplit,
)
from app.services.research_lab.promotion import run_holdout_gate


ROBUST = {
    "robust_across_required_regimes": True,
    "robustness_score": 72.0,
    "holdout_used": False,
}
MODEL_SELECTION = {
    "cscv_pbo": {"overfitting_risk_pass": True},
    "hansen_spa": {"superior_predictive_ability_pass": True},
}


def _split():
    return ResearchSplit(
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-01",
        validation_end="2024-12-31",
        holdout_start="2025-01-01",
        holdout_end="2025-12-31",
    )


def _qualified():
    candidate = ResearchCandidate("ema-1", "score_threshold", {"entry_score": 70, "exit_score": 40})
    return ExperimentResult(
        candidate,
        {
            "statistical_evidence": {"statistical_quality_pass": True},
            "deflated_sharpe": {"multiple_testing_pass": True},
        },
        ExperimentDecision.HOLDOUT_READY,
        60.0,
    )


def test_holdout_gate_uses_only_holdout_dates():
    calls = []

    def fake_backtest(**kwargs):
        calls.append(kwargs)
        return {
            "performance_metrics": {"sharpe_ratio": 1.8, "sortino_ratio": 2.5, "calmar_ratio": 1.6},
            "total_return_percent": 20,
            "alpha_percent": 8,
            "max_drawdown_percent": 10,
            "total_trades": 20,
            "winning_trade_count": 12,
            "win_rate_percent": 60,
        }

    result = run_holdout_gate(
        "2330",
        _split(),
        _qualified(),
        regime_robustness=ROBUST,
        model_selection_evidence=MODEL_SELECTION,
        backtest_fn=fake_backtest,
    )
    assert result.promoted is True
    assert len(calls) == 1
    assert calls[0]["start_date"] == "2025-01-01"
    assert calls[0]["end_date"] == "2025-12-31"


def test_unqualified_candidate_cannot_touch_holdout():
    called = False

    def fake_backtest(**kwargs):
        nonlocal called
        called = True
        return {}

    weak = ExperimentResult(_qualified().candidate, {}, ExperimentDecision.KEEP, 30.0)
    try:
        run_holdout_gate(
            "2330",
            _split(),
            weak,
            regime_robustness=ROBUST,
            model_selection_evidence=MODEL_SELECTION,
            backtest_fn=fake_backtest,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    assert called is False


def test_holdout_degradation_blocks_promotion():
    def fake_backtest(**kwargs):
        return {
            "performance_metrics": {"sharpe_ratio": 0.3, "sortino_ratio": 0.5, "calmar_ratio": 0.3},
            "total_return_percent": 3,
            "max_drawdown_percent": 20,
            "total_trades": 20,
        }

    result = run_holdout_gate(
        "2330",
        _split(),
        _qualified(),
        regime_robustness=ROBUST,
        model_selection_evidence=MODEL_SELECTION,
        backtest_fn=fake_backtest,
    )
    assert result.promoted is False
    assert result.reasons


def test_regime_failure_cannot_touch_holdout():
    called = False

    def fake_backtest(**kwargs):
        nonlocal called
        called = True
        return {}

    try:
        run_holdout_gate(
            "2330",
            _split(),
            _qualified(),
            regime_robustness={
                "robust_across_required_regimes": False,
                "holdout_used": False,
            },
            model_selection_evidence=MODEL_SELECTION,
            backtest_fn=fake_backtest,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    assert called is False


def test_set_level_spa_failure_does_not_block_selected_candidate_holdout():
    def fake_backtest(**kwargs):
        return {
            "performance_metrics": {
                "sharpe_ratio": 1.8,
                "sortino_ratio": 2.5,
                "calmar_ratio": 1.6,
            },
            "total_return_percent": 20,
            "alpha_percent": 8,
            "max_drawdown_percent": 10,
            "total_trades": 20,
            "winning_trade_count": 12,
            "win_rate_percent": 60,
        }

    result = run_holdout_gate(
        "2330",
        _split(),
        _qualified(),
        regime_robustness=ROBUST,
        model_selection_evidence={
            "cscv_pbo": {"overfitting_risk_pass": True},
            "hansen_spa": {"superior_predictive_ability_pass": False},
        },
        backtest_fn=fake_backtest,
    )
    assert result.promoted is True
