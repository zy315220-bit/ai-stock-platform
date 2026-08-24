from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.api.research_lab import run_research
from app.services.research_lab.evolution import generate_parameter_candidates


DEFAULT_MAX_EXPERIMENTS = 24
AUTOMATION_SCHEMA_VERSION = 1


def campaign_window(as_of_date: date) -> dict[str, str]:
    """Return one fixed research window for the current calendar quarter.

    Keeping the split fixed for the whole campaign prevents a daily scheduler
    from slowly leaking yesterday's holdout observations back into adaptive
    search.  A new campaign starts only at a quarter boundary and receives a
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


def execute_daily_stock_research(
    stock_code: str,
    as_of_date: date,
    *,
    max_experiments: int = DEFAULT_MAX_EXPERIMENTS,
    research_runner: Callable[..., dict[str, object]] = run_research,
) -> dict[str, Any]:
    stock = stock_code.strip().upper()
    campaign = campaign_window(as_of_date)
    candidate_offset = candidate_offset_for(stock, as_of_date)
    result = research_runner(
        stock_code=stock,
        start_date=date.fromisoformat(campaign["start_date"]),
        end_date=date.fromisoformat(campaign["end_date"]),
        max_generations=3,
        max_experiments=max_experiments,
        min_validation_trades=4,
        validation_finalists=5,
        walk_forward_slices=3,
        regime_candidate_count=2,
        regime_slices=6,
        min_regime_trades=1,
        candidate_offset=candidate_offset,
    )
    payload = dict(result)
    _assert_locked_holdout(payload)
    return {
        "schema_version": AUTOMATION_SCHEMA_VERSION,
        "automation": {
            "mode": "daily_unattended",
            "schedule": "30 10 * * 1-5",
            "schedule_timezone": "Asia/Taipei",
            "candidate_offset": candidate_offset,
            "max_experiments": max_experiments,
        },
        "as_of_date": as_of_date.isoformat(),
        "campaign": campaign,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stock_code": stock,
        "result": payload,
    }


def run_with_retry(
    stock_code: str,
    as_of_date: date,
    *,
    max_experiments: int,
    attempts: int,
    retry_delay_seconds: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return execute_daily_stock_research(
                stock_code,
                as_of_date,
                max_experiments=max_experiments,
            )
        except Exception as exc:  # GitHub Actions records the final traceback.
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one unattended daily research shard")
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--as-of-date", type=date.fromisoformat, required=True)
    parser.add_argument("--max-experiments", type=int, default=DEFAULT_MAX_EXPERIMENTS)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=int, default=20)
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
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
