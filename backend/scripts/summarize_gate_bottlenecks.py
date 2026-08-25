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


def summarize(input_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    bottlenecks: Counter[str] = Counter()
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
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol_count": symbol_count,
        "eligible_symbol_count": eligible_count,
        "blocked_symbol_count": symbol_count - eligible_count,
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
