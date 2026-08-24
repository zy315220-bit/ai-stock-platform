from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from typing import Any, Iterable

from .evolution import (
    SEARCH_SPACE_SCHEMA,
    candidate_parameter_signature,
    evolve_candidates,
)
from .models import ExperimentDecision, ExperimentResult, ResearchCandidate


TRAINING_MEMORY_SCHEMA_VERSION = 1
TRAIN_DATA_IDENTITY_SCHEMA = "canonical-train-score-series-v1"
MAX_ELITES = 12
MAX_FRONTIER = 96
MAX_SEEN_SIGNATURES = 10_000


@dataclass(frozen=True)
class DailyCandidatePlan:
    candidates: tuple[ResearchCandidate, ...]
    excluded_parameter_signatures: frozenset[str]
    prior_train_trial_sharpes: tuple[float, ...]
    audit: dict[str, Any]


def _candidate_from_payload(payload: Any) -> ResearchCandidate | None:
    if not isinstance(payload, dict):
        return None
    candidate_id = str(payload.get("candidate_id") or "").strip()
    strategy_family = str(payload.get("strategy_family") or "").strip()
    parameters = payload.get("parameters")
    if not candidate_id or not strategy_family or not isinstance(parameters, dict):
        return None
    return ResearchCandidate(
        candidate_id=candidate_id,
        strategy_family=strategy_family,
        parameters=dict(parameters),
        parent_id=(
            str(payload["parent_id"])
            if payload.get("parent_id") is not None
            else None
        ),
        hypothesis=str(payload.get("hypothesis") or ""),
    )


def _elite_result(payload: Any) -> ExperimentResult | None:
    if not isinstance(payload, dict):
        return None
    candidate = _candidate_from_payload(payload.get("candidate"))
    if candidate is None:
        return None
    try:
        decision = ExperimentDecision(str(payload.get("decision")))
        score = float(payload.get("research_score", 0.0))
    except (TypeError, ValueError):
        return None
    return ExperimentResult(
        candidate=candidate,
        validation_metrics={},
        decision=decision,
        research_score=score,
        reasons=tuple(str(item) for item in payload.get("reasons") or []),
        evaluation_phase="train",
    )


def _memory_compatibility(
    memory: Any,
    *,
    stock_code: str,
    campaign_id: str,
    train_window: tuple[str, str],
    train_data_identity: str,
) -> tuple[dict[str, Any] | None, str | None]:
    normalized_identity = str(train_data_identity or "").strip()
    if not normalized_identity:
        raise ValueError("Canonical train data identity is required")
    if not isinstance(memory, dict):
        return None, "missing"
    checks = (
        (memory.get("schema_version") == TRAINING_MEMORY_SCHEMA_VERSION, "schema_changed"),
        (memory.get("search_space_schema") == SEARCH_SPACE_SCHEMA, "search_space_changed"),
        (memory.get("provenance") == "TRAIN_ONLY", "unsafe_provenance"),
        (str(memory.get("stock_code") or "").upper() == stock_code.upper(), "stock_changed"),
        (memory.get("campaign_id") == campaign_id, "campaign_changed"),
        (list(memory.get("train_window") or []) == list(train_window), "train_window_changed"),
        (memory.get("validation_feedback_used") is False, "validation_feedback_detected"),
        (memory.get("holdout_feedback_used") is False, "holdout_feedback_detected"),
    )
    for safe, reason in checks:
        if not safe:
            return None, reason
    prior_identity = str(memory.get("train_data_identity") or "").strip()
    if prior_identity:
        if (
            memory.get("train_data_identity_schema")
            != TRAIN_DATA_IDENTITY_SCHEMA
        ):
            return None, "train_data_identity_schema_changed"
        if prior_identity != normalized_identity:
            return None, "train_data_revision"
    return memory, None


def _unique_candidates(
    candidates: Iterable[ResearchCandidate],
    *,
    excluded: set[str],
) -> list[ResearchCandidate]:
    selected: list[ResearchCandidate] = []
    local_seen: set[str] = set()
    for candidate in candidates:
        signature = candidate_parameter_signature(candidate)
        if signature in excluded or signature in local_seen:
            continue
        local_seen.add(signature)
        selected.append(candidate)
    return selected


def prepare_daily_candidate_plan(
    *,
    stock_code: str,
    campaign_id: str,
    train_window: tuple[str, str],
    train_data_identity: str,
    rotated_grid: Iterable[ResearchCandidate],
    prior_memory: dict[str, Any] | None,
) -> DailyCandidatePlan:
    """Build a novel train-only seed queue without validation feedback."""
    compatible, reset_reason = _memory_compatibility(
        prior_memory,
        stock_code=stock_code,
        campaign_id=campaign_id,
        train_window=train_window,
        train_data_identity=train_data_identity,
    )
    prior_identity = str(
        (compatible or {}).get("train_data_identity") or ""
    ).strip()
    identity_migrated = bool(compatible and not prior_identity)
    identity_verified = bool(
        compatible and prior_identity == str(train_data_identity).strip()
    )
    seen = {
        str(signature)
        for signature in (compatible or {}).get("seen_parameter_signatures", [])
    }
    frontier = _unique_candidates(
        (
            candidate
            for item in (compatible or {}).get("frontier", [])
            if (candidate := _candidate_from_payload(item)) is not None
        ),
        excluded=seen,
    )
    elite_results = [
        result
        for item in (compatible or {}).get("elites", [])
        if (result := _elite_result(item)) is not None
    ]
    elite_children = _unique_candidates(
        evolve_candidates(elite_results, top_k=3),
        excluded=seen,
    )
    novel_grid = _unique_candidates(rotated_grid, excluded=seen)

    queues = [
        ("frontier", frontier),
        ("elite_mutation", elite_children),
        ("novel_grid", novel_grid),
    ]
    planned: list[ResearchCandidate] = []
    planned_signatures: set[str] = set()
    seed_source_counts = {name: 0 for name, _ in queues}
    while any(queue for _, queue in queues):
        for name, queue in queues:
            if not queue:
                continue
            candidate = queue.pop(0)
            signature = candidate_parameter_signature(candidate)
            if signature in planned_signatures:
                continue
            planned_signatures.add(signature)
            planned.append(candidate)
            seed_source_counts[name] += 1

    audit = {
        "enabled": True,
        "schema_version": TRAINING_MEMORY_SCHEMA_VERSION,
        "search_space_schema": SEARCH_SPACE_SCHEMA,
        "prior_memory_loaded": compatible is not None,
        "prior_memory_id": (compatible or {}).get("memory_id"),
        "memory_reset_reason": reset_reason,
        "train_data_identity_schema": TRAIN_DATA_IDENTITY_SCHEMA,
        "train_data_identity": str(train_data_identity).strip(),
        "train_data_identity_verified": identity_verified,
        "train_data_identity_migrated": identity_migrated,
        "prior_seen_signature_count": len(seen),
        "prior_elite_count": len(elite_results),
        "prior_frontier_count": len(frontier),
        "prior_train_trial_count": len(
            (compatible or {}).get("train_trial_period_sharpes", [])
        ),
        "planned_candidate_count": len(planned),
        "seed_source_counts": seed_source_counts,
        "validation_feedback_used": False,
        "holdout_feedback_used": False,
    }
    return DailyCandidatePlan(
        candidates=tuple(planned),
        excluded_parameter_signatures=frozenset(seen),
        prior_train_trial_sharpes=tuple(
            float(value)
            for value in (compatible or {}).get(
                "train_trial_period_sharpes",
                [],
            )
            if isinstance(value, (int, float)) and math.isfinite(float(value))
        ),
        audit=audit,
    )


def _training_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for round_payload in result.get("rounds") or []:
        if round_payload.get("evaluation_phase") != "train":
            raise RuntimeError("Training memory refused non-train round evidence")
        generation = int(round_payload.get("generation", 0) or 0)
        for serialized in round_payload.get("evaluated") or []:
            if serialized.get("evaluation_phase") != "train":
                raise RuntimeError(
                    "Training memory refused validation or holdout evidence"
                )
            candidate = _candidate_from_payload(serialized.get("candidate"))
            if candidate is None:
                continue
            try:
                decision = ExperimentDecision(str(serialized.get("decision")))
                score = float(serialized.get("research_score", 0.0))
            except (TypeError, ValueError):
                continue
            metrics = serialized.get("validation_metrics") or {}
            statistics = metrics.get("statistical_evidence") or {}
            period_sharpe = statistics.get("period_sharpe_ratio")
            records.append(
                {
                    "candidate": asdict(candidate),
                    "parameter_signature": candidate_parameter_signature(candidate),
                    "research_score": score,
                    "decision": decision.value,
                    "reasons": [str(item) for item in serialized.get("reasons") or []],
                    "generation": generation,
                    "data_fingerprint": metrics.get("data_fingerprint"),
                    "train_period_sharpe": (
                        float(period_sharpe)
                        if isinstance(period_sharpe, (int, float))
                        and math.isfinite(float(period_sharpe))
                        else None
                    ),
                }
            )
    return records


def _frontier_candidates(result: dict[str, Any]) -> list[ResearchCandidate]:
    rounds = list(result.get("rounds") or [])
    if not rounds:
        return []
    return [
        candidate
        for item in rounds[-1].get("survivors") or []
        if (candidate := _candidate_from_payload(item)) is not None
    ]


def build_training_memory(
    *,
    stock_code: str,
    campaign_id: str,
    train_window: tuple[str, str],
    train_data_identity: str,
    as_of_date: str,
    result: dict[str, Any],
    prior_memory: dict[str, Any] | None,
) -> dict[str, Any]:
    """Persist only train-derived evidence for the next unattended run."""
    audit = result.get("research_audit") or {}
    if audit.get("validation_used_during_adaptive_search") is not False:
        raise RuntimeError("Training memory refused validation feedback")
    if audit.get("holdout_used_during_search") is not False:
        raise RuntimeError("Training memory refused holdout feedback")

    compatible, compatibility_reason = _memory_compatibility(
        prior_memory,
        stock_code=stock_code,
        campaign_id=campaign_id,
        train_window=train_window,
        train_data_identity=train_data_identity,
    )
    records = _training_records(result)
    current_fingerprints = sorted(
        {
            str(record["data_fingerprint"])
            for record in records
            if record.get("data_fingerprint")
        }
    )
    prior_fingerprints = sorted(
        str(item)
        for item in (compatible or {}).get("train_data_fingerprints", [])
    )
    prior_identity = str(
        (compatible or {}).get("train_data_identity") or ""
    ).strip()
    identity_migrated = bool(compatible and not prior_identity)
    identity_verified = bool(
        compatible and prior_identity == str(train_data_identity).strip()
    )

    prior_seen = {
        str(item)
        for item in (compatible or {}).get("seen_parameter_signatures", [])
    }
    current_seen = {
        str(record["parameter_signature"]) for record in records
    }
    merged_seen = sorted(prior_seen | current_seen)[-MAX_SEEN_SIGNATURES:]

    elite_by_signature: dict[str, dict[str, Any]] = {}
    for item in (compatible or {}).get("elites", []):
        if isinstance(item, dict) and item.get("parameter_signature"):
            elite_by_signature[str(item["parameter_signature"])] = dict(item)
    source_run_id = result.get("research_run_id")
    for record in records:
        if record["decision"] == ExperimentDecision.DISCARD.value:
            continue
        signature = str(record["parameter_signature"])
        elite = {
            "candidate": record["candidate"],
            "parameter_signature": signature,
            "research_score": record["research_score"],
            "decision": record["decision"],
            "reasons": record["reasons"],
            "source_generation": record["generation"],
            "source_research_run_id": source_run_id,
        }
        existing = elite_by_signature.get(signature)
        if existing is None or float(elite["research_score"]) > float(
            existing.get("research_score", 0.0)
        ):
            elite_by_signature[signature] = elite
    elites = sorted(
        elite_by_signature.values(),
        key=lambda item: float(item.get("research_score", 0.0)),
        reverse=True,
    )[:MAX_ELITES]

    frontier_sources: list[ResearchCandidate] = []
    for item in (compatible or {}).get("frontier", []):
        candidate = _candidate_from_payload(item)
        if candidate is not None:
            frontier_sources.append(candidate)
    frontier_sources.extend(_frontier_candidates(result))
    frontier = [
        asdict(candidate)
        for candidate in _unique_candidates(
            frontier_sources,
            excluded=set(merged_seen),
        )[:MAX_FRONTIER]
    ]

    previous_experiments = int(
        (compatible or {}).get("lifetime_experiment_count", 0) or 0
    )
    previous_runs = int((compatible or {}).get("lifetime_run_count", 0) or 0)
    strategy_families = sorted(
        {
            str(item)
            for item in (compatible or {}).get("strategy_families", [])
            if item
        }
        | {
            str((record.get("candidate") or {}).get("strategy_family"))
            for record in records
            if (record.get("candidate") or {}).get("strategy_family")
        }
    )
    train_trial_period_sharpes = [
        float(value)
        for value in (compatible or {}).get(
            "train_trial_period_sharpes",
            [],
        )
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    train_trial_period_sharpes.extend(
        float(record["train_period_sharpe"])
        for record in records
        if record.get("train_period_sharpe") is not None
    )
    train_trial_period_sharpes = train_trial_period_sharpes[
        -MAX_SEEN_SIGNATURES:
    ]
    memory = {
        "schema_version": TRAINING_MEMORY_SCHEMA_VERSION,
        "search_space_schema": SEARCH_SPACE_SCHEMA,
        "provenance": "TRAIN_ONLY",
        "stock_code": stock_code.strip().upper(),
        "campaign_id": campaign_id,
        "train_window": list(train_window),
        "as_of_date": as_of_date,
        "last_research_run_id": source_run_id,
        "train_data_identity_schema": TRAIN_DATA_IDENTITY_SCHEMA,
        "train_data_identity": str(train_data_identity).strip(),
        "train_data_identity_verified": identity_verified,
        "train_data_identity_migrated": identity_migrated,
        "train_data_fingerprints": current_fingerprints or prior_fingerprints,
        "seen_parameter_signatures": merged_seen,
        "elites": elites,
        "frontier": frontier,
        "strategy_families": strategy_families,
        "train_trial_period_sharpes": train_trial_period_sharpes,
        "lifetime_experiment_count": previous_experiments + len(records),
        "lifetime_run_count": previous_runs + 1,
        "last_run_new_experiment_count": len(records),
        "last_run_duplicate_skip_count": int(
            result.get("skipped_duplicate_count", 0) or 0
        ),
        "memory_reset_reason": compatibility_reason,
        "validation_feedback_used": False,
        "holdout_feedback_used": False,
    }
    identity_payload = json.dumps(
        {
            "stock_code": memory["stock_code"],
            "campaign_id": campaign_id,
            "train_window": memory["train_window"],
            "train_data_identity_schema": memory[
                "train_data_identity_schema"
            ],
            "train_data_identity": memory["train_data_identity"],
            "train_data_fingerprints": memory["train_data_fingerprints"],
            "seen_parameter_signatures": memory["seen_parameter_signatures"],
            "elites": memory["elites"],
            "frontier": memory["frontier"],
            "strategy_families": memory["strategy_families"],
            "train_trial_period_sharpes": memory[
                "train_trial_period_sharpes"
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    memory["memory_id"] = sha256(
        identity_payload.encode("utf-8")
    ).hexdigest()[:24]
    return memory


def training_memory_summary(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": memory.get("memory_id"),
        "search_space_schema": memory.get("search_space_schema"),
        "train_data_identity_schema": memory.get(
            "train_data_identity_schema"
        ),
        "train_data_identity": memory.get("train_data_identity"),
        "train_data_identity_verified": bool(
            memory.get("train_data_identity_verified")
        ),
        "train_data_identity_migrated": bool(
            memory.get("train_data_identity_migrated")
        ),
        "prior_memory_continued": memory.get("memory_reset_reason") is None,
        "unique_experiment_count": len(
            memory.get("seen_parameter_signatures") or []
        ),
        "elite_count": len(memory.get("elites") or []),
        "frontier_count": len(memory.get("frontier") or []),
        "strategy_family_count": len(
            memory.get("strategy_families") or []
        ),
        "strategy_families": list(
            memory.get("strategy_families") or []
        ),
        "train_trial_count": len(
            memory.get("train_trial_period_sharpes") or []
        ),
        "lifetime_experiment_count": int(
            memory.get("lifetime_experiment_count", 0) or 0
        ),
        "lifetime_run_count": int(memory.get("lifetime_run_count", 0) or 0),
        "last_run_new_experiment_count": int(
            memory.get("last_run_new_experiment_count", 0) or 0
        ),
        "last_run_duplicate_skip_count": int(
            memory.get("last_run_duplicate_skip_count", 0) or 0
        ),
        "validation_feedback_used": False,
        "holdout_feedback_used": False,
    }
