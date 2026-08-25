from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.scanner_service import SCANNER_UNIVERSE
from scripts.run_daily_autoresearch import write_json_atomic


RESEARCH_SYSTEM_AUDIT_SCHEMA = 1
REQUIRED_RANKING_SCHEMA = "paper-guided-evidence-ranking-v1"


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
    expected_universe: tuple[str, ...] = SCANNER_UNIVERSE,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    universe = tuple(str(value) for value in snapshot.get("universe") or [])
    training_memory = snapshot.get("training_memory") or {}
    ranking_methodology = snapshot.get("ranking_methodology") or {}

    check(
        "complete_universe",
        universe == expected_universe
        and int(snapshot.get("completed_symbol_count", 0) or 0) == len(expected_universe),
        f"expected={len(expected_universe)} completed={snapshot.get('completed_symbol_count')}",
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
        and final_policy.get("open_only_after_all_promotion_gates_pass") is True
        and final_policy.get("holdout_feedback_to_train") is False
        and final_policy.get("overwrite_existing_ledger") is False,
        "final holdout must be one-shot, promotion-gated, immutable, and feedback-isolated",
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

    failed = [row for row in checks if not row["passed"]]
    certified_count = int(final_holdout.get("final_pass_count", 0) or 0)
    system_ready = not failed
    return {
        "schema_version": RESEARCH_SYSTEM_AUDIT_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "system_status": "OPERATIONAL" if system_ready else "FAIL_CLOSED",
        "system_ready": system_ready,
        "research_engine_complete": system_ready,
        "certified_robot_count": certified_count,
        "champion_discovery_status": (
            "CERTIFIED_ROBOT_AVAILABLE" if certified_count else "SEARCH_CONTINUES"
        ),
        "completion_semantics": (
            "research_engine_complete means the autonomous research lifecycle is wired "
            "and integrity checks pass; it does not assert that a strategy has passed "
            "the one-shot Final Holdout."
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
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = audit_research_system(
        snapshot=_load(args.snapshot),
        model_selection=_load(args.model_selection),
        bottlenecks=_load(args.bottlenecks),
        final_holdout=_load(args.final_holdout),
    )
    write_json_atomic(args.output, audit)
    print(json.dumps(audit, ensure_ascii=False))
    if not audit["system_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
