from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.scanner_service import SCANNER_UNIVERSE
from scripts.run_daily_autoresearch import write_json_atomic


RESEARCH_SYSTEM_AUDIT_SCHEMA = 3
REQUIRED_RANKING_SCHEMA = "paper-guided-evidence-ranking-v1"
REQUIRED_DAILY_SCHEDULE = "30 22,10 * * *"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def audit_research_system(
    *,
    snapshot: dict[str, Any],
    model_selection: dict[str, Any],
    bottlenecks: dict[str, Any],
    final_holdout: dict[str, Any],
    certified_robots: dict[str, Any],
    challenger_roster: dict[str, Any],
    competition_tournament: dict[str, Any],
    expected_universe: tuple[str, ...] = SCANNER_UNIVERSE,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    universe = tuple(str(value) for value in snapshot.get("universe") or [])
    automation = snapshot.get("automation") or {}
    training_memory = snapshot.get("training_memory") or {}
    ranking_methodology = snapshot.get("ranking_methodology") or {}

    check(
        "complete_universe",
        universe == expected_universe
        and int(snapshot.get("completed_symbol_count", 0) or 0) == len(expected_universe),
        f"expected={len(expected_universe)} completed={snapshot.get('completed_symbol_count')}",
    )
    check(
        "autonomous_scheduler_registered",
        automation.get("enabled") is True
        and automation.get("mode") == "daily_unattended"
        and automation.get("schedule") == REQUIRED_DAILY_SCHEDULE
        and automation.get("schedule_timezone") == "Asia/Taipei"
        and int(automation.get("sessions_per_day", 0) or 0) == 2
        and automation.get("manual_action_required") is False,
        (
            f"schedule={automation.get('schedule')} "
            f"tz={automation.get('schedule_timezone')} "
            f"sessions={automation.get('sessions_per_day')}"
        ),
    )
    check(
        "aggregate_integrity_pass",
        snapshot.get("integrity_status") == "PASS",
        f"integrity_status={snapshot.get('integrity_status')}",
    )
    check(
        "train_only_memory",
        training_memory.get("provenance") == "TRAIN_ONLY"
        and training_memory.get("validation_feedback_used") is False
        and training_memory.get("holdout_feedback_used") is False,
        "adaptive memory must be TRAIN_ONLY with validation/holdout feedback disabled",
    )
    check(
        "canonical_train_identity_verified",
        int(training_memory.get("verified_data_identity_symbol_count", 0) or 0)
        == len(expected_universe),
        (
            "verified="
            f"{training_memory.get('verified_data_identity_symbol_count')}/{len(expected_universe)}"
        ),
    )
    check(
        "final_holdout_not_leaked",
        snapshot.get("holdout_opened") is False,
        "daily adaptive snapshot must never open Final Holdout itself",
    )
    check(
        "paper_guided_ranking_registered",
        ranking_methodology.get("schema") == REQUIRED_RANKING_SCHEMA
        and ranking_methodology.get("production_champion_rule") == "one_shot_holdout_required"
        and ranking_methodology.get("small_sample_win_rate_role") == "supporting_tiebreaker_only",
        f"ranking_schema={ranking_methodology.get('schema')}",
    )
    check(
        "model_selection_diagnostics_complete",
        int(model_selection.get("symbol_count", 0) or 0) == len(expected_universe),
        f"model_selection_symbols={model_selection.get('symbol_count')}",
    )
    check(
        "bottleneck_observer_complete",
        int(bottlenecks.get("symbol_count", 0) or 0) == len(expected_universe)
        and str(bottlenecks.get("feedback_policy") or "").startswith("OBSERVATION_ONLY"),
        (
            f"bottleneck_symbols={bottlenecks.get('symbol_count')} "
            f"policy={bottlenecks.get('feedback_policy')}"
        ),
    )

    final_policy = final_holdout.get("policy") or {}
    check(
        "one_shot_final_holdout_registered",
        final_policy.get("one_shot") is True
        and final_policy.get("durable_reservation_before_open") is True
        and final_policy.get("open_only_after_all_promotion_gates_pass") is True
        and final_policy.get("holdout_feedback_to_train") is False
        and final_policy.get("overwrite_existing_ledger") is False,
        (
            "final holdout must be durably reserved before read, one-shot, "
            "promotion-gated, immutable, and feedback-isolated"
        ),
    )
    blocked = int(final_holdout.get("blocked_reservation_count", 0) or 0)
    check(
        "no_ambiguous_holdout_reservations_in_run",
        blocked == 0,
        f"blocked_reservations={blocked}",
    )
    evaluated = int(final_holdout.get("newly_opened_count", 0) or 0) + int(
        final_holdout.get("already_evaluated_count", 0) or 0
    )
    eligible = int(final_holdout.get("eligible_candidate_count", 0) or 0)
    check(
        "all_eligible_candidates_accounted_for",
        evaluated == eligible,
        f"eligible={eligible} accounted_for={evaluated}",
    )

    unresolved = int(certified_robots.get("unresolved_reservation_count", 0) or 0)
    check(
        "no_unresolved_global_holdout_reservations",
        unresolved == 0,
        f"unresolved_reservations={unresolved}",
    )
    robots = certified_robots.get("robots") or []
    certified_count = int(certified_robots.get("certified_robot_count", 0) or 0)
    check(
        "certified_registry_consistent",
        isinstance(robots, list)
        and certified_count == len(robots)
        and all(
            isinstance(robot, dict)
            and robot.get("status") == "CERTIFIED_FINAL_HOLDOUT_PASS"
            for robot in robots
        ),
        f"certified_count={certified_count} registry_rows={len(robots) if isinstance(robots, list) else 'invalid'}",
    )

    challenger_policy = challenger_roster.get("policy") or {}
    challengers = challenger_roster.get("challengers") or []
    challenger_count = int(challenger_roster.get("challenger_count", -1) or 0)
    check(
        "certified_competition_bridge_registered",
        challenger_roster.get("schema_version") == 1
        and isinstance(challengers, list)
        and challenger_count == certified_count == len(challengers)
        and challenger_policy.get("certified_final_holdout_required") is True
        and challenger_policy.get("immutable_rule_fingerprint_required") is True
        and challenger_policy.get("competition_rebinds_capital_cost_risk_and_universe") is True
        and challenger_policy.get("holdout_score_used_for_ranking") is False
        and challenger_policy.get("same_campaign_competition_feedback_to_train") is False,
        f"certified={certified_count} challengers={challenger_count}",
    )

    tournament_status = competition_tournament.get("status")
    tournament_challenger_count = int(
        competition_tournament.get("challenger_count", -1) or 0
    )
    promotion = competition_tournament.get("promotion") or {}
    tournament_valid = (
        tournament_challenger_count == challenger_count
        and promotion.get("competition_feedback_to_same_campaign_train") is False
        if challenger_count > 0
        else (
            tournament_status == "WAITING_FOR_CERTIFIED_ROBOT"
            and tournament_challenger_count == 0
            and promotion.get("challenger_replaced_incumbent") is False
        )
    )
    if challenger_count > 0:
        tournament_valid = tournament_valid and tournament_status == "completed"
    check(
        "certified_challenger_tournament_closed_loop",
        tournament_valid,
        (
            f"status={tournament_status} challengers={tournament_challenger_count} "
            f"feedback_to_train={promotion.get('competition_feedback_to_same_campaign_train')}"
        ),
    )

    failed = [row for row in checks if not row["passed"]]
    system_ready = not failed
    return {
        "schema_version": RESEARCH_SYSTEM_AUDIT_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "system_status": "OPERATIONAL" if system_ready else "FAIL_CLOSED",
        "system_ready": system_ready,
        "research_engine_complete": system_ready,
        "competition_research_loop_complete": system_ready,
        "certified_robot_count": certified_count,
        "competition_challenger_count": challenger_count,
        "champion_discovery_status": (
            "CERTIFIED_ROBOT_AVAILABLE" if certified_count else "SEARCH_CONTINUES"
        ),
        "completion_semantics": (
            "research_engine_complete means the autonomous Train-to-Final-Holdout lifecycle, "
            "certified challenger bridge, and competition feedback isolation are wired and "
            "integrity checks pass; it does not assert that a strategy has passed Final Holdout."
        ),
        "passed_check_count": len(checks) - len(failed),
        "failed_check_count": len(failed),
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail-closed audit of the full autonomous research lifecycle"
    )
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--model-selection", type=Path, required=True)
    parser.add_argument("--bottlenecks", type=Path, required=True)
    parser.add_argument("--final-holdout", type=Path, required=True)
    parser.add_argument("--certified-robots", type=Path, required=True)
    parser.add_argument("--challenger-roster", type=Path, required=True)
    parser.add_argument("--competition-tournament", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = audit_research_system(
        snapshot=_load(args.snapshot),
        model_selection=_load(args.model_selection),
        bottlenecks=_load(args.bottlenecks),
        final_holdout=_load(args.final_holdout),
        certified_robots=_load(args.certified_robots),
        challenger_roster=_load(args.challenger_roster),
        competition_tournament=_load(args.competition_tournament),
    )
    write_json_atomic(args.output, audit)
    print(json.dumps(audit, ensure_ascii=False))
    if not audit["system_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
