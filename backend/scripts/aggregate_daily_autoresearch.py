from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.services.scanner_service import SCANNER_UNIVERSE
from app.services.research_lab.evolution import SEARCH_SPACE_SCHEMA
from app.services.research_lab.training_memory import (
    TRAIN_DATA_IDENTITY_SCHEMA,
    TRAINING_MEMORY_SCHEMA_VERSION,
    training_memory_summary,
)
from scripts.run_daily_autoresearch import write_json_atomic


def _number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _candidate_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    result = payload.get("result") or {}
    selected = result.get("selected_candidate")
    best = result.get("best_result")
    if not isinstance(selected, dict) or not isinstance(best, dict):
        return None
    metrics = best.get("validation_metrics") or {}
    statistics = metrics.get("statistical_evidence") or {}
    deflated = metrics.get("deflated_sharpe") or {}
    tournament = result.get("market_regime_tournament") or []
    robustness: dict[str, Any] = {}
    if tournament and isinstance(tournament[0], dict):
        matrix = tournament[0].get("market_regime_matrix") or {}
        robustness = matrix.get("robustness") or {}
    walk_forward = result.get("walk_forward_matrix") or {}
    walk_forward_aggregate = walk_forward.get("aggregate") or {}
    eligibility = result.get("promotion_eligibility") or {}
    version_payload = json.dumps(
        {
            "campaign_id": (payload.get("campaign") or {}).get("campaign_id"),
            "stock_code": payload.get("stock_code"),
            "candidate_id": selected.get("candidate_id"),
            "strategy_family": selected.get("strategy_family"),
            "parameters": selected.get("parameters") or {},
            "search_space_schema": SEARCH_SPACE_SCHEMA,
            "data_fingerprints": result.get("data_fingerprints") or [],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    robot_version_id = hashlib.sha256(
        version_payload.encode("utf-8")
    ).hexdigest()[:24]
    return {
        "stock_code": payload.get("stock_code"),
        "research_run_id": result.get("research_run_id"),
        "data_fingerprints": result.get("data_fingerprints") or [],
        "candidate_id": selected.get("candidate_id"),
        "robot_version_id": robot_version_id,
        "parent_id": selected.get("parent_id"),
        "strategy_family": selected.get("strategy_family"),
        "hypothesis": selected.get("hypothesis"),
        "parameters": selected.get("parameters") or {},
        "decision": best.get("decision"),
        "research_score": _number(best.get("research_score")),
        "eligible_for_one_shot_holdout": bool(
            eligibility.get("eligible_for_one_shot_holdout")
        ),
        "gate_reasons": eligibility.get("reasons") or [],
        "validation": {
            "completed_trades": int(_number(metrics.get("completed_trades"))),
            "win_rate_percent": _number(metrics.get("win_rate_percent")),
            "wilson_lower_percent": _number(
                metrics.get("wilson_win_rate_lower_bound_percent")
            ),
            "total_return_percent": _number(metrics.get("total_return_percent")),
            "alpha_percent": _number(metrics.get("alpha_percent")),
            "max_drawdown_percent": _number(metrics.get("max_drawdown_percent")),
            "probabilistic_sharpe_ratio_percent": _number(
                statistics.get("probabilistic_sharpe_ratio_percent")
            ),
            "deflated_sharpe_probability_percent": _number(
                deflated.get("deflated_sharpe_probability_percent")
            ),
        },
        "regime_robust": bool(
            robustness.get("robust_across_required_regimes")
        ),
        "regime_score": _number(robustness.get("robustness_score")),
        "walk_forward_positive_slice_ratio": _number(
            walk_forward_aggregate.get("positive_slice_ratio")
        ),
    }


def _ranking_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    validation = candidate.get("validation") or {}
    return (
        bool(candidate.get("eligible_for_one_shot_holdout")),
        bool(candidate.get("regime_robust")),
        _number(candidate.get("walk_forward_positive_slice_ratio")),
        _number(validation.get("wilson_lower_percent")),
        _number(validation.get("deflated_sharpe_probability_percent")),
        _number(candidate.get("research_score")),
        -abs(_number(validation.get("max_drawdown_percent"))),
        str(candidate.get("stock_code") or ""),
    )


def aggregate_payloads(
    payloads: Iterable[dict[str, Any]],
    *,
    as_of_date: date,
    expected_universe: tuple[str, ...] = SCANNER_UNIVERSE,
) -> dict[str, Any]:
    rows = list(payloads)
    by_symbol = {str(row.get("stock_code") or "").upper(): row for row in rows}
    missing = [symbol for symbol in expected_universe if symbol not in by_symbol]
    if missing:
        raise ValueError("Daily research is incomplete: " + ", ".join(missing))

    campaign_ids = {
        str((row.get("campaign") or {}).get("campaign_id") or "")
        for row in rows
    }
    if len(campaign_ids) != 1 or "" in campaign_ids:
        raise ValueError("Daily research payloads do not share one campaign")

    memories: dict[str, dict[str, Any]] = {}
    for symbol in expected_universe:
        if by_symbol[symbol].get("schema_version") != 2:
            raise ValueError(f"{symbol} daily payload schema mismatch")
        result = by_symbol[symbol].get("result") or {}
        promotion = result.get("promotion_eligibility") or {}
        audit = result.get("research_audit") or {}
        if promotion.get("holdout_opened") is not False:
            raise ValueError(f"{symbol} opened the final holdout")
        if audit.get("holdout_used_during_search") is not False:
            raise ValueError(f"{symbol} leaked final holdout data")
        memory_audit = audit.get("training_memory") or {}
        if memory_audit.get("validation_feedback_used") is not False:
            raise ValueError(f"{symbol} leaked validation into training memory")
        if memory_audit.get("holdout_feedback_used") is not False:
            raise ValueError(f"{symbol} leaked holdout into training memory")
        memory = by_symbol[symbol].get("training_memory")
        if not isinstance(memory, dict):
            raise ValueError(f"{symbol} did not publish training memory")
        if memory.get("provenance") != "TRAIN_ONLY":
            raise ValueError(f"{symbol} training memory provenance is unsafe")
        if memory.get("schema_version") != TRAINING_MEMORY_SCHEMA_VERSION:
            raise ValueError(f"{symbol} training memory schema mismatch")
        if memory.get("validation_feedback_used") is not False:
            raise ValueError(f"{symbol} memory contains validation feedback")
        if memory.get("holdout_feedback_used") is not False:
            raise ValueError(f"{symbol} memory contains holdout feedback")
        if str(memory.get("stock_code") or "").upper() != symbol:
            raise ValueError(f"{symbol} training memory stock mismatch")
        if memory.get("campaign_id") not in campaign_ids:
            raise ValueError(f"{symbol} training memory campaign mismatch")
        if memory.get("search_space_schema") != SEARCH_SPACE_SCHEMA:
            raise ValueError(f"{symbol} training memory search schema mismatch")
        if (
            memory.get("train_data_identity_schema")
            != TRAIN_DATA_IDENTITY_SCHEMA
        ):
            raise ValueError(
                f"{symbol} canonical train data identity schema mismatch"
            )
        if not str(memory.get("train_data_identity") or "").strip():
            raise ValueError(f"{symbol} canonical train data identity is missing")
        memories[symbol] = memory

    candidates = [
        summary
        for symbol in expected_universe
        if (summary := _candidate_summary(by_symbol[symbol])) is not None
    ]
    candidates.sort(key=_ranking_key, reverse=True)
    eligible_count = sum(
        1 for candidate in candidates
        if candidate.get("eligible_for_one_shot_holdout")
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    memory_summaries = {
        symbol: training_memory_summary(memories[symbol])
        for symbol in expected_universe
    }
    strategy_families = sorted(
        {
            str(family)
            for summary in memory_summaries.values()
            for family in summary.get("strategy_families") or []
            if family
        }
    )
    return {
        "schema_version": 2,
        "automation": {
            "enabled": True,
            "mode": "daily_unattended",
            "status": "COMPLETED",
            "schedule": "30 10 * * 1-5",
            "schedule_timezone": "Asia/Taipei",
            "schedule_label": "每個台股交易日 18:30",
            "runner": "github_actions_durable_matrix",
            "manual_action_required": False,
        },
        "as_of_date": as_of_date.isoformat(),
        "campaign_id": campaign_ids.pop(),
        "generated_at_utc": generated_at,
        "universe": list(expected_universe),
        "universe_size": len(expected_universe),
        "completed_symbol_count": len(expected_universe),
        "candidate_count": len(candidates),
        "eligible_candidate_count": eligible_count,
        "holdout_opened": False,
        "integrity_status": "PASS",
        "training_memory": {
            "enabled": True,
            "provenance": "TRAIN_ONLY",
            "search_space_schema": SEARCH_SPACE_SCHEMA,
            "completed_symbol_count": len(memories),
            "continued_symbol_count": sum(
                bool(summary.get("prior_memory_continued"))
                for summary in memory_summaries.values()
            ),
            "verified_data_identity_symbol_count": sum(
                bool(summary.get("train_data_identity_verified"))
                for summary in memory_summaries.values()
            ),
            "migrated_data_identity_symbol_count": sum(
                bool(summary.get("train_data_identity_migrated"))
                for summary in memory_summaries.values()
            ),
            "unique_experiment_count": sum(
                int(summary.get("unique_experiment_count", 0) or 0)
                for summary in memory_summaries.values()
            ),
            "lifetime_experiment_count": sum(
                int(summary.get("lifetime_experiment_count", 0) or 0)
                for summary in memory_summaries.values()
            ),
            "last_run_new_experiment_count": sum(
                int(summary.get("last_run_new_experiment_count", 0) or 0)
                for summary in memory_summaries.values()
            ),
            "last_run_duplicate_skip_count": sum(
                int(summary.get("last_run_duplicate_skip_count", 0) or 0)
                for summary in memory_summaries.values()
            ),
            "train_trial_count": sum(
                int(summary.get("train_trial_count", 0) or 0)
                for summary in memory_summaries.values()
            ),
            "elite_count": sum(
                int(summary.get("elite_count", 0) or 0)
                for summary in memory_summaries.values()
            ),
            "frontier_count": sum(
                int(summary.get("frontier_count", 0) or 0)
                for summary in memory_summaries.values()
            ),
            "strategy_family_count": len(strategy_families),
            "strategy_families": strategy_families,
            "validation_feedback_used": False,
            "holdout_feedback_used": False,
        },
        "ranking_policy": (
            "Exploratory evidence ranking only: promotion gate, regime robustness, "
            "walk-forward stability, Wilson lower bound, DSR, score, drawdown. "
            "No candidate is called a production champion before one-shot holdout."
        ),
        "top_candidate": candidates[0] if candidates else None,
        "candidates": candidates,
        "runs": [
            {
                "stock_code": symbol,
                "research_run_id": (
                    by_symbol[symbol].get("result") or {}
                ).get("research_run_id"),
                "data_fingerprints": (
                    by_symbol[symbol].get("result") or {}
                ).get("data_fingerprints") or [],
                "experiments_run": (
                    by_symbol[symbol].get("result") or {}
                ).get("experiments_run"),
                "candidate_offset": (
                    by_symbol[symbol].get("automation") or {}
                ).get("candidate_offset"),
                "training_memory": memory_summaries[symbol],
            }
            for symbol in expected_universe
        ],
    }


def load_payloads(input_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(input_dir.glob("*.json"))
    ]


def write_training_memories(
    payloads: Iterable[dict[str, Any]],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for payload in payloads:
        symbol = str(payload.get("stock_code") or "").upper()
        memory = payload.get("training_memory")
        if not symbol or not isinstance(memory, dict):
            raise ValueError("Cannot publish incomplete training memory")
        write_json_atomic(output_dir / f"{symbol}.json", memory)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate all daily research shards")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--memory-output-dir", type=Path, required=True)
    parser.add_argument("--as-of-date", type=date.fromisoformat, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_payloads(args.input_dir)
    payload = aggregate_payloads(
        rows,
        as_of_date=args.as_of_date,
    )
    write_json_atomic(args.output, payload)
    write_training_memories(rows, args.memory_output_dir)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "campaign_id": payload["campaign_id"],
                "completed_symbol_count": payload["completed_symbol_count"],
                "eligible_candidate_count": payload["eligible_candidate_count"],
                "holdout_opened": payload["holdout_opened"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
