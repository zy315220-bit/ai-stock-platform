from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.services.backtest.engine import backtest_stock
from app.services.research_lab.autoresearch import (
    ResearchSession,
    run_autoresearch,
)
from app.services.research_lab.evidence import (
    assess_validation_evidence,
)
from app.services.research_lab.evolution import (
    generate_parameter_candidates,
)
from app.services.research_lab.market_regimes import (
    MarketRegime,
    MarketRegimeMatrix,
    load_point_in_time_benchmark_returns,
    run_market_regime_validation,
)
from app.services.research_lab.models import (
    ExperimentDecision,
    ExperimentResult,
    ResearchCandidate,
)
from app.services.research_lab.runner import (
    run_research_batch,
    serialize_result,
)
from app.services.research_lab.splits import build_research_split
from app.services.research_lab.statistical_evidence import (
    cscv_probability_of_backtest_overfitting,
    deflated_sharpe_evidence,
    hansen_spa_test,
)
from app.services.research_lab.walk_forward import (
    WalkForwardEvidence,
    run_walk_forward_validation,
)

router = APIRouter()


def _rotated_parameter_candidates(candidate_offset: int) -> list[ResearchCandidate]:
    """Rotate the deterministic grid without using validation feedback.

    Daily unattended research uses a date-derived offset so a bounded run can
    explore a different region of the fixed candidate universe.  The ordering
    change is train-only and therefore does not leak validation or holdout data
    back into candidate generation.
    """
    candidates = generate_parameter_candidates()
    if not candidates:
        return []
    offset = candidate_offset % len(candidates)
    return candidates[offset:] + candidates[:offset]


def _unique_training_results(
    session: ResearchSession,
) -> list[ExperimentResult]:
    """Return the strongest train-only result for each exact parameter set."""
    unique: dict[tuple[tuple[str, str], ...], ExperimentResult] = {}
    for round_ in session.rounds:
        for result in round_.evaluated:
            signature = tuple(
                sorted(
                    (key, repr(value))
                    for key, value in result.candidate.parameters.items()
                )
            )
            existing = unique.get(signature)
            if existing is None or result.research_score > existing.research_score:
                unique[signature] = result
    return sorted(
        unique.values(),
        key=lambda item: item.research_score,
        reverse=True,
    )


def _diverse_training_survivors(
    ranked: list[ExperimentResult],
    limit: int,
) -> list[ExperimentResult]:
    """Select high-scoring finalists with distinct realized return paths."""
    selected: list[ExperimentResult] = []
    behavior_signatures: set[str] = set()
    for result in ranked:
        if result.decision is ExperimentDecision.DISCARD:
            continue
        returns = result.validation_metrics.get("_daily_excess_returns", [])
        if returns:
            signature_payload = json.dumps(
                [round(float(value), 10) for value in returns],
                separators=(",", ":"),
            )
        else:
            signature_payload = json.dumps(
                result.candidate.parameters,
                sort_keys=True,
                separators=(",", ":"),
            )
        signature = hashlib.sha256(
            signature_payload.encode("utf-8")
        ).hexdigest()
        if signature in behavior_signatures:
            continue
        behavior_signatures.add(signature)
        selected.append(result)
        if len(selected) >= limit:
            break
    return selected


def _serialize_matrix(matrix: MarketRegimeMatrix) -> dict[str, Any]:
    return {
        "candidate_id": matrix.candidate_id,
        "benchmark_code": matrix.benchmark_code,
        "slices": list(matrix.slices),
        "by_regime": matrix.by_regime,
        "robustness": matrix.robustness,
        "data_fingerprints": list(matrix.data_fingerprints),
    }


def _serialize_walk_forward(
    evidence: WalkForwardEvidence | None,
) -> dict[str, Any] | None:
    if evidence is None:
        return None
    return {
        "candidate_id": evidence.candidate_id,
        "slices": list(evidence.slices),
        "aggregate": evidence.aggregate,
    }


def execute_research_pipeline(
    *,
    stock_code: str,
    start_date: date,
    end_date: date,
    max_generations: int = 3,
    max_experiments: int = 40,
    min_validation_trades: int = 8,
    validation_finalists: int = 5,
    walk_forward_slices: int = 3,
    regime_candidate_count: int = 3,
    regime_slices: int = 6,
    min_regime_trades: int = 2,
    candidate_offset: int = 0,
    initial_candidates: list[ResearchCandidate] | None = None,
    excluded_training_signatures: set[str] | frozenset[str] | None = None,
    training_memory_audit: dict[str, Any] | None = None,
    prior_train_trial_sharpes: tuple[float, ...] = (),
) -> dict[str, object]:
    """Run train search, validation finals and a no-holdout regime tournament."""
    try:
        split = build_research_split(start_date, end_date)
        session = run_autoresearch(
            stock_code,
            split,
            (
                initial_candidates
                if initial_candidates is not None
                else _rotated_parameter_candidates(candidate_offset)
            ),
            backtest_fn=backtest_stock,
            max_generations=max_generations,
            max_experiments=max_experiments,
            min_validation_trades=min_validation_trades,
            excluded_parameter_signatures=(
                excluded_training_signatures or set()
            ),
        )

        train_ranked = _unique_training_results(session)
        train_survivors = _diverse_training_survivors(
            train_ranked,
            validation_finalists,
        )
        validation_results = run_research_batch(
            stock_code,
            split,
            [result.candidate for result in train_survivors],
            backtest_fn=backtest_stock,
            min_validation_trades=min_validation_trades,
            evaluation_phase="validation",
        )
        current_trial_sharpes = [
            float(statistics.get("period_sharpe_ratio", 0.0))
            for result in train_ranked
            if (
                statistics := result.validation_metrics.get(
                    "statistical_evidence",
                    {},
                )
            ).get("available")
        ]
        trial_sharpes = [
            float(value) for value in prior_train_trial_sharpes
        ] + current_trial_sharpes
        validation_results = [
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
            for result in validation_results
        ]
        excess_return_matrix = {
            result.candidate.candidate_id: result.validation_metrics.get(
                "_daily_excess_returns",
                [],
            )
            for result in validation_results
        }
        pbo_evidence = cscv_probability_of_backtest_overfitting(
            excess_return_matrix,
            slice_count=8,
        )
        spa_evidence = hansen_spa_test(excess_return_matrix)

        validation_survivors = [
            result
            for result in validation_results
            if result.decision is not ExperimentDecision.DISCARD
        ][:regime_candidate_count]
        benchmark_cache: dict[tuple[str, str], dict[str, Any]] = {}
        regime_estimate_cache: dict[
            str,
            tuple[MarketRegime, dict[str, Any]],
        ] = {}
        regime_return_series = (
            load_point_in_time_benchmark_returns("0050", split)
            if validation_survivors
            else None
        )
        tournament: list[
            tuple[ExperimentResult, MarketRegimeMatrix]
        ] = []
        for validation_result in validation_survivors:
            matrix = run_market_regime_validation(
                stock_code,
                split,
                validation_result.candidate,
                backtest_fn=backtest_stock,
                benchmark_backtest_fn=backtest_stock,
                slice_count=regime_slices,
                min_completed_trades_per_regime=min_regime_trades,
                benchmark_cache=benchmark_cache,
                regime_estimate_cache=regime_estimate_cache,
                regime_return_series=regime_return_series,
            )
            tournament.append((validation_result, matrix))

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
        selected_result = tournament[0][0] if tournament else None
        selected_matrix = tournament[0][1] if tournament else None

        walk_forward = None
        if selected_result is not None:
            walk_forward = run_walk_forward_validation(
                stock_code,
                split,
                selected_result.candidate,
                backtest_fn=backtest_stock,
                slice_count=walk_forward_slices,
                min_total_completed_trades=min_validation_trades,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    eligibility_reasons: list[str] = []
    if selected_result is None or selected_matrix is None:
        eligibility_reasons.append("no_validation_survivor")
    else:
        if selected_result.decision is not ExperimentDecision.HOLDOUT_READY:
            eligibility_reasons.append("validation_gate_not_ready")
        if not selected_matrix.robustness.get(
            "robust_across_required_regimes"
        ):
            eligibility_reasons.append("bull_bear_robustness_failed")
    if walk_forward is not None:
        evidence = walk_forward.aggregate.get("evidence_quality", {})
        if not evidence.get("sample_sufficient"):
            eligibility_reasons.append("walk_forward_sample_insufficient")
        if float(
            walk_forward.aggregate.get("positive_slice_ratio", 0.0)
            or 0.0
        ) < 0.5:
            eligibility_reasons.append("walk_forward_stability_failed")
    if selected_result is not None:
        statistics = selected_result.validation_metrics.get(
            "statistical_evidence",
            {},
        )
        deflated = selected_result.validation_metrics.get(
            "deflated_sharpe",
            {},
        )
        if not statistics.get("statistical_quality_pass"):
            eligibility_reasons.append("psr_mintrl_bootstrap_failed")
        if not deflated.get("multiple_testing_pass"):
            eligibility_reasons.append("deflated_sharpe_failed")
    if not pbo_evidence.get("overfitting_risk_pass"):
        eligibility_reasons.append("cscv_pbo_failed_or_unavailable")
    if not spa_evidence.get("superior_predictive_ability_pass"):
        eligibility_reasons.append("hansen_spa_failed_or_unavailable")

    rounds = [
        {
            "generation": round_.generation,
            "evaluation_phase": "train",
            "evaluated_count": len(round_.evaluated),
            "survivor_count": len(round_.survivors),
            "evaluated": [
                serialize_result(result) for result in round_.evaluated
            ],
            "survivors": [asdict(candidate) for candidate in round_.survivors],
        }
        for round_ in session.rounds
    ]
    tournament_payload = [
        {
            "rank": rank,
            "validation_result": serialize_result(validation_result),
            "market_regime_matrix": _serialize_matrix(matrix),
        }
        for rank, (validation_result, matrix) in enumerate(
            tournament,
            start=1,
        )
    ]
    promotion_eligible = not eligibility_reasons
    identity_results = [
        result
        for round_ in session.rounds
        for result in round_.evaluated
    ] + validation_results
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
            "stock_code": stock_code.strip().upper(),
            "split": asdict(split),
            "candidate_ids": [
                result.candidate.candidate_id for result in identity_results
            ],
            "data_fingerprints": data_fingerprints,
            "max_generations": max_generations,
            "max_experiments": max_experiments,
            "candidate_offset": candidate_offset,
            "training_memory_id": (
                (training_memory_audit or {}).get("prior_memory_id")
            ),
            "statistical_gate_schema": "research-integrity-v2",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    research_run_id = hashlib.sha256(
        identity_payload.encode("utf-8")
    ).hexdigest()[:24]

    return {
        "research_run_id": research_run_id,
        "data_fingerprints": data_fingerprints,
        "stock_code": stock_code.strip().upper(),
        "experiments_run": session.experiments_run,
        "evaluated_parameter_signatures": list(
            session.evaluated_parameter_signatures
        ),
        "skipped_duplicate_count": session.skipped_duplicate_count,
        "generations_run": len(session.rounds),
        "stopped_reason": session.stopped_reason,
        "training_best_result": (
            serialize_result(session.best_result)
            if session.best_result
            else None
        ),
        "validation_finalists": [
            serialize_result(result) for result in validation_results
        ],
        "best_result": (
            serialize_result(selected_result) if selected_result else None
        ),
        "selected_candidate": (
            asdict(selected_result.candidate) if selected_result else None
        ),
        "market_regime_tournament": tournament_payload,
        "model_selection_evidence": {
            "cscv_pbo": pbo_evidence,
            "hansen_spa": spa_evidence,
            "trial_count_for_deflated_sharpe": len(trial_sharpes),
            "current_run_trial_count_for_deflated_sharpe": len(
                current_trial_sharpes
            ),
        },
        "walk_forward_matrix": _serialize_walk_forward(walk_forward),
        "rounds": rounds,
        "promotion_eligibility": {
            "eligible_for_one_shot_holdout": promotion_eligible,
            "reasons": eligibility_reasons,
            "holdout_opened": False,
        },
        "research_audit": {
            "pipeline": [
                "TRAIN_AUTORESEARCH",
                "VALIDATION_FINALISTS",
                "BULL_BEAR_SIDEWAYS_AUDIT",
                "PSR_DSR_MINTRL_STATIONARY_BOOTSTRAP",
                "CSCV_PBO_AND_HANSEN_SPA",
                "WALK_FORWARD_VALIDATION",
                "LOCKED_FINAL_HOLDOUT",
            ],
            "candidate_generation": (
                "deterministic_diversified_grid_then_adaptive_"
                "numeric_and_structural_mutation"
            ),
            "selection": (
                "train_survivors_then_validation_then_regime_robustness"
            ),
            "training_used_for_search": True,
            "validation_used_during_adaptive_search": False,
            "holdout_used_during_search": False,
            "walk_forward_holdout_used": False,
            "market_regime_holdout_used": False,
            "market_regime_labels": (
                "point_in_time_Hamilton_0050_model_never_a_trading_signal"
            ),
            "validation_policy": {
                "min_completed_trades": min_validation_trades,
                "finalist_count": validation_finalists,
                "walk_forward_slices": walk_forward_slices,
                "regime_slices": regime_slices,
                "min_completed_trades_per_required_regime": (
                    min_regime_trades
                ),
            },
            "bounded_by": {
                "max_generations": max_generations,
                "max_experiments": max_experiments,
                "regime_candidate_count": regime_candidate_count,
                "candidate_offset": candidate_offset,
            },
            "training_memory": {
                **(training_memory_audit or {}),
                "current_run_new_signature_count": len(
                    session.evaluated_parameter_signatures
                ),
                "current_run_duplicate_skip_count": (
                    session.skipped_duplicate_count
                ),
                "validation_feedback_used": False,
                "holdout_feedback_used": False,
            },
        },
        "holdout_status": "LOCKED_REQUIRES_PROMOTION_GATE",
        "split": {
            "train": [split.train_start, split.train_end],
            "validation": [
                split.validation_start,
                split.validation_end,
            ],
            "holdout": [split.holdout_start, split.holdout_end],
        },
    }


@router.post("/run")
def run_research(
    stock_code: str = Query(..., min_length=4, max_length=10),
    start_date: date = Query(...),
    end_date: date = Query(...),
    max_generations: int = Query(3, ge=1, le=10),
    # The public/Vercel on-demand endpoint is deliberately capped at the same
    # 60-experiment maximum exposed by the UI. Deep 64-experiment autonomous
    # research runs directly on isolated GitHub Actions runners instead, so a
    # web request cannot consume the production function for a 200-run batch.
    max_experiments: int = Query(40, ge=1, le=60),
    min_validation_trades: int = Query(8, ge=1, le=100),
    validation_finalists: int = Query(5, ge=1, le=5),
    walk_forward_slices: int = Query(3, ge=2, le=8),
    regime_candidate_count: int = Query(3, ge=1, le=3),
    regime_slices: int = Query(6, ge=3, le=8),
    min_regime_trades: int = Query(2, ge=1, le=50),
    candidate_offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> dict[str, object]:
    return execute_research_pipeline(
        stock_code=stock_code,
        start_date=start_date,
        end_date=end_date,
        max_generations=max_generations,
        max_experiments=max_experiments,
        min_validation_trades=min_validation_trades,
        validation_finalists=validation_finalists,
        walk_forward_slices=walk_forward_slices,
        regime_candidate_count=regime_candidate_count,
        regime_slices=regime_slices,
        min_regime_trades=min_regime_trades,
        candidate_offset=candidate_offset,
    )
