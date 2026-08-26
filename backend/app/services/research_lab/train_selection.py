from __future__ import annotations

import json
import math
from typing import Iterable

from .models import ExperimentDecision, ExperimentResult


TRAIN_SELECTION_SCHEMA = "train-multiobjective-frontier-v2"


def _finite(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _proxy(result: ExperimentResult) -> dict[str, object]:
    value = result.validation_metrics.get("train_active_robustness_proxy") or {}
    return value if isinstance(value, dict) else {}


def _parameter_identity(result: ExperimentResult) -> str:
    return json.dumps(
        {
            "strategy_family": result.candidate.strategy_family,
            "parameters": result.candidate.parameters,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def train_selection_metrics(result: ExperimentResult) -> dict[str, float | str]:
    """Expose only Train-derived objectives used by adaptive selection."""
    proxy = _proxy(result)
    return {
        "schema": TRAIN_SELECTION_SCHEMA,
        "research_score": _finite(result.research_score),
        "annualized_mean_excess_percent": _finite(
            proxy.get("annualized_mean_excess_percent")
        ),
        "positive_slice_ratio": _finite(proxy.get("positive_slice_ratio")),
        "overall_information_ratio": _finite(
            proxy.get("overall_information_ratio")
        ),
        "median_slice_information_ratio": _finite(
            proxy.get("median_slice_information_ratio")
        ),
        "worst_slice_information_ratio": _finite(
            proxy.get("worst_slice_information_ratio")
        ),
        "dependence_adjusted_active_t_statistic": _finite(
            proxy.get("dependence_adjusted_active_t_statistic")
        ),
    }


def _score_key(result: ExperimentResult) -> tuple[float, ...]:
    metrics = train_selection_metrics(result)
    return (
        _finite(metrics["research_score"]),
        _finite(metrics["dependence_adjusted_active_t_statistic"]),
        _finite(metrics["annualized_mean_excess_percent"]),
    )


def _active_significance_key(result: ExperimentResult) -> tuple[float, ...]:
    metrics = train_selection_metrics(result)
    return (
        _finite(metrics["dependence_adjusted_active_t_statistic"]),
        _finite(metrics["positive_slice_ratio"]),
        _finite(metrics["annualized_mean_excess_percent"]),
        _finite(metrics["research_score"]),
    )


def _persistent_alpha_key(result: ExperimentResult) -> tuple[float, ...]:
    metrics = train_selection_metrics(result)
    return (
        _finite(metrics["positive_slice_ratio"]),
        _finite(metrics["worst_slice_information_ratio"]),
        _finite(metrics["median_slice_information_ratio"]),
        _finite(metrics["overall_information_ratio"]),
        _finite(metrics["research_score"]),
    )


def _mean_alpha_key(result: ExperimentResult) -> tuple[float, ...]:
    metrics = train_selection_metrics(result)
    return (
        _finite(metrics["annualized_mean_excess_percent"]),
        _finite(metrics["overall_information_ratio"]),
        _finite(metrics["positive_slice_ratio"]),
        _finite(metrics["research_score"]),
    )


def _family_champions(results: list[ExperimentResult]) -> list[ExperimentResult]:
    by_family: dict[str, ExperimentResult] = {}
    for result in results:
        family = result.candidate.strategy_family
        existing = by_family.get(family)
        if existing is None or _active_significance_key(result) > _active_significance_key(
            existing
        ):
            by_family[family] = result
    return sorted(
        by_family.values(),
        key=lambda result: (
            _active_significance_key(result),
            _score_key(result),
        ),
        reverse=True,
    )


def select_train_multiobjective(
    results: Iterable[ExperimentResult],
    *,
    limit: int,
) -> list[ExperimentResult]:
    """Select a deterministic Train-only frontier across complementary objectives.

    The first pick always honors the established Train research score. Remaining
    slots round-robin persistent active alpha, dependence-aware active evidence,
    mean active return, and strategy-family diversity. No Validation or Final
    Holdout metric is read here, so this can safely drive evolution and memory.
    """
    if limit <= 0:
        return []
    eligible = [
        result
        for result in results
        if result.decision is not ExperimentDecision.DISCARD
        and result.evaluation_phase == "train"
    ]
    if not eligible:
        return []

    queues = [
        sorted(eligible, key=_score_key, reverse=True),
        sorted(eligible, key=_active_significance_key, reverse=True),
        sorted(eligible, key=_persistent_alpha_key, reverse=True),
        sorted(eligible, key=_mean_alpha_key, reverse=True),
        _family_champions(eligible),
    ]

    selected: list[ExperimentResult] = []
    seen: set[str] = set()
    while len(selected) < limit:
        progressed = False
        for queue in queues:
            while queue and _parameter_identity(queue[0]) in seen:
                queue.pop(0)
            if not queue:
                continue
            result = queue.pop(0)
            identity = _parameter_identity(result)
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(result)
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def train_target_reached(
    result: ExperimentResult | None,
    *,
    target_score: float,
) -> bool:
    """Require robust Train-only active evidence before stopping search early."""
    if result is None or result.evaluation_phase != "train":
        return False
    if result.decision is not ExperimentDecision.HOLDOUT_READY:
        return False
    if result.research_score < target_score:
        return False
    proxy = _proxy(result)
    if not proxy.get("available"):
        return False
    return bool(
        _finite(proxy.get("positive_slice_ratio")) >= 0.80
        and _finite(proxy.get("annualized_mean_excess_percent")) > 0.0
        and _finite(proxy.get("dependence_adjusted_active_t_statistic")) >= 1.50
        and _finite(proxy.get("worst_slice_information_ratio")) > -0.25
    )
