from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from scripts.aggregate_daily_autoresearch import (
    _CONFIRMATION_GATE_TOTAL,
    _confirmation_gate_pass_count,
    _ranking_key,
)
from scripts.run_daily_autoresearch import write_json_atomic


INCUMBENT_SCHEMA_VERSION = 1
ALL_TIME_INCUMBENT_SCHEMA_VERSION = 1


def _behavior_signature(candidate: dict[str, Any] | None) -> str:
    if not isinstance(candidate, dict):
        return ""
    behavior = candidate.get("behavior") or {}
    if not isinstance(behavior, dict):
        return ""
    return str(behavior.get("behavior_signature") or "").strip()


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
    candidate = deepcopy(value)
    candidate["gate_reasons"] = [
        reason
        for reason in candidate.get("gate_reasons") or []
        if reason != "hansen_spa_failed_or_unavailable"
    ]
    candidate["confirmation_gate_pass_count"] = (
        _confirmation_gate_pass_count(candidate)
    )
    candidate["confirmation_gate_total"] = _CONFIRMATION_GATE_TOTAL
    model_selection = candidate.get("model_selection")
    if isinstance(model_selection, dict):
        model_selection["hansen_spa_role"] = (
            "SET_LEVEL_DIAGNOSTIC_NOT_INDIVIDUAL_PROMOTION_GATE"
        )
        model_selection["hansen_spa_hard_gate"] = False
    return candidate


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

    incumbent_behavior = _behavior_signature(incumbent)
    round_behavior = _behavior_signature(round_candidate)
    behavioral_near_duplicate = bool(
        incumbent_behavior
        and round_behavior
        and incumbent_behavior == round_behavior
        and incumbent_id != round_id
    )

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
        "behavioral_near_duplicate": behavioral_near_duplicate,
        "behavioral_duplicate_basis": (
            "exact_behavior_signature"
            if behavioral_near_duplicate
            else None
        ),
        "behavioral_duplicate_of": (
            incumbent_id if behavioral_near_duplicate else None
        ),
    }
    incumbent_record = {
        "schema_version": INCUMBENT_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "candidate": incumbent,
        "source_snapshot_as_of_date": output.get("as_of_date"),
        "selection": output["incumbent_status"],
    }
    return output, incumbent_record


def select_all_time_incumbent(
    snapshot: dict[str, Any],
    *,
    prior_all_time_incumbent: dict[str, Any] | None = None,
    historical_snapshots: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Archive the strongest observed evidence without granting current eligibility.

    Campaign windows remain separate for promotion. This record is a permanent,
    observation-only high-water mark; it is never read by search or Holdout.
    """
    pool: list[tuple[str, dict[str, Any]]] = []
    if isinstance(prior_all_time_incumbent, dict):
        candidate = _valid_candidate(prior_all_time_incumbent.get("candidate"))
        if candidate is not None and prior_all_time_incumbent.get("campaign_id"):
            prior = deepcopy(prior_all_time_incumbent)
            prior["candidate"] = candidate
            pool.append(("prior_all_time_incumbent", prior))

    for source, snapshots in (
        ("historical_archive", historical_snapshots),
        ("current_snapshot", (snapshot,)),
    ):
        for observed in snapshots:
            embedded = observed.get("all_time_incumbent")
            if isinstance(embedded, dict) and embedded.get("scope") == "ALL_TIME":
                candidate = _valid_candidate(embedded.get("candidate"))
                if candidate is not None and embedded.get("campaign_id"):
                    recovered = deepcopy(embedded)
                    recovered["candidate"] = candidate
                    pool.append((source, recovered))
            campaign_id = str(observed.get("campaign_id") or "").strip()
            if not campaign_id:
                continue
            values = [
                observed.get("incumbent_candidate"),
                observed.get("top_candidate"),
                observed.get("round_top_candidate"),
                *(observed.get("candidates") or []),
            ]
            for value in values:
                candidate = _valid_candidate(value)
                if candidate is None:
                    continue
                pool.append((source, {
                    "campaign_id": campaign_id,
                    "candidate": candidate,
                    "source_snapshot_as_of_date": observed.get("as_of_date"),
                    "source_generated_at_utc": observed.get("generated_at_utc"),
                }))

    if not pool:
        raise ValueError("no historical candidate evidence is available")
    # Prior evidence wins ties, preserving its original date and provenance.
    source, strongest = max(pool, key=lambda item: _ranking_key(item[1]["candidate"]))
    record = deepcopy(strongest)
    previous = prior_all_time_incumbent
    state = "BOOTSTRAPPED" if previous is None else (
        "RETAINED" if source == "prior_all_time_incumbent" else "REPLACED"
    )
    record["schema_version"] = ALL_TIME_INCUMBENT_SCHEMA_VERSION
    record["scope"] = "ALL_TIME"
    record["selection"] = {
        "state": state,
        "source": source,
        "historical_identity": f"{record['campaign_id']}:{_candidate_identity(record['candidate'])}",
        "ranking_key": "paper_guided_evidence_hierarchy_v1",
        "evidence_scope": "ORIGINAL_CAMPAIGN_ONLY",
        "observation_only": True,
        "grants_current_promotion_eligibility": False,
        "feeds_train_memory": False,
        "opens_final_holdout": False,
    }
    return record


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return load_json(path)


def load_historical_snapshots(
    runs_root: Path,
    history_root: Path | None = None,
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    paths = list(runs_root.glob("*/*/latest.json"))
    if history_root is not None:
        # Daily archives include preserved incumbents missing from raw runs.
        paths.extend(history_root.glob("*.json"))
    for path in sorted(paths):
        try:
            snapshots.append(load_json(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return snapshots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preserve current-campaign and all-time research incumbents"
    )
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--incumbent", type=Path, required=True)
    parser.add_argument("--history-root", type=Path)
    parser.add_argument("--all-time-incumbent", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = load_json(args.snapshot)
    prior = load_optional_json(args.incumbent)
    history_root = args.history_root or args.snapshot.parent / "history"
    all_time_path = args.all_time_incumbent or args.snapshot.parent / "all-time-incumbent.json"
    historical = load_historical_snapshots(args.runs_root, history_root)
    updated, incumbent = select_research_incumbent(
        snapshot,
        prior_incumbent=prior,
        historical_snapshots=historical,
    )
    all_time = select_all_time_incumbent(
        updated,
        prior_all_time_incumbent=load_optional_json(all_time_path),
        historical_snapshots=historical,
    )
    write_json_atomic(all_time_path, all_time)
    updated["all_time_incumbent"] = all_time
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
