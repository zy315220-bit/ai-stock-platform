from __future__ import annotations

from scripts.preserve_research_incumbent import select_research_incumbent


def _candidate(
    stock: str,
    candidate_id: str,
    *,
    gates: int,
    dsr: float,
    score: float,
    decision: str = "HOLDOUT_READY",
) -> dict[str, object]:
    return {
        "stock_code": stock,
        "candidate_id": candidate_id,
        "robot_version_id": f"robot-{candidate_id}",
        "decision": decision,
        "decision_rank": 2 if decision == "HOLDOUT_READY" else 1,
        "research_score": score,
        "eligible_for_one_shot_holdout": False,
        "confirmation_gate_pass_count": gates,
        "confirmation_gate_total": 7,
        "regime_robust": False,
        "walk_forward_sample_sufficient": True,
        "walk_forward_positive_slice_ratio": 0.6667,
        "validation": {
            "deflated_sharpe_pass": False,
            "deflated_sharpe_probability_percent": dsr,
            "wilson_lower_percent": 40.0,
            "max_drawdown_percent": 12.0,
        },
        "model_selection": {
            "hansen_spa_pass": False,
            "cscv_pbo_pass": False,
        },
    }


def test_old_stronger_candidate_is_retained() -> None:
    old = _candidate("2882", "old", gates=3, dsr=66.38, score=72.15)
    challenger = _candidate("2891", "new", gates=2, dsr=48.28, score=50.93)
    snapshot = {
        "campaign_id": "2026-Q3",
        "as_of_date": "2026-08-26",
        "top_candidate": challenger,
    }
    prior = {"campaign_id": "2026-Q3", "candidate": old}

    updated, record = select_research_incumbent(
        snapshot,
        prior_incumbent=prior,
    )

    assert updated["round_top_candidate"]["stock_code"] == "2891"
    assert updated["top_candidate"]["stock_code"] == "2882"
    assert updated["incumbent_candidate"]["candidate_id"] == "old"
    assert updated["incumbent_status"]["state"] == "RETAINED"
    assert record["candidate"]["stock_code"] == "2882"


def test_stronger_current_round_replaces_incumbent() -> None:
    old = _candidate("2882", "old", gates=3, dsr=66.38, score=72.15)
    challenger = _candidate("2330", "new", gates=4, dsr=80.0, score=74.0)
    snapshot = {
        "campaign_id": "2026-Q3",
        "as_of_date": "2026-08-26",
        "top_candidate": challenger,
    }
    prior = {"campaign_id": "2026-Q3", "candidate": old}

    updated, _ = select_research_incumbent(
        snapshot,
        prior_incumbent=prior,
    )

    assert updated["top_candidate"]["stock_code"] == "2330"
    assert updated["incumbent_status"]["state"] == "REPLACED"
    assert updated["incumbent_status"][
        "round_challenger_replaced_incumbent"
    ] is True


def test_historical_runs_bootstrap_missing_incumbent() -> None:
    old = _candidate("2882", "historical", gates=3, dsr=66.38, score=72.15)
    challenger = _candidate("2891", "round", gates=2, dsr=48.28, score=50.93)
    snapshot = {
        "campaign_id": "2026-Q3",
        "as_of_date": "2026-08-26",
        "top_candidate": challenger,
    }
    historical = [
        {
            "campaign_id": "2026-Q3",
            "top_candidate": old,
        }
    ]

    updated, _ = select_research_incumbent(
        snapshot,
        historical_snapshots=historical,
    )

    assert updated["top_candidate"]["stock_code"] == "2882"
    assert updated["incumbent_status"]["state"] == "BOOTSTRAPPED"
    assert updated["incumbent_status"]["source"] == "historical_run"


def test_prior_campaign_is_not_compared() -> None:
    stale = _candidate("2882", "stale", gates=7, dsr=99.0, score=99.0)
    challenger = _candidate("2891", "fresh", gates=2, dsr=48.28, score=50.93)
    snapshot = {
        "campaign_id": "2026-Q4",
        "as_of_date": "2026-10-01",
        "top_candidate": challenger,
    }
    prior = {"campaign_id": "2026-Q3", "candidate": stale}

    updated, _ = select_research_incumbent(
        snapshot,
        prior_incumbent=prior,
    )

    assert updated["top_candidate"]["stock_code"] == "2891"
    assert updated["incumbent_status"]["same_campaign_only"] is True
    assert updated["incumbent_status"]["feeds_train_memory"] is False
