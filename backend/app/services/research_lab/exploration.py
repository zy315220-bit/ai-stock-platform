"""Pre-registered, bounded alpha exploration using existing execution parameters.

No validation/regime/holdout metrics enter this catalog or its ordering. Keeping
the parameter-signature schema unchanged preserves all earlier trial history:
this extends the catalog without changing what an existing strategy means.
"""
from __future__ import annotations

from hashlib import sha256
from itertools import product
import json
from typing import Iterable

from .models import ResearchCandidate


EXPLORATION_POLICY_SCHEMA = "alpha-duration-exposure-exploration-v1"
HOLDING_DAYS = (5, 10, 15, 20, 30, 40, 60, 80, 100, 120, 160, 200, 252)
ATR_TARGETS = (0.75, 1.0, 1.5, 2.0, 3.0)
MAX_POSITION_FRACTIONS = (0.50, 0.65, 0.75, 0.85)


def _variant(parent: ResearchCandidate, **overrides: object) -> ResearchCandidate:
    parameters = {**parent.parameters, **overrides}
    identity = json.dumps(
        {"family": parent.strategy_family, "parameters": parameters},
        sort_keys=True, separators=(",", ":"),
    )
    return ResearchCandidate(
        candidate_id=f"alpha-parameter-{sha256(identity.encode()).hexdigest()[:16]}",
        strategy_family=parent.strategy_family,
        parameters=parameters,
        parent_id=parent.candidate_id,
        hypothesis="Train-only duration/exposure exploration; technical entry rule preserved",
    )


def generate_alpha_exploration(seeds: Iterable[ResearchCandidate]) -> list[ResearchCandidate]:
    candidates = []
    for seed in seeds:
        if "time" not in str(seed.parameters.get("exit_mode", "")):
            continue
        if seed.parameters.get("atr_target_percent") is None:
            variants = ({"max_holding_days": days} for days in HOLDING_DAYS)
        else:
            variants = (
                {"max_holding_days": days, "atr_target_percent": target,
                 "max_position_fraction": fraction}
                for days, target, fraction in product(
                    HOLDING_DAYS, ATR_TARGETS, MAX_POSITION_FRACTIONS,
                )
                if fraction >= float(seed.parameters.get("min_position_fraction", 0.25))
            )
        for overrides in variants:
            candidate = _variant(seed, **overrides)
            if candidate.parameters != seed.parameters:
                candidates.append(candidate)
    return sorted(candidates, key=lambda candidate: candidate.candidate_id)


def alpha_parameter_neighbors(parent: ResearchCandidate) -> list[ResearchCandidate]:
    """Move real alpha parameters; neutral score thresholds are never mutated."""
    dimensions = [("max_holding_days", HOLDING_DAYS)]
    if parent.parameters.get("atr_target_percent") is not None:
        dimensions.extend([
            ("atr_target_percent", ATR_TARGETS),
            ("max_position_fraction", MAX_POSITION_FRACTIONS),
        ])
    children = []
    for name, values in dimensions:
        current = float(parent.parameters[name])
        lower = [value for value in values if value < current]
        upper = [value for value in values if value > current]
        for value in ([max(lower)] if lower else []) + ([min(upper)] if upper else []):
            if name == "max_position_fraction" and value < float(parent.parameters.get("min_position_fraction", 0.25)):
                continue
            children.append(_variant(parent, **{name: value}))
    return children
