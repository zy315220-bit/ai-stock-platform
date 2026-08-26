from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def summarize(input_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    pbo_available = 0
    pbo_pass = 0
    spa_available = 0
    spa_pass = 0
    pbo_unavailable_reasons: dict[str, int] = {}
    spa_unavailable_reasons: dict[str, int] = {}

    for path in sorted(input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        stock_code = str(payload.get("stock_code") or path.stem).upper()
        result = payload.get("result") or {}
        evidence = result.get("model_selection_evidence") or {}
        pbo = evidence.get("cscv_pbo") or {}
        spa = evidence.get("hansen_spa") or {}

        pbo_is_available = bool(pbo.get("available"))
        spa_is_available = bool(spa.get("available"))
        pbo_is_pass = bool(pbo.get("overfitting_risk_pass"))
        spa_is_pass = bool(spa.get("superior_predictive_ability_pass"))
        pbo_available += int(pbo_is_available)
        spa_available += int(spa_is_available)
        pbo_pass += int(pbo_is_pass)
        spa_pass += int(spa_is_pass)

        if not pbo_is_available:
            reason = str(pbo.get("reason") or "unknown")
            pbo_unavailable_reasons[reason] = pbo_unavailable_reasons.get(reason, 0) + 1
        if not spa_is_available:
            reason = str(spa.get("reason") or "unknown")
            spa_unavailable_reasons[reason] = spa_unavailable_reasons.get(reason, 0) + 1

        consistent_critical = (spa.get("critical_values_5pct") or {}).get("consistent")
        p_values = spa.get("p_values") or {}
        rows.append(
            {
                "stock_code": stock_code,
                "pbo": {
                    "available": pbo_is_available,
                    "pass": pbo_is_pass,
                    "probability_percent": _finite_number(
                        pbo.get("pbo_probability_percent")
                    ),
                    "candidate_count": int(pbo.get("candidate_count", 0) or 0),
                    "original_candidate_count": int(
                        pbo.get("original_candidate_count", 0) or 0
                    ),
                    "reason": pbo.get("reason"),
                },
                "spa": {
                    "available": spa_is_available,
                    "pass": spa_is_pass,
                    "method": spa.get("method"),
                    "studentization": spa.get("studentization"),
                    "p_value": _finite_number(spa.get("spa_p_value")),
                    "p_values": {
                        "lower": _finite_number(p_values.get("lower")),
                        "consistent": _finite_number(p_values.get("consistent")),
                        "upper": _finite_number(p_values.get("upper")),
                    },
                    "candidate_count": int(spa.get("candidate_count", 0) or 0),
                    "active_candidate_count": int(
                        spa.get("active_candidate_count", 0) or 0
                    ),
                    "observations": int(spa.get("observations", 0) or 0),
                    "best_candidate_id": spa.get("best_candidate_id"),
                    "best_mean_daily_excess_percent": _finite_number(
                        spa.get("best_mean_daily_excess_percent")
                    ),
                    "observed_max_studentized_statistic": _finite_number(
                        spa.get("observed_max_studentized_statistic")
                    ),
                    "critical_value_5pct_consistent": _finite_number(
                        consistent_critical
                    ),
                    "required_mean_daily_excess_percent_at_5pct": _finite_number(
                        spa.get("required_mean_daily_excess_percent_at_5pct")
                    ),
                    "additional_mean_daily_excess_percent_needed_at_5pct": _finite_number(
                        spa.get(
                            "additional_mean_daily_excess_percent_needed_at_5pct"
                        )
                    ),
                    "reason": spa.get("reason"),
                },
                "deflated_sharpe_trial_count": int(
                    evidence.get("trial_count_for_deflated_sharpe", 0) or 0
                ),
            }
        )

    pbo_ranked = sorted(
        (
            row for row in rows
            if row["pbo"]["available"]
            and row["pbo"]["probability_percent"] is not None
        ),
        key=lambda row: row["pbo"]["probability_percent"],
    )
    spa_ranked = sorted(
        (
            row for row in rows
            if row["spa"]["available"]
            and row["spa"]["p_value"] is not None
        ),
        key=lambda row: row["spa"]["p_value"],
    )

    return {
        "schema_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol_count": len(rows),
        "pbo": {
            "available_symbol_count": pbo_available,
            "pass_symbol_count": pbo_pass,
            "unavailable_symbol_count": len(rows) - pbo_available,
            "unavailable_reasons": pbo_unavailable_reasons,
            "best_by_lowest_pbo_probability": pbo_ranked[:5],
        },
        "spa": {
            "available_symbol_count": spa_available,
            "pass_symbol_count": spa_pass,
            "unavailable_symbol_count": len(rows) - spa_available,
            "unavailable_reasons": spa_unavailable_reasons,
            "best_by_lowest_p_value": spa_ranked[:5],
        },
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize CSCV/PBO and Hansen SPA evidence across daily research shards"
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
                "pbo_available": payload["pbo"]["available_symbol_count"],
                "pbo_pass": payload["pbo"]["pass_symbol_count"],
                "spa_available": payload["spa"]["available_symbol_count"],
                "spa_pass": payload["spa"]["pass_symbol_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
