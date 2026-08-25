from __future__ import annotations

from scripts.aggregate_daily_autoresearch import _ranking_key


def _candidate(
    stock_code: str,
    *,
    decision: str,
    score: float,
    wilson: float,
    dsr: float,
    dsr_pass: bool,
    total_return: float,
    alpha: float,
    drawdown: float,
    regime_robust: bool = False,
    walk_forward_ratio: float = 2 / 3,
    walk_forward_sample_sufficient: bool = True,
    pbo_pass: bool = False,
    spa_pass: bool = False,
    eligible: bool = False,
) -> dict:
    candidate = {
        "stock_code": stock_code,
        "decision": decision,
        "research_score": score,
        "eligible_for_one_shot_holdout": eligible,
        "regime_robust": regime_robust,
        "walk_forward_sample_sufficient": walk_forward_sample_sufficient,
        "walk_forward_positive_slice_ratio": walk_forward_ratio,
        "validation": {
            "total_return_percent": total_return,
            "alpha_percent": alpha,
            "wilson_lower_percent": wilson,
            "deflated_sharpe_probability_percent": dsr,
            "deflated_sharpe_pass": dsr_pass,
            "statistical_quality_pass": False,
            "max_drawdown_percent": drawdown,
        },
        "model_selection": {
            "cscv_pbo_pass": pbo_pass,
            "hansen_spa_pass": spa_pass,
        },
    }
    confirmation = sum(
        (
            regime_robust,
            walk_forward_sample_sufficient,
            walk_forward_ratio >= 0.5,
            False,
            dsr_pass,
            pbo_pass,
            spa_pass,
        )
    )
    candidate["confirmation_gate_pass_count"] = confirmation
    return candidate


def test_holdout_ready_stronger_evidence_beats_small_sample_wilson_leader() -> None:
    # Mirrors the 2026-08-25 failure mode: the KEEP candidate has a higher
    # Wilson lower bound, while the HOLDOUT_READY candidate has much stronger
    # DSR, research score, return, and alpha. Wilson must not dominate the rank.
    small_sample_wilson_leader = _candidate(
        "00919",
        decision="KEEP",
        score=44.53,
        wilson=51.01,
        dsr=2.64,
        dsr_pass=False,
        total_return=12.09,
        alpha=-13.57,
        drawdown=4.72,
    )
    stronger_holdout_ready = _candidate(
        "2882",
        decision="HOLDOUT_READY",
        score=72.15,
        wilson=43.65,
        dsr=70.38,
        dsr_pass=True,
        total_return=50.86,
        alpha=4.13,
        drawdown=15.37,
    )

    ranked = sorted(
        [small_sample_wilson_leader, stronger_holdout_ready],
        key=_ranking_key,
        reverse=True,
    )

    assert ranked[0]["stock_code"] == "2882"


def test_promotion_eligibility_remains_absolute_first_priority() -> None:
    eligible = _candidate(
        "2330",
        decision="KEEP",
        score=10.0,
        wilson=1.0,
        dsr=1.0,
        dsr_pass=False,
        total_return=1.0,
        alpha=0.0,
        drawdown=30.0,
        eligible=True,
    )
    not_eligible = _candidate(
        "2882",
        decision="HOLDOUT_READY",
        score=99.0,
        wilson=99.0,
        dsr=99.0,
        dsr_pass=True,
        total_return=99.0,
        alpha=99.0,
        drawdown=1.0,
        eligible=False,
        regime_robust=True,
        pbo_pass=True,
        spa_pass=True,
    )

    ranked = sorted([not_eligible, eligible], key=_ranking_key, reverse=True)
    assert ranked[0]["stock_code"] == "2330"
