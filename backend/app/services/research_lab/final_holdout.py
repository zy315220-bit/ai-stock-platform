from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from app.services.backtest.engine import backtest_stock

from .models import ExperimentDecision, ResearchCandidate
from .runner import _validation_metrics
from .scoring import evaluate_candidate


FINAL_HOLDOUT_SCHEMA_VERSION = 2
FINAL_HOLDOUT_MIN_COMPLETED_TRADES = 4
FINAL_HOLDOUT_MAX_DRAWDOWN_PERCENT = 30.0
FINAL_HOLDOUT_STATE_RESERVED = "RESERVED_BEFORE_OPEN"
FINAL_HOLDOUT_STATE_EVALUATED = "EVALUATED_ONCE"

BacktestFn = Callable[..., dict[str, Any]]


def _canonical_candidate_identity(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    result = payload.get("result") or {}
    selected = result.get("selected_candidate") or {}
    split = result.get("split") or {}
    campaign = payload.get("campaign") or {}
    stock_code = str(payload.get("stock_code") or "").strip().upper()
    candidate_id = str(selected.get("candidate_id") or "").strip()
    holdout_window = split.get("holdout") or []

    if not stock_code or not candidate_id:
        raise ValueError("Final holdout requires one identified stock and candidate")
    if not isinstance(holdout_window, list) or len(holdout_window) != 2:
        raise ValueError("Final holdout window is missing")
    if not holdout_window[0] or not holdout_window[1]:
        raise ValueError("Final holdout window is incomplete")

    identity_payload = {
        "schema": "research-final-holdout-identity-v1",
        "campaign_id": str(campaign.get("campaign_id") or ""),
        "stock_code": stock_code,
        "candidate_id": candidate_id,
        "strategy_family": selected.get("strategy_family"),
        "parameters": selected.get("parameters") or {},
        "holdout_window": list(holdout_window),
    }
    canonical = json.dumps(
        identity_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    evaluation_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return evaluation_id, identity_payload


def ledger_path_for(payload: dict[str, Any], ledger_root: Path) -> Path:
    _, identity = _canonical_candidate_identity(payload)
    campaign_id = str(identity["campaign_id"] or "unknown-campaign")
    stock_code = str(identity["stock_code"])
    candidate_id = str(identity["candidate_id"])
    safe_candidate = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in candidate_id
    )
    return ledger_root / campaign_id / stock_code / f"{safe_candidate}.json"


def _assert_pre_holdout_eligibility(payload: dict[str, Any]) -> None:
    result = payload.get("result") or {}
    promotion = result.get("promotion_eligibility") or {}
    audit = result.get("research_audit") or {}
    selected = result.get("selected_candidate")
    best = result.get("best_result") or {}

    if not promotion.get("eligible_for_one_shot_holdout"):
        raise ValueError("Candidate is not eligible for the one-shot final holdout")
    if promotion.get("reasons"):
        raise ValueError("Eligible candidate unexpectedly still has promotion blockers")
    if promotion.get("holdout_opened") is not False:
        raise ValueError("Pre-holdout payload says the final holdout was already opened")
    if result.get("holdout_status") != "LOCKED_REQUIRES_PROMOTION_GATE":
        raise ValueError("Final holdout lock status is invalid")
    if audit.get("holdout_used_during_search") is not False:
        raise ValueError("Final holdout leaked into adaptive research")
    if (audit.get("training_memory") or {}).get("holdout_feedback_used") is not False:
        raise ValueError("Final holdout feedback leaked into TRAIN_ONLY memory")
    if not isinstance(selected, dict):
        raise ValueError("Eligible payload has no selected candidate")
    if str(best.get("decision") or "") != ExperimentDecision.HOLDOUT_READY.value:
        raise ValueError("Eligible payload is not HOLDOUT_READY before final holdout")


def _pre_holdout_evidence_digest(payload: dict[str, Any]) -> str:
    result = payload.get("result") or {}
    selected = result.get("selected_candidate") or {}
    digest_payload = json.dumps(
        {
            "research_run_id": result.get("research_run_id"),
            "data_fingerprints": result.get("data_fingerprints") or [],
            "promotion_eligibility": result.get("promotion_eligibility") or {},
            "selected_candidate": selected,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()


def _policy(
    *,
    minimum_completed_trades: int,
    max_drawdown_percent: float,
) -> dict[str, Any]:
    return {
        "rubric": "same_fixed_validation_rubric_no_post_holdout_retuning",
        "minimum_completed_trades": max(1, int(minimum_completed_trades)),
        "max_drawdown_percent": float(max_drawdown_percent),
        "pass_requires": "HOLDOUT_READY_under_fixed_rubric",
        "durable_reservation_before_open": True,
        "holdout_feedback_to_train": False,
        "candidate_generation_after_open": False,
    }


def reserve_final_holdout(
    payload: dict[str, Any],
    *,
    claim_run_id: str,
    minimum_completed_trades: int = FINAL_HOLDOUT_MIN_COMPLETED_TRADES,
    max_drawdown_percent: float = FINAL_HOLDOUT_MAX_DRAWDOWN_PERCENT,
) -> dict[str, Any]:
    """Create a no-data reservation that must be persisted before Holdout opens.

    The reservation is deliberately written before any holdout backtest. If the
    workflow crashes after the reservation is durably pushed, a future run must
    fail closed rather than silently opening the same final exam a second time.
    """
    _assert_pre_holdout_eligibility(payload)
    claim = str(claim_run_id or "").strip()
    if not claim:
        raise ValueError("Final holdout reservation requires a claim_run_id")
    evaluation_id, identity = _canonical_candidate_identity(payload)
    result = payload.get("result") or {}
    return {
        "schema_version": FINAL_HOLDOUT_SCHEMA_VERSION,
        "evaluation_id": evaluation_id,
        "identity": identity,
        "state": FINAL_HOLDOUT_STATE_RESERVED,
        "reserved_at_utc": datetime.now(timezone.utc).isoformat(),
        "reservation_claim_run_id": claim,
        "opened_once": False,
        "opened_at_utc": None,
        "pre_holdout_research_run_id": result.get("research_run_id"),
        "pre_holdout_evidence_digest": _pre_holdout_evidence_digest(payload),
        "policy": _policy(
            minimum_completed_trades=minimum_completed_trades,
            max_drawdown_percent=max_drawdown_percent,
        ),
        "result": None,
    }


def _assert_matching_ledger_identity(
    ledger: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    evaluation_id, identity = _canonical_candidate_identity(payload)
    if ledger.get("evaluation_id") != evaluation_id or ledger.get("identity") != identity:
        raise ValueError(
            "Final holdout ledger identity collision; refusing to overwrite prior evidence"
        )
    if ledger.get("schema_version") != FINAL_HOLDOUT_SCHEMA_VERSION:
        raise ValueError("Unsupported final holdout ledger schema")


def evaluate_reserved_final_holdout(
    payload: dict[str, Any],
    reservation: dict[str, Any],
    *,
    claim_run_id: str,
    backtest_fn: BacktestFn = backtest_stock,
) -> dict[str, Any]:
    """Open Holdout only after the matching reservation has been persisted.

    The caller must persist the reservation to durable storage before invoking
    this function. A reservation from another run is never automatically taken
    over: that ambiguous crash-recovery case intentionally fails closed.
    """
    _assert_pre_holdout_eligibility(payload)
    _assert_matching_ledger_identity(reservation, payload)
    claim = str(claim_run_id or "").strip()
    if reservation.get("state") != FINAL_HOLDOUT_STATE_RESERVED:
        raise ValueError("Final holdout is not in the reserved-before-open state")
    if reservation.get("opened_once") is not False:
        raise ValueError("Reserved final holdout is unexpectedly already marked opened")
    if reservation.get("reservation_claim_run_id") != claim:
        raise ValueError("Final holdout reservation belongs to another workflow run")

    result = payload["result"]
    selected = result["selected_candidate"]
    identity = reservation["identity"]
    holdout_start, holdout_end = identity["holdout_window"]
    candidate = ResearchCandidate(
        candidate_id=str(selected["candidate_id"]),
        strategy_family=str(selected.get("strategy_family") or "unknown"),
        parameters=dict(selected.get("parameters") or {}),
        parent_id=selected.get("parent_id"),
        hypothesis=str(selected.get("hypothesis") or ""),
    )

    report = backtest_fn(
        stock_code=identity["stock_code"],
        start_date=holdout_start,
        end_date=holdout_end,
        liquidate_at_end=False,
        include_research_series=True,
        **candidate.parameters,
    )
    metrics = _validation_metrics(report)
    policy = reservation.get("policy") or {}
    holdout_result = evaluate_candidate(
        candidate,
        metrics,
        min_trades=max(1, int(policy.get("minimum_completed_trades", 1) or 1)),
        max_drawdown_percent=float(
            policy.get("max_drawdown_percent", FINAL_HOLDOUT_MAX_DRAWDOWN_PERCENT)
        ),
    )
    passed = holdout_result.decision is ExperimentDecision.HOLDOUT_READY

    return {
        **reservation,
        "state": FINAL_HOLDOUT_STATE_EVALUATED,
        "opened_once": True,
        "opened_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": {
            "status": "FINAL_HOLDOUT_PASS" if passed else "FINAL_HOLDOUT_FAIL",
            "passed": passed,
            "decision": holdout_result.decision.value,
            "research_score": holdout_result.research_score,
            "reasons": list(holdout_result.reasons),
            "metrics": {
                key: value
                for key, value in holdout_result.validation_metrics.items()
                if not key.startswith("_")
            },
            "candidate": asdict(candidate),
        },
    }


def evaluate_final_holdout_once(
    payload: dict[str, Any],
    *,
    backtest_fn: BacktestFn = backtest_stock,
    minimum_completed_trades: int = FINAL_HOLDOUT_MIN_COMPLETED_TRADES,
    max_drawdown_percent: float = FINAL_HOLDOUT_MAX_DRAWDOWN_PERCENT,
) -> dict[str, Any]:
    """Deterministic test helper; production uses durable reserve then evaluate.

    This wrapper preserves a convenient unit-test API. It does not provide the
    crash-safe durability guarantee by itself and therefore must not be called
    by the production daily workflow.
    """
    reservation = reserve_final_holdout(
        payload,
        claim_run_id="unit-test-inline-reservation",
        minimum_completed_trades=minimum_completed_trades,
        max_drawdown_percent=max_drawdown_percent,
    )
    return evaluate_reserved_final_holdout(
        payload,
        reservation,
        claim_run_id="unit-test-inline-reservation",
        backtest_fn=backtest_fn,
    )


def load_existing_ledger(path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    existing = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(existing, dict):
        raise ValueError(f"Malformed final holdout ledger: {path}")
    _assert_matching_ledger_identity(existing, payload)
    state = existing.get("state")
    if state == FINAL_HOLDOUT_STATE_RESERVED:
        if existing.get("opened_once") is not False:
            raise ValueError("Reserved final holdout ledger is incorrectly marked opened")
    elif state == FINAL_HOLDOUT_STATE_EVALUATED:
        if existing.get("opened_once") is not True:
            raise ValueError("Evaluated final holdout ledger is not marked one-shot")
    else:
        raise ValueError("Final holdout ledger has an unsupported state")
    return existing
