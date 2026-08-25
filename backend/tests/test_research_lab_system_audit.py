from __future__ import annotations

from scripts.audit_research_system import audit_research_system


UNIVERSE = (
    "0050", "0056", "00878", "00919", "2330", "2317", "2454", "2308",
    "2382", "2303", "2345", "2379", "2881", "2882", "2891", "2603",
    "2615", "3037", "3231", "3711",
)


def _snapshot() -> dict:
    return {
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


def test_full_research_lifecycle_can_be_operational_without_forcing_a_champion() -> None:
    audit = audit_research_system(
        snapshot=_snapshot(),
        model_selection=_model_selection(),
        bottlenecks=_bottlenecks(),
        final_holdout=_final_holdout(),
        certified_robots=_certified(),
        expected_universe=UNIVERSE,
    )

    assert audit["system_ready"] is True
    assert audit["research_engine_complete"] is True
    assert audit["system_status"] == "OPERATIONAL"
    assert audit["certified_robot_count"] == 0
    assert audit["champion_discovery_status"] == "SEARCH_CONTINUES"
    assert audit["failed_check_count"] == 0


def test_audit_fails_closed_if_validation_feedback_enters_train_memory() -> None:
    snapshot = _snapshot()
    snapshot["training_memory"]["validation_feedback_used"] = True

    audit = audit_research_system(
        snapshot=snapshot,
        model_selection=_model_selection(),
        bottlenecks=_bottlenecks(),
        final_holdout=_final_holdout(),
        certified_robots=_certified(),
        expected_universe=UNIVERSE,
    )

    assert audit["system_ready"] is False
    assert audit["system_status"] == "FAIL_CLOSED"
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "train_only_memory" in failed_names


def test_audit_fails_closed_if_eligible_holdout_is_not_accounted_for() -> None:
    holdout = _final_holdout()
    holdout["eligible_candidate_count"] = 1

    audit = audit_research_system(
        snapshot=_snapshot(),
        model_selection=_model_selection(),
        bottlenecks=_bottlenecks(),
        final_holdout=holdout,
        certified_robots=_certified(),
        expected_universe=UNIVERSE,
    )

    assert audit["system_ready"] is False
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "all_eligible_candidates_accounted_for" in failed_names


def test_audit_fails_closed_on_unresolved_durable_reservation() -> None:
    certified = _certified()
    certified["unresolved_reservation_count"] = 1

    audit = audit_research_system(
        snapshot=_snapshot(),
        model_selection=_model_selection(),
        bottlenecks=_bottlenecks(),
        final_holdout=_final_holdout(),
        certified_robots=certified,
        expected_universe=UNIVERSE,
    )

    assert audit["system_ready"] is False
    failed_names = {row["name"] for row in audit["checks"] if not row["passed"]}
    assert "no_unresolved_global_holdout_reservations" in failed_names
