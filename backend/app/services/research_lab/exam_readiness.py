from __future__ import annotations

from datetime import date
from typing import Any, Callable

import pandas as pd

from app.services.history_policy import MINIMUM_RESEARCH_YEARS
from .models import ResearchSplit


MIN_VALIDATION_SESSIONS = 180
MAX_ALLOWED_END_GAP_DAYS = 10


def _coverage_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    coverage = report.get("history_coverage") or {}
    return {
        "requested_start_date": report.get("requested_start_date"),
        "requested_end_date": report.get("requested_end_date"),
        "actual_start_date": report.get("actual_start_date"),
        "actual_end_date": report.get("actual_end_date"),
        "row_count": int(coverage.get("row_count", 0) or 0),
        "available_years": float(coverage.get("available_years", 0.0) or 0.0),
        "complete_month_coverage": bool(coverage.get("complete_month_coverage")),
        "missing_months": list(coverage.get("missing_months") or []),
        "long_horizon_qualified": bool(coverage.get("long_horizon_qualified")),
        "data_source": report.get("data_source"),
        "history_recovery": dict(report.get("history_recovery") or {}),
    }


def _end_gap_days(actual_end: Any, required_end: str) -> int | None:
    if not actual_end:
        return None
    try:
        actual = pd.Timestamp(actual_end).normalize()
        required = pd.Timestamp(required_end).normalize()
    except (TypeError, ValueError):
        return None
    return max(0, int((required - actual).days))


def assess_research_exam_readiness(
    *,
    stock_code: str,
    split: ResearchSplit,
    coverage_probe: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Check that Train and Validation have enough evidence before any candidate exam.

    This preflight deliberately does not read the Final Holdout. The probe is
    allowed to inspect only dataset coverage metadata for Train and Validation;
    no return, trade, score, or validation-performance field is consumed by
    candidate generation. If the paper is incomplete, the candidate is deferred
    rather than recorded as a strategy failure.
    """
    train_report = coverage_probe(
        stock_code=stock_code,
        start_date=split.train_start,
        end_date=split.train_end,
    )
    validation_report = coverage_probe(
        stock_code=stock_code,
        start_date=split.validation_start,
        end_date=split.validation_end,
    )
    train = _coverage_snapshot(train_report)
    validation = _coverage_snapshot(validation_report)

    reasons: list[str] = []
    if not train["complete_month_coverage"] or train["missing_months"]:
        reasons.append("train_provider_history_incomplete")
    if train["available_years"] < MINIMUM_RESEARCH_YEARS:
        reasons.append("train_history_below_minimum_research_years")
    train_end_gap = _end_gap_days(train["actual_end_date"], split.train_end)
    if train_end_gap is None or train_end_gap > MAX_ALLOWED_END_GAP_DAYS:
        reasons.append("train_history_does_not_reach_split_end")

    if not validation["complete_month_coverage"] or validation["missing_months"]:
        reasons.append("validation_provider_history_incomplete")
    if validation["row_count"] < MIN_VALIDATION_SESSIONS:
        reasons.append("validation_session_count_insufficient")
    validation_end_gap = _end_gap_days(
        validation["actual_end_date"],
        split.validation_end,
    )
    if validation_end_gap is None or validation_end_gap > MAX_ALLOWED_END_GAP_DAYS:
        reasons.append("validation_history_does_not_reach_split_end")

    allowed = not reasons
    return {
        "schema_version": 1,
        "status": "READY_FOR_RESEARCH_EXAM" if allowed else "DEFERRED_DATA_LIMITED",
        "exam_allowed": allowed,
        "stock_code": stock_code.strip().upper(),
        "train": train,
        "validation": validation,
        "minimum_train_years": MINIMUM_RESEARCH_YEARS,
        "minimum_validation_sessions": MIN_VALIDATION_SESSIONS,
        "max_allowed_end_gap_days": MAX_ALLOWED_END_GAP_DAYS,
        "reasons": reasons,
        "policy": {
            "data_limited_is_not_strategy_failure": True,
            "candidate_exam_runs_only_after_preflight_pass": True,
            "validation_performance_not_used_in_preflight": True,
            "final_holdout_read_during_preflight": False,
            "final_holdout_remains_one_shot_and_locked": True,
        },
    }
