from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.research_lab.final_holdout import (
    FINAL_HOLDOUT_SCHEMA_VERSION,
    FINAL_HOLDOUT_STATE_EVALUATED,
    FINAL_HOLDOUT_STATE_RESERVED,
    evaluate_reserved_final_holdout,
    ledger_path_for,
    load_existing_ledger,
    reserve_final_holdout,
)
from scripts.run_daily_autoresearch import write_json_atomic


def _load_payloads(input_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(input_dir.glob("*.json"))
    ]


def _eligible_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        payload
        for payload in payloads
        if ((payload.get("result") or {}).get("promotion_eligibility") or {}).get(
            "eligible_for_one_shot_holdout"
        )
    ]


def reserve_final_holdouts(
    payloads: list[dict[str, Any]],
    *,
    ledger_root: Path,
    claim_run_id: str,
) -> dict[str, Any]:
    """Write reservations only; this phase never reads Final Holdout data."""
    rows: list[dict[str, Any]] = []
    new_count = 0
    owned_count = 0
    already_evaluated = 0
    blocked_count = 0
    eligible_payloads = _eligible_payloads(payloads)

    for payload in eligible_payloads:
        result = payload.get("result") or {}
        path = ledger_path_for(payload, ledger_root)
        existing = load_existing_ledger(path, payload)
        if existing is None:
            record = reserve_final_holdout(payload, claim_run_id=claim_run_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(path, record)
            status = "NEW_RESERVATION"
            new_count += 1
        elif existing.get("state") == FINAL_HOLDOUT_STATE_EVALUATED:
            record = existing
            status = "ALREADY_EVALUATED"
            already_evaluated += 1
        elif existing.get("state") == FINAL_HOLDOUT_STATE_RESERVED:
            record = existing
            if existing.get("reservation_claim_run_id") == claim_run_id:
                status = "ALREADY_RESERVED_THIS_RUN"
                owned_count += 1
            else:
                status = "FOREIGN_RESERVATION_BLOCKED"
                blocked_count += 1
        else:  # load_existing_ledger already validates this; defensive fail-closed.
            raise ValueError("Unsupported final holdout ledger state")
        rows.append(
            {
                "stock_code": payload.get("stock_code"),
                "candidate_id": (result.get("selected_candidate") or {}).get(
                    "candidate_id"
                ),
                "evaluation_id": record.get("evaluation_id"),
                "ledger_status": status,
                "ledger_state": record.get("state"),
                "ledger_path": str(path),
            }
        )

    return {
        "schema_version": 2,
        "phase": "RESERVE_BEFORE_OPEN",
        "policy": {
            "one_shot": True,
            "durable_reservation_before_open": True,
            "open_only_after_all_promotion_gates_pass": True,
            "holdout_feedback_to_train": False,
            "overwrite_existing_ledger": False,
            "foreign_reservation_recovery": "FAIL_CLOSED_REQUIRES_AUDIT",
        },
        "claim_run_id": claim_run_id,
        "eligible_candidate_count": len(eligible_payloads),
        "new_reservation_count": new_count,
        "owned_existing_reservation_count": owned_count,
        "already_evaluated_count": already_evaluated,
        "blocked_reservation_count": blocked_count,
        "holdout_opened_in_this_phase": 0,
        "rows": rows,
    }


def evaluate_reserved_final_holdouts(
    payloads: list[dict[str, Any]],
    *,
    ledger_root: Path,
    claim_run_id: str,
) -> dict[str, Any]:
    """Open only reservations owned by this run; foreign reservations stay shut."""
    rows: list[dict[str, Any]] = []
    newly_opened = 0
    already_evaluated = 0
    blocked_count = 0
    pass_count = 0
    fail_count = 0
    eligible_payloads = _eligible_payloads(payloads)

    for payload in eligible_payloads:
        result = payload.get("result") or {}
        path = ledger_path_for(payload, ledger_root)
        existing = load_existing_ledger(path, payload)
        if existing is None:
            raise ValueError(
                "Final holdout reservation is missing; refusing to open unreserved data"
            )
        if existing.get("state") == FINAL_HOLDOUT_STATE_EVALUATED:
            record = existing
            status = "ALREADY_EVALUATED"
            already_evaluated += 1
        elif existing.get("state") == FINAL_HOLDOUT_STATE_RESERVED:
            if existing.get("reservation_claim_run_id") != claim_run_id:
                record = existing
                status = "FOREIGN_RESERVATION_BLOCKED"
                blocked_count += 1
            else:
                record = evaluate_reserved_final_holdout(
                    payload,
                    existing,
                    claim_run_id=claim_run_id,
                )
                write_json_atomic(path, record)
                status = "OPENED_ONCE"
                newly_opened += 1
        else:
            raise ValueError("Unsupported final holdout ledger state")

        final_result = record.get("result") or {}
        if final_result.get("passed") is True:
            pass_count += 1
        elif final_result.get("passed") is False:
            fail_count += 1
        rows.append(
            {
                "stock_code": payload.get("stock_code"),
                "candidate_id": (result.get("selected_candidate") or {}).get(
                    "candidate_id"
                ),
                "evaluation_id": record.get("evaluation_id"),
                "ledger_status": status,
                "ledger_state": record.get("state"),
                "final_status": final_result.get("status"),
                "passed": final_result.get("passed"),
                "ledger_path": str(path),
            }
        )

    return {
        "schema_version": 2,
        "phase": "EVALUATE_RESERVED_ONCE",
        "policy": {
            "one_shot": True,
            "durable_reservation_before_open": True,
            "open_only_after_all_promotion_gates_pass": True,
            "holdout_feedback_to_train": False,
            "overwrite_existing_ledger": False,
            "foreign_reservation_recovery": "FAIL_CLOSED_REQUIRES_AUDIT",
        },
        "claim_run_id": claim_run_id,
        "eligible_candidate_count": len(eligible_payloads),
        "newly_opened_count": newly_opened,
        "already_evaluated_count": already_evaluated,
        "blocked_reservation_count": blocked_count,
        "final_pass_count": pass_count,
        "final_fail_count": fail_count,
        "rows": rows,
    }


def build_certified_registry(ledger_root: Path) -> dict[str, Any]:
    """Build an immutable-evidence roster from every passed holdout ledger.

    Reserved-but-not-opened ledgers are intentionally ignored. Holdout performance
    is not used to rank certified robots, because that would convert the final
    exam into another optimization dataset.
    """
    certified: list[dict[str, Any]] = []
    reserved_count = 0
    if ledger_root.is_dir():
        for path in sorted(ledger_root.rglob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError(f"Malformed final holdout ledger: {path}")
            if record.get("schema_version") != FINAL_HOLDOUT_SCHEMA_VERSION:
                raise ValueError(f"Unsupported final holdout ledger schema: {path}")
            if record.get("state") == FINAL_HOLDOUT_STATE_RESERVED:
                if record.get("opened_once") is not False:
                    raise ValueError(
                        f"Reserved final holdout ledger is incorrectly opened: {path}"
                    )
                reserved_count += 1
                continue
            if record.get("state") != FINAL_HOLDOUT_STATE_EVALUATED:
                raise ValueError(f"Unsupported final holdout ledger state: {path}")
            if record.get("opened_once") is not True:
                raise ValueError(f"Final holdout ledger is not one-shot: {path}")
            result = record.get("result") or {}
            if result.get("passed") is not True:
                continue
            identity = record.get("identity") or {}
            candidate = result.get("candidate") or {}
            certified.append(
                {
                    "certification_id": record.get("evaluation_id"),
                    "campaign_id": identity.get("campaign_id"),
                    "stock_code": identity.get("stock_code"),
                    "candidate_id": identity.get("candidate_id"),
                    "strategy_family": identity.get("strategy_family"),
                    "parameters": identity.get("parameters") or {},
                    "holdout_window": identity.get("holdout_window") or [],
                    "opened_at_utc": record.get("opened_at_utc"),
                    "pre_holdout_research_run_id": record.get(
                        "pre_holdout_research_run_id"
                    ),
                    "candidate": candidate,
                    "status": "CERTIFIED_FINAL_HOLDOUT_PASS",
                }
            )

    certified.sort(
        key=lambda item: (
            str(item.get("campaign_id") or ""),
            str(item.get("stock_code") or ""),
            str(item.get("candidate_id") or ""),
        )
    )
    return {
        "schema_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certified_robot_count": len(certified),
        "unresolved_reservation_count": reserved_count,
        "selection_policy": (
            "Certification is binary after the pre-registered one-shot Final Holdout. "
            "Holdout scores are not used to rank or optimize certified robots."
        ),
        "competition_bridge_policy": (
            "Only CERTIFIED_FINAL_HOLDOUT_PASS specifications may be offered to a "
            "future competition adapter; competition outcomes must never feed back "
            "into the completed campaign's Train search."
        ),
        "robots": certified,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reserve then open final holdout once for fully promoted candidates"
    )
    parser.add_argument("--phase", choices=("reserve", "evaluate"), required=True)
    parser.add_argument("--claim-run-id", required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--certified-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payloads = _load_payloads(args.input_dir)
    if args.phase == "reserve":
        summary = reserve_final_holdouts(
            payloads,
            ledger_root=args.ledger_root,
            claim_run_id=args.claim_run_id,
        )
    else:
        summary = evaluate_reserved_final_holdouts(
            payloads,
            ledger_root=args.ledger_root,
            claim_run_id=args.claim_run_id,
        )
    write_json_atomic(args.summary_output, summary)

    registry = None
    if args.certified_output is not None:
        registry = build_certified_registry(args.ledger_root)
        write_json_atomic(args.certified_output, registry)

    print(
        json.dumps(
            {
                **summary,
                "certified_robot_count": (
                    registry.get("certified_robot_count") if registry else None
                ),
            },
            ensure_ascii=False,
        )
    )

    if int(summary.get("blocked_reservation_count", 0) or 0) > 0:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
