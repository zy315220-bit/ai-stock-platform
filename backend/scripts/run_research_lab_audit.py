from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from app.services.backtest.engine import backtest_stock
from app.services.research_lab.autoresearch import run_autoresearch
from app.services.research_lab.evolution import generate_parameter_candidates
from app.services.research_lab.market_regimes import (
    load_point_in_time_benchmark_returns,
    run_market_regime_validation,
)
from app.services.research_lab.models import ExperimentDecision, ResearchSplit
from app.services.research_lab.promotion import run_holdout_gate
from app.services.research_lab.runner import (
    run_research_batch,
    serialize_result,
)
from app.services.research_lab.statistical_evidence import (
    cscv_probability_of_backtest_overfitting,
    deflated_sharpe_evidence,
    hansen_spa_test,
)
from app.services.research_lab.walk_forward import (
    run_walk_forward_validation,
)

STOCK_CODE = "2330"
SPLIT = ResearchSplit(
    "2020-01-01",
    "2022-12-31",
    "2023-01-01",
    "2024-12-31",
    "2025-01-01",
    "2025-12-31",
)
OUT = Path("research_artifacts/research_lab_2330_latest.json")
MIN_TRADES = 4


def main() -> None:
    session = run_autoresearch(
        STOCK_CODE,
        SPLIT,
        generate_parameter_candidates(),
        backtest_fn=backtest_stock,
        max_generations=4,
        max_experiments=48,
        top_k=3,
        target_score=75.0,
        min_validation_trades=MIN_TRADES,
    )
    train_results = sorted(
        (
            result
            for round_ in session.rounds
            for result in round_.evaluated
            if result.decision is not ExperimentDecision.DISCARD
        ),
        key=lambda result: result.research_score,
        reverse=True,
    )
    diverse_training_results = []
    behavior_signatures = set()
    for result in train_results:
        returns = result.validation_metrics.get("_daily_excess_returns", [])
        signature_payload = json.dumps(
            [round(float(value), 10) for value in returns]
            if returns
            else result.candidate.parameters,
            sort_keys=not bool(returns),
            separators=(",", ":"),
        )
        signature = hashlib.sha256(
            signature_payload.encode("utf-8")
        ).hexdigest()
        if signature in behavior_signatures:
            continue
        behavior_signatures.add(signature)
        diverse_training_results.append(result)
        if len(diverse_training_results) >= 5:
            break
    finalists = run_research_batch(
        STOCK_CODE,
        SPLIT,
        [result.candidate for result in diverse_training_results],
        backtest_fn=backtest_stock,
        min_validation_trades=MIN_TRADES,
        evaluation_phase="validation",
    )
    all_training_results = [
        result
        for round_ in session.rounds
        for result in round_.evaluated
    ]
    trial_sharpes = [
        float(statistics.get("period_sharpe_ratio", 0.0))
        for result in all_training_results
        if (
            statistics := result.validation_metrics.get(
                "statistical_evidence",
                {},
            )
        ).get("available")
    ]
    finalists = [
        replace(
            result,
            validation_metrics={
                **result.validation_metrics,
                "deflated_sharpe": deflated_sharpe_evidence(
                    result.validation_metrics.get(
                        "statistical_evidence",
                        {},
                    ),
                    trial_sharpes,
                ),
            },
        )
        for result in finalists
    ]
    excess_returns = {
        result.candidate.candidate_id: result.validation_metrics.get(
            "_daily_excess_returns",
            [],
        )
        for result in finalists
    }
    pbo_evidence = cscv_probability_of_backtest_overfitting(excess_returns)
    spa_evidence = hansen_spa_test(excess_returns)
    validation_survivors = [
        result
        for result in finalists
        if result.decision is not ExperimentDecision.DISCARD
    ]

    benchmark_cache = {}
    regime_estimate_cache = {}
    regime_return_series = (
        load_point_in_time_benchmark_returns("0050", SPLIT)
        if validation_survivors
        else None
    )
    tournament = []
    for result in validation_survivors[:3]:
        matrix = run_market_regime_validation(
            STOCK_CODE,
            SPLIT,
            result.candidate,
            backtest_fn=backtest_stock,
            benchmark_backtest_fn=backtest_stock,
            slice_count=6,
            min_completed_trades_per_regime=1,
            benchmark_cache=benchmark_cache,
            regime_estimate_cache=regime_estimate_cache,
            regime_return_series=regime_return_series,
        )
        tournament.append((result, matrix))
    tournament.sort(
        key=lambda item: (
            bool(
                item[1].robustness.get(
                    "robust_across_required_regimes"
                )
            ),
            float(item[1].robustness.get("robustness_score", 0.0)),
            item[0].research_score,
        ),
        reverse=True,
    )

    selected = tournament[0][0] if tournament else None
    selected_matrix = tournament[0][1] if tournament else None
    walk_forward = None
    if selected is not None:
        walk_forward = run_walk_forward_validation(
            STOCK_CODE,
            SPLIT,
            selected.candidate,
            backtest_fn=backtest_stock,
            slice_count=3,
            min_total_completed_trades=MIN_TRADES,
        )

    promotion_ready = bool(
        selected
        and selected_matrix
        and walk_forward
        and selected.decision is ExperimentDecision.HOLDOUT_READY
        and selected_matrix.robustness.get(
            "robust_across_required_regimes"
        )
        and walk_forward.aggregate.get("evidence_quality", {}).get(
            "sample_sufficient"
        )
        and float(
            walk_forward.aggregate.get("positive_slice_ratio", 0.0)
            or 0.0
        )
        >= 0.5
        and selected.validation_metrics.get(
            "statistical_evidence",
            {},
        ).get("statistical_quality_pass")
        and selected.validation_metrics.get(
            "deflated_sharpe",
            {},
        ).get("multiple_testing_pass")
        and pbo_evidence.get("overfitting_risk_pass")
        and spa_evidence.get("superior_predictive_ability_pass")
    )

    promotion = None
    if promotion_ready and selected is not None and selected_matrix is not None:
        promotion = asdict(
            run_holdout_gate(
                STOCK_CODE,
                SPLIT,
                selected,
                regime_robustness=selected_matrix.robustness,
                model_selection_evidence={
                    "cscv_pbo": pbo_evidence,
                    "hansen_spa": spa_evidence,
                },
                backtest_fn=backtest_stock,
            )
        )
    else:
        promotion = {
            "promoted": False,
            "holdout_opened": False,
            "reason": (
                "train, validation, market-regime and walk-forward gates "
                "did not all qualify; final holdout remains untouched"
            ),
        }

    identity_results = all_training_results + finalists
    data_fingerprints = sorted(
        {
            str(fingerprint)
            for result in identity_results
            if (
                fingerprint := result.validation_metrics.get(
                    "data_fingerprint"
                )
            )
        }
        | {
            fingerprint
            for _, matrix in tournament
            for fingerprint in matrix.data_fingerprints
        }
    )
    identity_payload = json.dumps(
        {
            "stock_code": STOCK_CODE,
            "split": asdict(SPLIT),
            "candidate_ids": [
                result.candidate.candidate_id for result in identity_results
            ],
            "data_fingerprints": data_fingerprints,
            "statistical_gate_schema": "research-integrity-v2",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    research_run_id = hashlib.sha256(
        identity_payload.encode("utf-8")
    ).hexdigest()[:24]
    payload = {
        "schema_version": 2,
        "research_run_id": research_run_id,
        "data_fingerprints": data_fingerprints,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stock_code": STOCK_CODE,
        "split": asdict(SPLIT),
        "audit_invariants": {
            "adaptive_search_phase": "train",
            "validation_used_during_adaptive_search": False,
            "market_regime_holdout_used": False,
            "walk_forward_holdout_used": False,
            "regime_labels_point_in_time": True,
            "holdout_opened_only_after_all_gates": True,
        },
        "experiments_run": session.experiments_run,
        "stopped_reason": session.stopped_reason,
        "rounds": [
            {
                "generation": round_.generation,
                "evaluated": [
                    serialize_result(result) for result in round_.evaluated
                ],
                "survivors": [
                    asdict(candidate) for candidate in round_.survivors
                ],
            }
            for round_ in session.rounds
        ],
        "training_best": (
            serialize_result(session.best_result)
            if session.best_result
            else None
        ),
        "validation_finalists": [
            serialize_result(result) for result in finalists
        ],
        "market_regime_tournament": [
            {
                "validation_result": serialize_result(result),
                "matrix": asdict(matrix),
            }
            for result, matrix in tournament
        ],
        "model_selection_evidence": {
            "trial_count_for_deflated_sharpe": len(trial_sharpes),
            "cscv_pbo": pbo_evidence,
            "hansen_spa": spa_evidence,
        },
        "selected_validation": (
            serialize_result(selected) if selected else None
        ),
        "walk_forward": (
            asdict(walk_forward) if walk_forward else None
        ),
        "promotion_ready": promotion_ready,
        "promotion": promotion,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "artifact": str(OUT),
                "stock_code": STOCK_CODE,
                "experiments_run": session.experiments_run,
                "stopped_reason": session.stopped_reason,
                "training_best_score": (
                    session.best_result.research_score
                    if session.best_result
                    else None
                ),
                "selected_validation_score": (
                    selected.research_score if selected else None
                ),
                "regime_robust": (
                    selected_matrix.robustness.get(
                        "robust_across_required_regimes"
                    )
                    if selected_matrix
                    else False
                ),
                "promotion": promotion,
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
