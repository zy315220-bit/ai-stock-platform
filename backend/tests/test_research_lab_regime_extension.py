from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import app.services.research_lab.market_regimes as regimes
from app.services.research_lab.models import ResearchSplit


def _split() -> ResearchSplit:
    return ResearchSplit(
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-01",
        validation_end="2024-12-31",
        holdout_start="2025-01-01",
        holdout_end="2025-12-31",
    )


def _returns() -> pd.Series:
    index = pd.date_range("2005-01-03", "2024-12-31", freq="B")
    return pd.Series(0.0002, index=index, dtype=float)


def test_regime_window_extends_until_missing_bear_is_found(monkeypatch) -> None:
    def fake_estimate(_series, as_of_date):
        as_of = pd.Timestamp(as_of_date)
        # The base 2020-2024 window begins with a 2019-12-31 as-of date,
        # so keep that BULL. A two-year extension reaches a 2017 as-of date
        # and should be the first attempt able to observe the synthetic BEAR.
        regime = "BEAR" if as_of.year < 2018 else "BULL"
        return SimpleNamespace(
            regime=regime,
            to_dict=lambda: {
                "regime": regime,
                "as_of_date": as_of.strftime("%Y-%m-%d"),
                "method": "synthetic_point_in_time",
                "confidence": 1.0,
                "future_observations_used": False,
            },
        )

    monkeypatch.setattr(regimes, "estimate_hamilton_regime_as_of", fake_estimate)
    labelled, extension_years, missing = regimes._adaptive_labelled_slices(
        _split(),
        slice_count=6,
        causal_returns=_returns(),
        estimate_cache={},
        extension_step_years=2,
        max_extension_years=10,
    )

    assert extension_years == 2
    assert missing == ()
    assert {regime.value for _, regime, _ in labelled} == {"BULL", "BEAR"}
    assert len(labelled) > 6


def test_regime_window_stays_fail_closed_at_extension_cap(monkeypatch) -> None:
    def bull_only(_series, as_of_date):
        as_of = pd.Timestamp(as_of_date)
        return SimpleNamespace(
            regime="BULL",
            to_dict=lambda: {
                "regime": "BULL",
                "as_of_date": as_of.strftime("%Y-%m-%d"),
                "method": "synthetic_point_in_time",
                "confidence": 1.0,
                "future_observations_used": False,
            },
        )

    monkeypatch.setattr(regimes, "estimate_hamilton_regime_as_of", bull_only)
    labelled, extension_years, missing = regimes._adaptive_labelled_slices(
        _split(),
        slice_count=6,
        causal_returns=_returns(),
        estimate_cache={},
        extension_step_years=2,
        max_extension_years=4,
    )

    assert extension_years == 4
    assert missing == ("BEAR",)
    assert labelled
