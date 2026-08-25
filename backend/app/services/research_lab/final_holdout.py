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


FINAL_HOLDOUT_SCHEMA_VERSION = 1
FINAL_HOLDOUT_MIN_COMPLETED_TRADES = 4
FINAL_HOLDOUT_MAX_DRAWDOWN_PERCENT = 30.0

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


def _public_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metrics.items()
        if not key.startswith("_")
    }


def evaluate_final_holdout_once(
    payload: dict[str, Any],
    *,
    backtest_fn: BacktestFn = backtest_stock,
    minimum_completed_trades: int = FINAL_HOLDOUT_MIN_COMPLETED_TRADES,
    max_drawdown_percent: float = FINAL_HOLDOUT_MAX_DRAWDOWN_PERCENT,
) -> dict[str, Any]:
    """Open the untouched final holdout exactly once for one promoted candidate.

    This function performs no candidate generation and returns no information to
    TRAIN_ONLY memory. The final decision reuses the already-fixed validation
    scoring rubric rather than retuning thresholds after seeing holdout results.
    A durable ledger outside adaptive memory is responsible for preventing a
    second evaluation of the same campaign/candidate identity.
    """
    _assert_pre_holdout_eligibility(payload)
    evaluation_id, identity = _canonical_candidate_identity(payload)
    result = payload["result"]
    selected = result["selected_candidate"]
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
    holdout_result = evaluate_candidate(
        candidate,
        metrics,
        min_trades=max(1, int(minimum_completed_trades)),
        max_drawdown_percent=float(max_drawdown_percent),
    )
    passed = holdout_result.decision is ExperimentDecision.HOLDOUT_READY

    pre_holdout_digest_payload = json.dumps(
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

    return {
        "schema_version": FINAL_HOLDOUT_SCHEMA_VERSION,
        "evaluation_id": evaluation_id,
        "identity": identity,
        "opened_at_utc": datetime.now(timezone.utc).isoformat(),
        "opened_once": True,
        "pre_holdout_research_run_id": result.get("research_run_id"),
        "pre_holdout_evidence_digest": hashlib.sha256(
            pre_holdout_digest_payload.encode("utf-8")
        ).hexdigest(),
        "policy": {
            "rubric": "same_fixed_validation_rubric_no_post_holdout_retuning",
            "minimum_completed_trades": max(1, int(minimum_completed_trades)),
            "max_drawdown_percent": float(max_drawdown_percent),
            "pass_requires": "HOLDOUT_READY_under_fixed_rubric",
            "holdout_feedback_to_train": False,
            "candidate_generation_after_open": False,
        },
        "result": {
            "status": "FINAL_HOLDOUT_PASS" if passed else "FINAL_HOLDOUT_FAIL",
            "passed": passed,
            "decision": holdout_result.decision.value,
            "research_score": holdout_result.research_score,
            "reasons": list(holdout_result.reasons),
            "metrics": _public_metrics(holdout_result.validation_metrics),
            "candidate": asdict(candidate),
        },
    }


def load_existing_ledger(path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    existing = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(existing, dict):
        raise ValueError(f"Malformed final holdout ledger: {path}")
    evaluation_id, identity = _canonical_candidate_identity(payload)
    if existing.get("evaluation_id") != evaluation_id or existing.get("identity") != identity:
        raise ValueError(
            "Final holdout ledger identity collision; refusing to overwrite prior evidence"
        )
    if existing.get("opened_once") is not True:
        raise ValueError("Existing final holdout ledger is not marked one-shot")
    return existing
