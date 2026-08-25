from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.research_lab.final_holdout import (
    FINAL_HOLDOUT_SCHEMA_VERSION,
    evaluate_final_holdout_once,
    ledger_path_for,
    load_existing_ledger,
)
from scripts.run_daily_autoresearch import write_json_atomic


def _load_payloads(input_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(input_dir.glob("*.json"))
    ]


def process_final_holdouts(
    payloads: list[dict[str, Any]],
    *,
    ledger_root: Path,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    newly_opened = 0
    already_evaluated = 0
    pass_count = 0
    fail_count = 0
    eligible_count = 0

    for payload in payloads:
        result = payload.get("result") or {}
        promotion = result.get("promotion_eligibility") or {}
        if not promotion.get("eligible_for_one_shot_holdout"):
            continue
        eligible_count += 1
        path = ledger_path_for(payload, ledger_root)
        existing = load_existing_ledger(path, payload)
        if existing is not None:
            record = existing
            status = "ALREADY_EVALUATED"
            already_evaluated += 1
        else:
            record = evaluate_final_holdout_once(payload)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(path, record)
            status = "OPENED_ONCE"
            newly_opened += 1

        final_result = record.get("result") or {}
        if final_result.get("passed") is True:
            pass_count += 1
        elif final_result.get("passed") is False:
            fail_count += 1
        rows.append(
            {
                "stock_code": payload.get("stock_code"),
                "candidate_id": ((result.get("selected_candidate") or {}).get("candidate_id")),
                "evaluation_id": record.get("evaluation_id"),
                "ledger_status": status,
                "final_status": final_result.get("status"),
                "passed": final_result.get("passed"),
                "ledger_path": str(path),
            }
        )

    return {
        "schema_version": 1,
        "policy": {
            "one_shot": True,
            "open_only_after_all_promotion_gates_pass": True,
            "holdout_feedback_to_train": False,
            "overwrite_existing_ledger": False,
        },
        "eligible_candidate_count": eligible_count,
        "newly_opened_count": newly_opened,
        "already_evaluated_count": already_evaluated,
        "final_pass_count": pass_count,
        "final_fail_count": fail_count,
        "rows": rows,
    }


def build_certified_registry(ledger_root: Path) -> dict[str, Any]:
    """Build an immutable-evidence roster from every passed holdout ledger.

    Holdout performance is deliberately not used to rank certified robots. A
    pass certifies that a pre-selected candidate survived the untouched exam;
    selecting among multiple certified robots based on their holdout scores
    would turn the final exam into another optimization dataset.
    """
    certified: list[dict[str, Any]] = []
    if ledger_root.is_dir():
        for path in sorted(ledger_root.rglob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError(f"Malformed final holdout ledger: {path}")
            if record.get("schema_version") != FINAL_HOLDOUT_SCHEMA_VERSION:
                raise ValueError(f"Unsupported final holdout ledger schema: {path}")
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
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certified_robot_count": len(certified),
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
        description="Open final holdout once for fully promoted research candidates"
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--certified-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = process_final_holdouts(
        _load_payloads(args.input_dir),
        ledger_root=args.ledger_root,
    )
    registry = build_certified_registry(args.ledger_root)
    write_json_atomic(args.summary_output, summary)
    write_json_atomic(args.certified_output, registry)
    print(
        json.dumps(
            {
                **summary,
                "certified_robot_count": registry["certified_robot_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
