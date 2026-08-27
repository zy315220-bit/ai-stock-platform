from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL_SELECTION_REASON_MAP = {
    "cscv_pbo_failed_or_unavailable": "cscv_pbo",
    "hansen_spa_failed_or_unavailable": "hansen_spa",
}


def _classify_model_selection(result: dict[str, Any]) -> dict[str, str]:
    evidence = result.get("model_selection_evidence") or {}
    pbo = evidence.get("cscv_pbo") or {}
    spa = evidence.get("hansen_spa") or {}
    return {
        "cscv_pbo": (
            "pass"
            if pbo.get("overfitting_risk_pass")
            else "failed"
            if pbo.get("available")
            else "unavailable"
        ),
        "hansen_spa": (
            "pass"
            if spa.get("superior_predictive_ability_pass")
            else "failed"
            if spa.get("available")
            else "unavailable"
        ),
    }


def _coverage_from_result(row: dict[str, Any] | None) -> dict[str, Any]:
    metrics = (row or {}).get("validation_metrics") or {}
    coverage = metrics.get("history_coverage") or {}
    return {
        "actual_start_date": metrics.get("actual_start_date"),
        "actual_end_date": metrics.get("actual_end_date"),
        "available_years": float(coverage.get("available_years", 0.0) or 0.0),
        "row_count": int(coverage.get("row_count", 0) or 0),
        "complete_month_coverage": coverage.get("complete_month_coverage"),
        "missing_months": list(coverage.get("missing_months") or []),
        "long_horizon_qualified": bool(coverage.get("long_horizon_qualified")),
    }


def _classify_data_readiness(result: dict[str, Any]) -> dict[str, Any]:
    """Keep missing market evidence distinct from a strategy losing a gate.

    Validation slices are intentionally shorter than three years, so only
    missing calendar months are treated as provider-data incompleteness there.
    A short Train history with complete months is a lifecycle limitation (for
    example a recently listed ETF), not a strategy failure and not a provider
    outage. Candidate-diversity limitations are reported separately as well.
    """
    train = _coverage_from_result(result.get("training_best_result"))
    validation_rows = [
        _coverage_from_result(row)
        for row in (result.get("validation_finalists") or [])
        if isinstance(row, dict)
    ]
    provider_incomplete = (
        train["complete_month_coverage"] is False
        or bool(train["missing_months"])
        or any(
            row["complete_month_coverage"] is False or bool(row["missing_months"])
            for row in validation_rows
        )
    )
    short_train_history = bool(train["row_count"]) and not train["long_horizon_qualified"]

    evidence = result.get("model_selection_evidence") or {}
    pbo = evidence.get("cscv_pbo") or {}
    spa = evidence.get("hansen_spa") or {}
    pbo_reason = str(pbo.get("reason") or "")
    spa_reason = str(spa.get("reason") or "")
    candidate_diversity_limited = (
        not pbo.get("available")
        and pbo_reason == "CSCV_requires_three_candidates_and_even_slices"
    )
    statistical_observation_limited = (
        not spa.get("available")
        and spa_reason == "SPA_requires_at_least_30_return_observations"
    )

    if provider_incomplete:
        state = "PROVIDER_DATA_INCOMPLETE"
    elif short_train_history:
        state = "LIFECYCLE_LIMITED_SHORT_TRAIN_HISTORY"
    else:
        state = "DATA_READY"

    return {
        "state": state,
        "provider_data_incomplete": provider_incomplete,
        "short_train_history": short_train_history,
        "candidate_diversity_limited": candidate_diversity_limited,
        "statistical_observation_limited": statistical_observation_limited,
        "train": train,
        "validation_complete_months": all(
            row["complete_month_coverage"] is not False and not row["missing_months"]
            for row in validation_rows
        ),
        "validation_finalist_count": len(validation_rows),
        "pbo_unavailable_reason": pbo_reason or None,
        "spa_unavailable_reason": spa_reason or None,
        "interpretation": (
            "DATA_LIMITATION_NOT_STRATEGY_FAILURE"
            if provider_incomplete or short_train_history
            else "STRATEGY_GATES_EVALUABLE"
        ),
    }


def summarize(input_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    bottlenecks: Counter[str] = Counter()
    data_states: Counter[str] = Counter()
    model_selection_states: dict[str, Counter[str]] = {
        "cscv_pbo": Counter(),
        "hansen_spa": Counter(),
    }
    eligible_count = 0

    for path in sorted(input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        stock_code = str(payload.get("stock_code") or path.stem).upper()
        result = payload.get("result") or {}
        promotion = result.get("promotion_eligibility") or {}
        reasons = [str(reason) for reason in promotion.get("reasons") or []]
        eligible = bool(promotion.get("eligible_for_one_shot_holdout"))
        eligible_count += int(eligible)

        model_states = _classify_model_selection(result)
        for gate, state in model_states.items():
            model_selection_states[gate][state] += 1

        data_readiness = _classify_data_readiness(result)
        data_states[data_readiness["state"]] += 1

        normalized_reasons: list[str] = []
        for reason in reasons:
            model_gate = MODEL_SELECTION_REASON_MAP.get(reason)
            if model_gate:
                normalized = f"{model_gate}_{model_states[model_gate]}"
            else:
                normalized = reason
            normalized_reasons.append(normalized)
            bottlenecks[normalized] += 1

        rows.append(
            {
                "stock_code": stock_code,
                "eligible_for_one_shot_holdout": eligible,
                "raw_reasons": reasons,
                "normalized_reasons": normalized_reasons,
                "model_selection_state": model_states,
                "data_readiness": data_readiness,
            }
        )

    ranked = [
        {"reason": reason, "symbol_count": count}
        for reason, count in sorted(
            bottlenecks.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    symbol_count = len(rows)
    provider_incomplete_count = sum(
        row["data_readiness"]["provider_data_incomplete"] for row in rows
    )
    lifecycle_limited_count = sum(
        row["data_readiness"]["short_train_history"] for row in rows
    )
    diversity_limited_count = sum(
        row["data_readiness"]["candidate_diversity_limited"] for row in rows
    )
    return {
        "schema_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol_count": symbol_count,
        "eligible_symbol_count": eligible_count,
        "blocked_symbol_count": symbol_count - eligible_count,
        "data_readiness_state_counts": dict(sorted(data_states.items())),
        "provider_data_incomplete_symbol_count": provider_incomplete_count,
        "lifecycle_limited_symbol_count": lifecycle_limited_count,
        "candidate_diversity_limited_symbol_count": diversity_limited_count,
        "data_failure_policy": (
            "Provider/lifecycle data limitations are reported separately and must "
            "not be interpreted as evidence that a strategy itself failed."
        ),
        "top_bottlenecks": ranked,
        "model_selection_state_counts": {
            gate: dict(sorted(states.items()))
            for gate, states in model_selection_states.items()
        },
        "research_priority_observer": [
            item["reason"] for item in ranked[:5]
        ],
        "feedback_policy": (
            "OBSERVATION_ONLY: validation/holdout diagnostics must not feed "
            "candidate generation or train-memory adaptation"
        ),
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize promotion-gate bottlenecks across daily research shards"
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of-date", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = summarize(args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "symbol_count": payload["symbol_count"],
                "eligible_symbol_count": payload["eligible_symbol_count"],
                "provider_data_incomplete_symbol_count": payload[
                    "provider_data_incomplete_symbol_count"
                ],
                "lifecycle_limited_symbol_count": payload[
                    "lifecycle_limited_symbol_count"
                ],
                "top_bottleneck": (
                    payload["top_bottlenecks"][0]
                    if payload["top_bottlenecks"]
                    else None
                ),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
