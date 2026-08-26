from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from scripts.run_daily_autoresearch import write_json_atomic


_DECISION_RANK = {
    "DISCARD": 0,
    "KEEP": 1,
    "HOLDOUT_READY": 2,
}
_STATE_SCHEMA_VERSION = 1
_TRACKING_SCHEMA = "research-incumbent-v1"


def _number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _decision_rank(value: Any) -> int:
    return _DECISION_RANK.get(str(value or "").upper(), -1)


def ranking_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    """Match the daily exploratory ranking policy without feeding Train memory."""
    validation = candidate.get("validation") or {}
    model_selection = candidate.get("model_selection") or {}
    return (
        bool(candidate.get("eligible_for_one_shot_holdout")),
        _decision_rank(candidate.get("decision")),
        int(candidate.get("confirmation_gate_pass_count", 0) or 0),
        bool(candidate.get("regime_robust")),
        bool(candidate.get("walk_forward_sample_sufficient")),
        _number(candidate.get("walk_forward_positive_slice_ratio")),
        bool(model_selection.get("hansen_spa_pass")),
        bool(model_selection.get("cscv_pbo_pass")),
        bool(validation.get("deflated_sharpe_pass")),
        _number(validation.get("deflated_sharpe_probability_percent")),
        _number(candidate.get("research_score")),
        _number(validation.get("wilson_lower_percent")),
        -abs(_number(validation.get("max_drawdown_percent"))),
        str(candidate.get("stock_code") or ""),
    )


def _candidate_id(candidate: dict[str, Any] | None) -> str | None:
    if not isinstance(candidate, dict):
        return None
    return str(
        candidate.get("robot_version_id")
        or candidate.get("candidate_id")
        or ""
    ).strip() or None


def _safe_candidate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if not str(value.get("candidate_id") or "").strip():
        return None
    return deepcopy(value)


def load_optional_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def apply_incumbent_retention(
    snapshot: dict[str, Any],
    prior_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Preserve the strongest observed candidate inside one frozen campaign.

    This state is observation-only. It never enters TRAIN_ONLY memory and it is
    never used to open Final Holdout. Promotion remains driven by the current
    run's auditable shard and current gate results.
    """
    updated = deepcopy(snapshot)
    campaign_id = str(updated.get("campaign_id") or "").strip()
    if not campaign_id:
        raise ValueError("Snapshot campaign_id is required")

    round_top = _safe_candidate(updated.get("top_candidate"))
    previous_campaign_incumbent = None
    prior_incumbent = None
    incumbent_since = None

    if isinstance(prior_state, dict):
        state_campaign = str(prior_state.get("campaign_id") or "").strip()
        candidate = _safe_candidate(prior_state.get("incumbent_candidate"))
        if state_campaign == campaign_id:
            prior_incumbent = candidate
            incumbent_since = prior_state.get("incumbent_since_utc")
        elif candidate is not None:
            previous_campaign_incumbent = {
                "campaign_id": state_campaign or None,
                "candidate": candidate,
                "incumbent_since_utc": prior_state.get("incumbent_since_utc"),
                "last_compared_at_utc": prior_state.get("last_compared_at_utc"),
            }

    action: str
    if prior_incumbent is None and round_top is None:
        incumbent = None
        action = "empty"
    elif prior_incumbent is None:
        incumbent = round_top
        action = "initialized"
        incumbent_since = updated.get("generated_at_utc")
    elif round_top is None:
        incumbent = prior_incumbent
        action = "retained_no_challenger"
    elif ranking_key(round_top) > ranking_key(prior_incumbent):
        incumbent = round_top
        action = "replaced"
        incumbent_since = updated.get("generated_at_utc")
    else:
        incumbent = prior_incumbent
        action = "retained"

    round_top_id = _candidate_id(round_top)
    incumbent_id = _candidate_id(incumbent)
    incumbent_in_current_round = bool(
        incumbent_id and round_top_id and incumbent_id == round_top_id
    )

    updated["round_top_candidate"] = round_top
    updated["incumbent_candidate"] = deepcopy(incumbent)
    # Backward compatibility: the existing UI/API consumer sees the retained
    # incumbent as top_candidate, while round_top_candidate exposes this run.
    updated["top_candidate"] = deepcopy(incumbent)
    updated["incumbent_tracking"] = {
        "schema": _TRACKING_SCHEMA,
        "campaign_id": campaign_id,
        "action": action,
        "incumbent_robot_version_id": incumbent_id,
        "challenger_robot_version_id": round_top_id,
        "incumbent_in_current_round": incumbent_in_current_round,
        "comparison_policy": "same_campaign_paper_guided_evidence_ranking",
        "cross_campaign_replacement_allowed": False,
        "training_feedback_used": False,
        "validation_feedback_to_train": False,
        "holdout_feedback_to_train": False,
        "promotion_uses_historical_incumbent": False,
        "note": (
            "Incumbent retention is display/ranking memory only. A historical "
            "incumbent must appear in a current auditable run and pass current "
            "gates before Final Holdout can open."
        ),
    }

    state = {
        "schema_version": _STATE_SCHEMA_VERSION,
        "tracking_schema": _TRACKING_SCHEMA,
        "campaign_id": campaign_id,
        "incumbent_candidate": deepcopy(incumbent),
        "incumbent_since_utc": incumbent_since,
        "last_compared_at_utc": updated.get("generated_at_utc"),
        "last_action": action,
        "last_round_top_candidate": deepcopy(round_top),
        "previous_campaign_incumbent": previous_campaign_incumbent,
        "training_feedback_used": False,
        "promotion_uses_historical_incumbent": False,
    }
    return updated, state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retain the strongest same-campaign research incumbent"
    )
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--history-dir",
        type=Path,
        help="Optional daily history directory to mirror the corrected snapshot",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot must be one JSON object")
    updated, state = apply_incumbent_retention(
        snapshot,
        load_optional_state(args.state),
    )
    write_json_atomic(args.snapshot, updated)
    write_json_atomic(args.state, state)

    if args.history_dir is not None:
        as_of_date = str(updated.get("as_of_date") or "").strip()
        if as_of_date:
            history_path = args.history_dir / f"{as_of_date}.json"
            if history_path.exists():
                write_json_atomic(history_path, updated)

    print(
        json.dumps(
            {
                "campaign_id": updated.get("campaign_id"),
                "action": (updated.get("incumbent_tracking") or {}).get("action"),
                "incumbent": _candidate_id(updated.get("incumbent_candidate")),
                "round_top": _candidate_id(updated.get("round_top_candidate")),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
