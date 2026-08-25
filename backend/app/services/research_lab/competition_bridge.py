from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import re
from typing import Any
from zoneinfo import ZoneInfo

from app.services.competition_service import freeze_robot_spec

from .runner import _ALLOWED_PARAMETERS


CHALLENGER_SCHEMA_VERSION = 2
CERTIFIED_STATUS = "CERTIFIED_FINAL_HOLDOUT_PASS"
QUEUE_STATUS = "QUEUED_CERTIFIED"
WAITING_STATUS = "WAITING_FOR_CERTIFIED_ROBOT"
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


def _required_text(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"Certified robot is missing {key}")
    return value


def _validated_parameters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Certified robot parameters must be an object")
    unknown = set(value) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(
            f"Certified robot contains unsupported research parameters: {sorted(unknown)}"
        )
    return dict(value)


def _robot_id(certification_id: str, stock_code: str) -> str:
    digest = hashlib.sha256(certification_id.encode("utf-8")).hexdigest()[:12].upper()
    safe_stock = re.sub(r"[^A-Z0-9]+", "-", stock_code.upper()).strip("-")
    return f"RESEARCH-{safe_stock or 'UNKNOWN'}-{digest}"


def _challenge_not_before(certified_robot: dict[str, Any]) -> dict[str, str]:
    """Return the first calendar date that may contribute to competition evidence.

    Competition evidence must be strictly newer than both the Final Holdout and the
    certification event. This prevents a certified strategy from immediately winning
    a title by being ranked again on data that was already used for its final exam.
    """

    holdout_window = certified_robot.get("holdout_window")
    if not isinstance(holdout_window, (list, tuple)) or len(holdout_window) != 2:
        raise ValueError("Certified robot holdout_window must contain start and end")
    try:
        holdout_end = datetime.fromisoformat(str(holdout_window[1])).date()
    except ValueError as error:
        raise ValueError("Certified robot holdout end date is invalid") from error

    opened_at = _required_text(certified_robot, "opened_at_utc")
    try:
        opened = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Certified robot opened_at_utc is invalid") from error
    if opened.tzinfo is None:
        raise ValueError("Certified robot opened_at_utc must include a timezone")
    certification_date = opened.astimezone(TAIPEI_TIMEZONE).date()
    last_tainted_date = max(holdout_end, certification_date)
    challenge_not_before = last_tainted_date + timedelta(days=1)
    return {
        "holdout_end_date": holdout_end.isoformat(),
        "certification_date_taipei": certification_date.isoformat(),
        "challenge_not_before": challenge_not_before.isoformat(),
    }


def build_competition_challenger(
    certified_robot: dict[str, Any],
) -> dict[str, Any]:
    """Convert one Final-Holdout-certified research result into an immutable queue item.

    The adapter freezes an auditable rule specification but deliberately quarantines
    it from title evidence until a market session strictly after certification and
    Final Holdout. The competition layer still imposes its own capital, cost, risk,
    market universe and common comparison window.
    """

    if not isinstance(certified_robot, dict):
        raise ValueError("Certified robot must be an object")
    if certified_robot.get("status") != CERTIFIED_STATUS:
        raise ValueError("Only CERTIFIED_FINAL_HOLDOUT_PASS robots may enter the queue")

    certification_id = _required_text(certified_robot, "certification_id")
    campaign_id = _required_text(certified_robot, "campaign_id")
    stock_code = _required_text(certified_robot, "stock_code")
    candidate_id = _required_text(certified_robot, "candidate_id")
    strategy_family = _required_text(certified_robot, "strategy_family")
    research_parameters = _validated_parameters(certified_robot.get("parameters"))
    challenge_dates = _challenge_not_before(certified_robot)

    competition_parameters = dict(research_parameters)
    research_initial_capital = competition_parameters.pop("initial_capital", None)
    robot_id = _robot_id(certification_id, stock_code)

    spec = {
        "robot_id": robot_id,
        "name": f"研究院認證挑戰者 {candidate_id}",
        "family": f"research::{strategy_family}",
        "entry": {
            "entry_score": competition_parameters.get("entry_score"),
            "entry_mode": competition_parameters.get("entry_mode"),
            "require_ema_trend": competition_parameters.get("require_ema_trend"),
            "ema_fast_column": competition_parameters.get("ema_fast_column"),
            "ema_slow_column": competition_parameters.get("ema_slow_column"),
        },
        "exit": {
            "exit_score": competition_parameters.get("exit_score"),
            "exit_mode": competition_parameters.get("exit_mode"),
            "max_holding_days": competition_parameters.get("max_holding_days"),
        },
        "parameters": competition_parameters,
        "certification": {
            "certification_id": certification_id,
            "campaign_id": campaign_id,
            "stock_code": stock_code,
            "candidate_id": candidate_id,
            "strategy_family": strategy_family,
            "holdout_window": certified_robot.get("holdout_window") or [],
            "opened_at_utc": certified_robot.get("opened_at_utc"),
            "pre_holdout_research_run_id": certified_robot.get(
                "pre_holdout_research_run_id"
            ),
        },
        "competition_contract": {
            "role": "challenger",
            "status": QUEUE_STATUS,
            "fixed_rule": True,
            "competition_sets_initial_capital": True,
            "competition_sets_cost_model": True,
            "competition_sets_risk_model": True,
            "competition_sets_market_universe": True,
            "final_holdout_score_used_for_competition_ranking": False,
            "same_campaign_competition_feedback_to_train": False,
            "post_certification_evidence_only": True,
            **challenge_dates,
        },
    }
    frozen = freeze_robot_spec(spec)

    return {
        "schema_version": CHALLENGER_SCHEMA_VERSION,
        "challenger_id": f"CH-{frozen['rule_fingerprint'][:20]}",
        "robot_id": robot_id,
        "status": QUEUE_STATUS,
        "rule_fingerprint": frozen["rule_fingerprint"],
        "immutable": True,
        "spec": spec,
        "challenge_contract": {
            "post_certification_evidence_only": True,
            **challenge_dates,
        },
        "research_provenance": {
            "certification_id": certification_id,
            "campaign_id": campaign_id,
            "stock_code": stock_code,
            "candidate_id": candidate_id,
            "strategy_family": strategy_family,
            "research_initial_capital": research_initial_capital,
            "opened_at_utc": certified_robot.get("opened_at_utc"),
            "pre_holdout_research_run_id": certified_robot.get(
                "pre_holdout_research_run_id"
            ),
        },
    }


def build_competition_challenger_roster(
    certified_registry: dict[str, Any],
) -> dict[str, Any]:
    """Build a fail-closed queue from the certified Final Holdout registry."""

    if not isinstance(certified_registry, dict):
        raise ValueError("Certified registry must be an object")
    if certified_registry.get("schema_version") != 2:
        raise ValueError("Unsupported certified registry schema")

    robots = certified_registry.get("robots")
    if not isinstance(robots, list):
        raise ValueError("Certified registry robots must be a list")
    expected_count = certified_registry.get("certified_robot_count")
    if not isinstance(expected_count, int) or expected_count != len(robots):
        raise ValueError("Certified registry count does not match robot entries")

    challengers = [build_competition_challenger(robot) for robot in robots]
    fingerprints = [item["rule_fingerprint"] for item in challengers]
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("Duplicate immutable challenger fingerprints detected")
    challengers.sort(key=lambda item: (item["robot_id"], item["challenger_id"]))

    return {
        "schema_version": CHALLENGER_SCHEMA_VERSION,
        "source_registry_schema_version": certified_registry.get("schema_version"),
        "generated_from_certified_registry_at_utc": certified_registry.get(
            "generated_at_utc"
        ),
        "status": "READY" if challengers else WAITING_STATUS,
        "challenger_count": len(challengers),
        "policy": {
            "certified_final_holdout_required": True,
            "immutable_rule_fingerprint_required": True,
            "competition_rebinds_capital_cost_risk_and_universe": True,
            "holdout_score_used_for_ranking": False,
            "same_campaign_competition_feedback_to_train": False,
            "post_certification_evidence_only": True,
            "common_fresh_comparison_window": True,
            "automatic_activation_when_certified": True,
        },
        "challengers": challengers,
    }
