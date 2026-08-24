from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.research_lab.causal_regimes import (
    estimate_hamilton_regime_as_of,
)


def _returns() -> pd.Series:
    rng = np.random.default_rng(31)
    dates = pd.bdate_range("2016-01-01", "2024-12-31")
    values = np.concatenate(
        [
            rng.normal(0.0008, 0.006, len(dates) // 3),
            rng.normal(-0.0007, 0.009, len(dates) // 3),
            rng.normal(0.0001, 0.004, len(dates) - 2 * (len(dates) // 3)),
        ]
    )
    return pd.Series(values, index=dates)


def test_hamilton_regime_estimate_is_strictly_point_in_time() -> None:
    returns = _returns()
    as_of = "2022-06-30"
    original = estimate_hamilton_regime_as_of(returns, as_of)
    changed_future = returns.copy()
    changed_future.loc[changed_future.index > as_of] = 0.25
    repeated = estimate_hamilton_regime_as_of(changed_future, as_of)

    assert original == repeated
    assert original.as_of_date == as_of
    assert original.future_observations_used is False
    assert original.regime in {"BULL", "BEAR", "SIDEWAYS"}
    assert abs(sum(original.state_probabilities.values()) - 1.0) < 1e-5


def test_hamilton_regime_rejects_short_history() -> None:
    short = pd.Series(
        np.zeros(100),
        index=pd.bdate_range("2024-01-01", periods=100),
    )
    try:
        estimate_hamilton_regime_as_of(short, short.index[-1])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
