from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.preserve_research_incumbent import (
    load_historical_snapshots,
    select_all_time_incumbent,
    select_research_incumbent,
)


def _candidate(
    stock: str,
    candidate_id: str,
    *,
    gates: int,
    dsr: float,
    score: float,
    decision: str = "HOLDOUT_READY",
) -> dict[str, object]:
    flags = [index < min(gates, 6) for index in range(6)]
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
        "gate_reasons": ["hansen_spa_failed_or_unavailable"],
        "regime_robust": flags[0],
        "walk_forward_sample_sufficient": flags[1],
        "walk_forward_positive_slice_ratio": 0.6667 if flags[2] else 0.0,
        "validation": {
            "statistical_quality_pass": flags[3],
            "deflated_sharpe_pass": flags[4],
            "deflated_sharpe_probability_percent": dsr,
            "wilson_lower_percent": 40.0,
            "max_drawdown_percent": 12.0,
        },
        "model_selection": {
            "hansen_spa_pass": gates >= 7,
            "cscv_pbo_pass": flags[5],
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
    assert updated["top_candidate"]["confirmation_gate_total"] == 6
    assert updated["top_candidate"]["confirmation_gate_pass_count"] == 3
    assert "hansen_spa_failed_or_unavailable" not in updated["top_candidate"][
        "gate_reasons"
    ]
    assert updated["top_candidate"]["model_selection"][
        "hansen_spa_hard_gate"
    ] is False


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


def test_incumbent_marks_behaviorally_duplicate_challenger() -> None:
    old = _candidate("2882", "old", gates=4, dsr=89.0, score=78.58)
    challenger = _candidate("2882", "new", gates=3, dsr=88.5, score=78.58)
    old["behavior"] = {"behavior_signature": "same-path"}
    challenger["behavior"] = {"behavior_signature": "same-path"}

    snapshot = {
        "campaign_id": "2026-Q3",
        "as_of_date": "2026-08-27",
        "top_candidate": challenger,
    }
    prior = {"campaign_id": "2026-Q3", "candidate": old}

    updated, _ = select_research_incumbent(
        snapshot,
        prior_incumbent=prior,
    )

    assert updated["incumbent_status"]["behavioral_near_duplicate"] is True
    assert (
        updated["incumbent_status"]["behavioral_duplicate_basis"]
        == "exact_behavior_signature"
    )
    assert updated["incumbent_status"]["behavioral_duplicate_of"] == "robot-old"


def test_all_time_survives_quarter_change_without_promoting_old_evidence() -> None:
    old = _candidate("2882", "old", gates=5, dsr=96.04, score=80.0)
    current = _candidate("2615", "current", gates=3, dsr=70.0, score=65.0)
    historical = [{
        "campaign_id": "2026-Q3", "as_of_date": "2026-09-30",
        "top_candidate": old,
    }]
    snapshot = {
        "campaign_id": "2026-Q4", "as_of_date": "2026-10-04",
        "top_candidate": current, "eligible_candidate_count": 0,
        "holdout_opened": False,
        "training_memory": {"provenance": "TRAIN_ONLY"},
    }
    original = deepcopy(snapshot)
    updated, _ = select_research_incumbent(snapshot, historical_snapshots=historical)
    archive = select_all_time_incumbent(updated, historical_snapshots=historical)

    assert archive["candidate"]["candidate_id"] == "old"
    assert archive["candidate"]["confirmation_gate_pass_count"] == 5
    assert archive["campaign_id"] == "2026-Q3"
    assert archive["source_snapshot_as_of_date"] == "2026-09-30"
    assert archive["selection"]["grants_current_promotion_eligibility"] is False
    assert archive["selection"]["feeds_train_memory"] is False
    assert archive["selection"]["opens_final_holdout"] is False
    assert updated["top_candidate"]["candidate_id"] == "current"
    assert updated["eligible_candidate_count"] == 0
    assert updated["holdout_opened"] is False
    assert updated["training_memory"] == original["training_memory"]
    assert snapshot == original


def test_durable_all_time_retains_provenance_when_original_archive_is_missing() -> None:
    old = _candidate("2882", "old", gates=5, dsr=96.04, score=80.0)
    historical = {"campaign_id": "2026-Q3", "as_of_date": "2026-09-30", "top_candidate": old}
    prior = select_all_time_incumbent(historical)
    weaker = {"campaign_id": "2027-Q1", "as_of_date": "2027-01-02",
              "top_candidate": _candidate("2615", "weaker", gates=3, dsr=70.0, score=65.0)}

    archive = select_all_time_incumbent(weaker, prior_all_time_incumbent=prior)
    assert archive["selection"]["state"] == "RETAINED"
    assert archive["candidate"] == prior["candidate"]
    assert archive["source_snapshot_as_of_date"] == "2026-09-30"
    assert archive["campaign_id"] == "2026-Q3"
    assert prior["selection"]["state"] == "BOOTSTRAPPED"


def test_all_time_replaces_only_with_stronger_observed_evidence() -> None:
    old = _candidate("2882", "same-version", gates=5, dsr=96.04, score=80.0)
    prior = select_all_time_incumbent({"campaign_id": "2026-Q3", "top_candidate": old})
    # Even the same robot version evaluated in a new quarter has new provenance.
    stronger = _candidate("2882", "same-version", gates=6, dsr=99.0, score=85.0)
    snapshot = {"campaign_id": "2026-Q4", "as_of_date": "2026-10-05", "top_candidate": stronger}
    archive = select_all_time_incumbent(snapshot, prior_all_time_incumbent=prior)
    assert archive["selection"]["state"] == "REPLACED"
    assert archive["campaign_id"] == "2026-Q4"
    assert archive["candidate"]["confirmation_gate_pass_count"] == 6
    assert archive["source_snapshot_as_of_date"] == "2026-10-05"


def test_all_time_can_recover_best_from_daily_history_when_runs_are_absent(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    observed = {"campaign_id": "2026-Q3", "as_of_date": "2026-09-30",
                "incumbent_candidate": _candidate("2882", "old", gates=5, dsr=96.04, score=80.0)}
    (history / "2026-09-30.json").write_text(json.dumps(observed))
    (history / "broken.json").write_text("interrupted write")
    recovered = load_historical_snapshots(tmp_path / "missing-runs", history)
    assert recovered == [observed]
    archive = select_all_time_incumbent({"campaign_id": "2026-Q4"}, historical_snapshots=recovered)
    assert archive["candidate"]["candidate_id"] == "old"


def test_all_time_includes_candidates_outside_snapshot_top() -> None:
    snapshot = {
        "campaign_id": "2026-Q3",
        "top_candidate": _candidate("2615", "top", gates=3, dsr=70.0, score=65.0),
        "candidates": [_candidate("2882", "best", gates=5, dsr=96.04, score=80.0)],
    }
    assert select_all_time_incumbent(snapshot)["candidate"]["candidate_id"] == "best"


def test_all_time_recovers_embedded_archive_without_changing_its_origin() -> None:
    archive = select_all_time_incumbent({
        "campaign_id": "2026-Q3", "as_of_date": "2026-09-30",
        "top_candidate": _candidate("2882", "old", gates=5, dsr=96.04, score=80.0),
    })
    snapshot = {
        "campaign_id": "2026-Q4", "as_of_date": "2026-10-05",
        "top_candidate": _candidate("2615", "new", gates=3, dsr=70.0, score=65.0),
        "all_time_incumbent": archive,
    }
    recovered = select_all_time_incumbent(snapshot)
    assert recovered["candidate"]["candidate_id"] == "old"
    assert recovered["campaign_id"] == "2026-Q3"
    assert recovered["source_snapshot_as_of_date"] == "2026-09-30"
