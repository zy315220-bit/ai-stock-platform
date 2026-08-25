from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.api.research_lab import execute_research_pipeline
from app.services.backtest.engine import backtest_stock
from app.services.research_lab.evolution import generate_parameter_candidates
from app.services.research_lab.splits import build_research_split
from app.services.research_lab.training_memory import (
    TRAIN_DATA_IDENTITY_SCHEMA,
    build_training_memory,
    prepare_daily_candidate_plan,
    training_memory_summary,
)


DEFAULT_MAX_EXPERIMENTS = 24
AUTOMATION_SCHEMA_VERSION = 2


def resolve_train_data_identity(
    *,
    stock_code: str,
    train_start: str,
    train_end: str,
) -> str:
    """Fingerprint one fixed Train-only frame before adaptive search.

    Candidate strategies can require different indicator columns and therefore
    trim different leading rows. Their execution fingerprints remain useful
    audit evidence, but they are not a stable cross-day dataset identity. This
    fixed score-only probe makes the compatibility decision independent of the
    strategy family selected on a particular day.
    """
    report = backtest_stock(
        stock_code=stock_code,
        start_date=train_start,
        end_date=train_end,
        entry_score=99,
        exit_score=1,
        initial_capital=100_000,
        require_ema_trend=False,
        entry_mode="score",
        exit_mode="score",
        max_holding_days=60,
        liquidate_at_end=False,
        include_research_series=False,
    )
    cache = report.get("score_series_cache") or {}
    fingerprint = str(cache.get("fingerprint") or "").strip()
    if not fingerprint:
        raise RuntimeError("Canonical Train data probe produced no fingerprint")
    identity_payload = json.dumps(
        {
            "schema": TRAIN_DATA_IDENTITY_SCHEMA,
            "score_cache_schema": cache.get("schema"),
            "stock_code": stock_code,
            "train_window": [train_start, train_end],
            "actual_window": [
                report.get("actual_start_date"),
                report.get("actual_end_date"),
            ],
            "fingerprint": fingerprint,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity_payload.encode("utf-8")).hexdigest()[:24]


def campaign_window(as_of_date: date) -> dict[str, str]:
    """Return one fixed research window for the current calendar quarter.

    Keeping the split fixed for the whole campaign prevents a daily scheduler
    from slowly leaking yesterday's holdout observations back into adaptive
    search. A new campaign starts only at a quarter boundary and receives a
    new versioned identity.
    """
    quarter = (as_of_date.month - 1) // 3 + 1
    quarter_start_month = (quarter - 1) * 3 + 1
    quarter_start = date(as_of_date.year, quarter_start_month, 1)
    campaign_end = quarter_start - timedelta(days=1)
    campaign_start = date(campaign_end.year - 6, 1, 1)
    return {
        "campaign_id": f"{as_of_date.year}-Q{quarter}",
        "start_date": campaign_start.isoformat(),
        "end_date": campaign_end.isoformat(),
    }


def candidate_offset_for(stock_code: str, as_of_date: date) -> int:
    """Select a reproducible daily train-grid rotation for one symbol."""
    candidate_count = len(generate_parameter_candidates())
    if candidate_count == 0:
        raise RuntimeError("Research candidate universe is empty")
    payload = f"{stock_code.strip().upper()}|{as_of_date.isoformat()}"
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12], 16) % candidate_count


def _assert_locked_holdout(result: dict[str, Any]) -> None:
    promotion = result.get("promotion_eligibility") or {}
    audit = result.get("research_audit") or {}
    if promotion.get("holdout_opened") is not False:
        raise RuntimeError("Daily research refused: final holdout was opened")
    if audit.get("holdout_used_during_search") is not False:
        raise RuntimeError("Daily research refused: holdout leaked into search")
    if result.get("holdout_status") != "LOCKED_REQUIRES_PROMOTION_GATE":
        raise RuntimeError("Daily research refused: holdout lock status is invalid")
    memory_audit = audit.get("training_memory") or {}
    if memory_audit.get("validation_feedback_used") is not False:
        raise RuntimeError("Daily research refused: validation entered memory")
    if memory_audit.get("holdout_feedback_used") is not False:
        raise RuntimeError("Daily research refused: holdout entered memory")


def execute_daily_stock_research(
    stock_code: str,
    as_of_date: date,
    *,
    max_experiments: int = DEFAULT_MAX_EXPERIMENTS,
    prior_training_memory: dict[str, Any] | None = None,
    research_runner: Callable[
        ..., dict[str, object]
    ] = execute_research_pipeline,
    train_identity_resolver: Callable[..., str] = resolve_train_data_identity,
) -> dict[str, Any]:
    stock = stock_code.strip().upper()
    campaign = campaign_window(as_of_date)
    candidate_offset = candidate_offset_for(stock, as_of_date)
    split = build_research_split(
        campaign["start_date"],
        campaign["end_date"],
    )
    train_data_identity = train_identity_resolver(
        stock_code=stock,
        train_start=split.train_start,
        train_end=split.train_end,
    )
    grid = generate_parameter_candidates()
    rotated_grid = grid[candidate_offset:] + grid[:candidate_offset]
    candidate_plan = prepare_daily_candidate_plan(
        stock_code=stock,
        campaign_id=campaign["campaign_id"],
        train_window=(split.train_start, split.train_end),
        train_data_identity=train_data_identity,
        rotated_grid=rotated_grid,
        prior_memory=prior_training_memory,
    )
    result = research_runner(
        stock_code=stock,
        start_date=date.fromisoformat(campaign["start_date"]),
        end_date=date.fromisoformat(campaign["end_date"]),
        max_generations=3,
        max_experiments=max_experiments,
        min_validation_trades=4,
        validation_finalists=8,
        walk_forward_slices=3,
        regime_candidate_count=3,
        regime_slices=6,
        min_regime_trades=1,
        candidate_offset=candidate_offset,
        initial_candidates=list(candidate_plan.candidates),
        excluded_training_signatures=(
            candidate_plan.excluded_parameter_signatures
        ),
        training_memory_audit=candidate_plan.audit,
        prior_train_trial_sharpes=(
            candidate_plan.prior_train_trial_sharpes
        ),
    )
    payload = dict(result)
    _assert_locked_holdout(payload)
    memory = build_training_memory(
        stock_code=stock,
        campaign_id=campaign["campaign_id"],
        train_window=(split.train_start, split.train_end),
        train_data_identity=train_data_identity,
        as_of_date=as_of_date.isoformat(),
        result=payload,
        prior_memory=prior_training_memory,
    )
    promotion_block_reason: str | None = None
    if memory.get("memory_reset_reason") == "train_data_revision":
        promotion_block_reason = (
            "train_data_revision_requires_fresh_cumulative_evidence"
        )
    elif not memory.get("train_data_identity_verified"):
        promotion_block_reason = (
            "train_data_identity_requires_consecutive_confirmation"
        )
    if promotion_block_reason:
        promotion = dict(payload.get("promotion_eligibility") or {})
        reasons = list(promotion.get("reasons") or [])
        if promotion_block_reason not in reasons:
            reasons.append(promotion_block_reason)
        promotion.update(
            eligible_for_one_shot_holdout=False,
            reasons=reasons,
            holdout_opened=False,
        )
        payload["promotion_eligibility"] = promotion
    return {
        "schema_version": AUTOMATION_SCHEMA_VERSION,
        "automation": {
            "mode": "daily_unattended",
            "schedule": "30 22,10 * * *",
            "schedule_timezone": "Asia/Taipei",
            "sessions_per_day": 2,
            "candidate_offset": candidate_offset,
            "max_experiments": max_experiments,
            "training_memory": training_memory_summary(memory),
        },
        "as_of_date": as_of_date.isoformat(),
        "campaign": campaign,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stock_code": stock,
        "result": payload,
        "training_memory": memory,
    }


def run_with_retry(
    stock_code: str,
    as_of_date: date,
    *,
    max_experiments: int,
    attempts: int,
    retry_delay_seconds: int,
    prior_training_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return execute_daily_stock_research(
                stock_code,
                as_of_date,
                max_experiments=max_experiments,
                prior_training_memory=prior_training_memory,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(max(0, retry_delay_seconds))
    assert last_error is not None
    raise last_error


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_optional_memory(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Training memory must be one JSON object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one unattended daily research shard")
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--as-of-date", type=date.fromisoformat, required=True)
    parser.add_argument("--max-experiments", type=int, default=DEFAULT_MAX_EXPERIMENTS)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=int, default=20)
    parser.add_argument("--prior-memory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_with_retry(
        args.stock_code,
        args.as_of_date,
        max_experiments=max(1, args.max_experiments),
        attempts=max(1, args.attempts),
        retry_delay_seconds=max(0, args.retry_delay_seconds),
        prior_training_memory=load_optional_memory(args.prior_memory),
    )
    write_json_atomic(args.output, payload)
    result = payload["result"]
    print(
        json.dumps(
            {
                "stock_code": payload["stock_code"],
                "campaign": payload["campaign"]["campaign_id"],
                "research_run_id": result.get("research_run_id"),
                "experiments_run": result.get("experiments_run"),
                "eligible_for_one_shot_holdout": (
                    result.get("promotion_eligibility") or {}
                ).get("eligible_for_one_shot_holdout", False),
                "holdout_opened": False,
                "training_memory": payload["automation"][
                    "training_memory"
                ],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
