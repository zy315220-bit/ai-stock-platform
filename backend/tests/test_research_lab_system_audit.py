from __future__ import annotations

from scripts.audit_research_system import audit_research_system


UNIVERSE = (
    "0050", "0056", "00878", "00919", "2330", "2317", "2454", "2308",
    "2382", "2303", "2345", "2379", "2881", "2882", "2891", "2603",
    "2615", "3037", "3231", "3711",
)


def _snapshot() -> dict:
    return {
        "automation": {
            "enabled": True,
            "mode": "daily_unattended",
            "schedule": "30 22,10 * * *",
            "schedule_timezone": "Asia/Taipei",
            "sessions_per_day": 2,
            "manual_action_required": False,
        },
        "universe": list(UNIVERSE),
        "completed_symbol_count": 20,
        "integrity_status": "PASS",
        "holdout_opened": False,
        "training_memory": {
            "provenance": "TRAIN_ONLY",
            "validation_feedback_used": False,
            "holdout_feedback_used": False,
            "verified_data_identity_symbol_count": 20,
        },
        "ranking_methodology": {
            "schema": "paper-guided-evidence-ranking-v1",
            "production_champion_rule": "one_shot_holdout_required",
            "small_sample_win_rate_role": "supporting_tiebreaker_only",
        },
    }


def _model_selection() -> dict:
    return {"symbol_count": 20}


def _bottlenecks() -> dict:
    return {
        "symbol_count": 20,
        "feedback_policy": (
            "OBSERVATION_ONLY: validation/holdout diagnostics must not feed "
            "candidate generation or train-memory adaptation"
        ),
    }


def _final_holdout() -> dict:
    return {
        "policy": {
            "one_shot": True,
            "durable_reservation_before_open": True,
            "open_only_after_all_promotion_gates_pass": True,
            "holdout_feedback_to_train": False,
            "overwrite_existing_ledger": False,
        },
        "eligible_candidate_count": 0,
        "newly_opened_count": 0,
        "already_evaluated_count": 0,
        "blocked_reservation_count": 0,
        "final_pass_count": 0,
    }


def _certified() -> dict:
    return {
        "certified_robot_count": 0,
        "unresolved_reservation_count": 0,
        "robots": [],
    }


def _challengers() -> dict:
    return {
        "schema_version": 2,
        "status": "WAITING_FOR_CERTIFIED_ROBOT",
        "challenger_count": 0,
        "policy": {
            "certified_final_holdout_required": True,
            "immutable_rule_fingerprint_required": True,
            "competition_rebinds_capital_cost_risk_and_universe": True,
            "holdout_score_used_for_ranking": False,
            "same_campaign_competition_feedback_to_train": False,
            "post_certification_evidence_only": True,
            "common_fresh_comparison_window": True,
        },
        "challengers": [],
    }


def _tournament() -> dict:
    return {
        "schema_version": 2,
        "status": "WAITING_FOR_CERTIFIED_ROBOT",
        "challenger_count": 0,
        "promotion": {
            "challenger_replaced_incumbent": False,
            "reason": "No Final-Holdout-certified challenger exists yet.",
            "competition_feedback_to_same_campaign_train": False,
        },
    }


def _audit(
    snapshot: dict | None = None,
    final_holdout: dict | None = None,
    certified: dict | None = None,
    challengers: dict | None = None,
    tournament: dict | None = None,
):
    return audit_research_system(
        snapshot=snapshot or _snapshot(),
        model_selection=_model_selection(),
        bottlenecks=_bottlenecks(),
        final_holdout=final_holdout or _final_holdout(),
        certified_robots=certified or _certified(),
        challenger_roster=challengers or _challengers(),
        competition_tournament=tournament or _tournament(),
        expected_universe=UNIVERSE,
    )


def test_full_research_lifecycle_can_be_operational_without_forcing_a_champion() -> None:
    audit = _audit()
    assert audit["system_ready"] is True
    assert audit["research_engine_complete"] is True
    assert audit["competition_research_loop_complete"] is True
    assert audit["post_certification_evidence_isolated"] is True
    assert audit["system_status"] == "OPERATIONAL"
    assert audit["certified_robot_count"] == 0
    assert audit["competition_challenger_count"] == 0
    assert audit["champion_discovery_status"] == "SEARCH_CONTINUES"
    assert audit["failed_check_count"] == 0


def test_audit_fails_closed_if_validation_feedback_enters_train_memory() -> None:
    snapshot = _snapshot()
    snapshot["training_memory"]["validation_feedback_used"] = True
    audit = _audit(snapshot=snapshot)
    assert audit["system_ready"] is False
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "train_only_memory" in failed_names


def test_audit_fails_closed_if_scheduler_drops_weekend_or_second_session() -> None:
    snapshot = _snapshot()
    snapshot["automation"]["schedule"] = "30 10 * * 1-5"
    snapshot["automation"]["sessions_per_day"] = 1
    audit = _audit(snapshot=snapshot)
    assert audit["system_ready"] is False
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "autonomous_scheduler_registered" in failed_names


def test_audit_fails_closed_if_eligible_holdout_is_not_accounted_for() -> None:
    holdout = _final_holdout()
    holdout["eligible_candidate_count"] = 1
    audit = _audit(final_holdout=holdout)
    assert audit["system_ready"] is False
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "all_eligible_candidates_accounted_for" in failed_names


def test_audit_fails_closed_on_unresolved_durable_reservation() -> None:
    certified = _certified()
    certified["unresolved_reservation_count"] = 1
    audit = _audit(certified=certified)
    assert audit["system_ready"] is False
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "no_unresolved_global_holdout_reservations" in failed_names


def test_audit_fails_closed_if_competition_bridge_is_missing_certified_robot() -> None:
    certified = {
        "certified_robot_count": 1,
        "unresolved_reservation_count": 0,
        "robots": [{"status": "CERTIFIED_FINAL_HOLDOUT_PASS"}],
    }
    audit = _audit(certified=certified)
    assert audit["system_ready"] is False
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "certified_competition_bridge_registered" in failed_names


def test_audit_accepts_quarantine_while_waiting_for_fresh_market_data() -> None:
    certified = {
        "certified_robot_count": 1,
        "unresolved_reservation_count": 0,
        "robots": [{"status": "CERTIFIED_FINAL_HOLDOUT_PASS"}],
    }
    challengers = _challengers()
    challengers["status"] = "READY"
    challengers["challenger_count"] = 1
    challengers["challengers"] = [
        {
            "challenge_contract": {
                "post_certification_evidence_only": True,
                "challenge_not_before": "2026-08-27",
            }
        }
    ]
    tournament = {
        "schema_version": 2,
        "status": "ACCUMULATING_POST_CERTIFICATION_EVIDENCE",
        "challenger_count": 1,
        "common_fresh_window": {
            "start": "2026-08-27",
            "end": "2026-08-25",
            "available": False,
        },
        "promotion": {
            "challenger_replaced_incumbent": False,
            "competition_feedback_to_same_campaign_train": False,
        },
    }
    audit = _audit(certified=certified, challengers=challengers, tournament=tournament)
    assert audit["system_ready"] is True


def test_audit_rejects_completed_tournament_without_fresh_window_policy() -> None:
    certified = {
        "certified_robot_count": 1,
        "unresolved_reservation_count": 0,
        "robots": [{"status": "CERTIFIED_FINAL_HOLDOUT_PASS"}],
    }
    challengers = _challengers()
    challengers["status"] = "READY"
    challengers["challenger_count"] = 1
    challengers["challengers"] = [
        {
            "challenge_contract": {
                "post_certification_evidence_only": True,
                "challenge_not_before": "2026-08-21",
            }
        }
    ]
    tournament = {
        "schema_version": 2,
        "status": "completed",
        "challenger_count": 1,
        "common_fresh_window": {"start": "2026-08-21", "end": "2026-08-25", "available": True},
        "evaluation_policy": {
            "post_certification_evidence_only": False,
            "final_holdout_overlap_forbidden": False,
            "common_fresh_comparison_window": False,
            "same_capital_cost_risk_universe": True,
        },
        "promotion": {
            "challenger_replaced_incumbent": False,
            "competition_feedback_to_same_campaign_train": False,
        },
    }
    audit = _audit(certified=certified, challengers=challengers, tournament=tournament)
    assert audit["system_ready"] is False
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "post_certification_title_evidence_isolated" in failed_names
