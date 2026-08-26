from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from scripts.aggregate_daily_autoresearch import _ranking_key
from scripts.run_daily_autoresearch import write_json_atomic


INCUMBENT_SCHEMA_VERSION = 1


def _candidate_identity(candidate: dict[str, Any] | None) -> str:
    if not isinstance(candidate, dict):
        return ""
    robot_version = str(candidate.get("robot_version_id") or "").strip()
    if robot_version:
        return robot_version
    stock = str(candidate.get("stock_code") or "").strip().upper()
    candidate_id = str(candidate.get("candidate_id") or "").strip()
    return f"{stock}:{candidate_id}" if stock or candidate_id else ""


def _valid_candidate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if not _candidate_identity(value):
        return None
    return deepcopy(value)


def _historical_candidates(
    snapshots: Iterable[dict[str, Any]],
    *,
    campaign_id: str,
) -> list[tuple[str, dict[str, Any]]]:
    candidates: list[tuple[str, dict[str, Any]]] = []
    for snapshot in snapshots:
        if str(snapshot.get("campaign_id") or "") != campaign_id:
            continue
        candidate = _valid_candidate(
            snapshot.get("incumbent_candidate") or snapshot.get("top_candidate")
        )
        if candidate is not None:
            candidates.append(("historical_run", candidate))
    return candidates


def select_research_incumbent(
    snapshot: dict[str, Any],
    *,
    prior_incumbent: dict[str, Any] | None = None,
    historical_snapshots: Iterable[dict[str, Any]] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Preserve the strongest same-campaign exploratory candidate.

    This is an observation-only archive/ranking operation. It never changes
    Train memory, candidate generation, Validation, Promotion Gate, or Final
    Holdout state. Cross-campaign incumbents are intentionally not compared
    because their evaluation windows are not directly interchangeable.
    """
    output = deepcopy(snapshot)
    campaign_id = str(output.get("campaign_id") or "").strip()
    if not campaign_id:
        raise ValueError("snapshot campaign_id is required")

    round_candidate = _valid_candidate(
        output.get("round_top_candidate") or output.get("top_candidate")
    )
    if round_candidate is None:
        raise ValueError("snapshot top_candidate is required")

    pool: list[tuple[str, dict[str, Any]]] = [("current_round", round_candidate)]
    previous: dict[str, Any] | None = None
    if isinstance(prior_incumbent, dict):
        prior_campaign = str(prior_incumbent.get("campaign_id") or "")
        if prior_campaign == campaign_id:
            previous = _valid_candidate(prior_incumbent.get("candidate"))
            if previous is not None:
                pool.append(("prior_incumbent", previous))

    pool.extend(
        _historical_candidates(
            historical_snapshots,
            campaign_id=campaign_id,
        )
    )

    # Deduplicate identical robot versions while keeping the strongest copy.
    by_identity: dict[str, tuple[str, dict[str, Any]]] = {}
    for source, candidate in pool:
        identity = _candidate_identity(candidate)
        existing = by_identity.get(identity)
        if existing is None or _ranking_key(candidate) > _ranking_key(existing[1]):
            by_identity[identity] = (source, candidate)

    source, incumbent = max(
        by_identity.values(),
        key=lambda item: _ranking_key(item[1]),
    )
    incumbent_id = _candidate_identity(incumbent)
    round_id = _candidate_identity(round_candidate)
    previous_id = _candidate_identity(previous)
    incumbent_in_current_round = incumbent_id == round_id

    if previous is None:
        state = "BOOTSTRAPPED"
    elif incumbent_id == previous_id:
        state = "RETAINED"
    else:
        state = "REPLACED"

    output["round_top_candidate"] = round_candidate
    output["incumbent_candidate"] = incumbent
    # Keep backward compatibility: existing UI/API consumers read top_candidate.
    output["top_candidate"] = incumbent
    output["incumbent_status"] = {
        "schema_version": INCUMBENT_SCHEMA_VERSION,
        "state": state,
        "source": source,
        "campaign_id": campaign_id,
        "incumbent_identity": incumbent_id,
        "round_challenger_identity": round_id,
        "previous_incumbent_identity": previous_id or None,
        "round_challenger_replaced_incumbent": bool(
            previous is not None
            and round_id == incumbent_id
            and incumbent_id != previous_id
        ),
        "incumbent_in_current_round": incumbent_in_current_round,
        "requires_current_revalidation": not incumbent_in_current_round,
        "same_campaign_only": True,
        "feeds_train_memory": False,
        "opens_final_holdout": False,
        "ranking_key": "paper_guided_evidence_hierarchy_v1",
    }
    incumbent_record = {
        "schema_version": INCUMBENT_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "candidate": incumbent,
        "source_snapshot_as_of_date": output.get("as_of_date"),
        "selection": output["incumbent_status"],
    }
    return output, incumbent_record


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return load_json(path)


def load_historical_snapshots(runs_root: Path) -> list[dict[str, Any]]:
    if not runs_root.is_dir():
        return []
    snapshots: list[dict[str, Any]] = []
    for path in sorted(runs_root.glob("*/*/latest.json")):
        try:
            snapshots.append(load_json(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return snapshots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preserve the strongest same-campaign research incumbent"
    )
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--incumbent", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = load_json(args.snapshot)
    prior = load_optional_json(args.incumbent)
    historical = load_historical_snapshots(args.runs_root)
    updated, incumbent = select_research_incumbent(
        snapshot,
        prior_incumbent=prior,
        historical_snapshots=historical,
    )
    write_json_atomic(args.snapshot, updated)
    write_json_atomic(args.incumbent, incumbent)
    print(
        json.dumps(
            {
                "campaign_id": incumbent["campaign_id"],
                "incumbent": _candidate_identity(incumbent["candidate"]),
                "state": incumbent["selection"]["state"],
                "source": incumbent["selection"]["source"],
                "round_challenger": incumbent["selection"][
                    "round_challenger_identity"
                ],
                "requires_current_revalidation": incumbent["selection"][
                    "requires_current_revalidation"
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
