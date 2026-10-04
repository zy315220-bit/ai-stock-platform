from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.backtest import engine
from app.services.research_lab.causal_regimes import estimate_hamilton_regime_as_of
from app.services.research_lab.market_regimes import load_point_in_time_benchmark_returns
from app.services.research_lab.models import ResearchSplit


@pytest.fixture(autouse=True)
def clear_history_cache():
    engine._clear_history_snapshot_cache()
    yield
    engine._clear_history_snapshot_cache()


def _frame(start: str, end: str) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    prices = 20 * np.exp(np.arange(len(dates)) * 0.0001)
    frame = pd.DataFrame(
        {"Open": prices, "High": prices + 0.1, "Low": prices - 0.1,
         "Close": prices, "Volume": 1_000_000}, index=dates,
    )
    frame.attrs.update(
        price_basis="latest-unit split-adjusted", split_adjusted=True,
        corporate_action_validated=True, split_adjustments=[], dividends=[],
    )
    return frame


def test_extended_regime_history_can_label_the_earliest_stress_slice(monkeypatch):
    today = pd.Timestamp(date.today())
    full = _frame("2003-06-25", today.strftime("%Y-%m-%d"))
    recent = full.loc[full.index >= today - pd.DateOffset(years=10)]
    calls = []

    def provider(_code, **options):
        calls.append(options)
        if options["prefer_official"]:
            cutoff = today - pd.DateOffset(months=options["official_months"] - 1)
            return full.loc[full.index >= cutoff.replace(day=1)].copy()
        return (full if options["daily_period"] == "max" else recent).copy()

    monkeypatch.setattr(engine, "download_stock", provider)
    split = ResearchSplit("2020-01-01", "2023-12-31", "2024-01-01",
                          "2024-12-31", "2025-01-01", "2025-12-31")
    returns = load_point_in_time_benchmark_returns("0050", split)
    estimate = estimate_hamilton_regime_as_of(returns, "2009-12-31")

    assert estimate.future_observations_used is False
    assert len(returns.loc[:"2009-12-31"]) >= 126
    assert returns.index.max() <= pd.Timestamp(split.validation_end)
    assert not any(call["prefer_official"] for call in calls)


def test_official_fallback_covers_the_requested_historical_start(monkeypatch):
    today = pd.Timestamp(date.today())
    full = _frame("2003-06-25", today.strftime("%Y-%m-%d"))

    def provider(_code, **options):
        if not options["prefer_official"]:
            return pd.DataFrame()
        cutoff = today - pd.DateOffset(months=options["official_months"] - 1)
        return full.loc[full.index >= cutoff.replace(day=1)].copy()

    monkeypatch.setattr(engine, "download_stock", provider)
    history = engine._download_backtest_history(
        "0050", required_start_date="2007-01-01", required_end_date="2024-12-31",
    )

    assert history.index.min().to_period("M") <= pd.Period("2007-01", freq="M")
    assert history.attrs["history_recovery"]["method"] == "official_refresh"


def test_holdout_price_changes_do_not_change_regime_evidence(monkeypatch):
    full = _frame("2003-06-25", "2026-10-02")
    split = ResearchSplit("2020-01-01", "2023-12-31", "2024-01-01",
                          "2024-12-31", "2025-01-01", "2025-12-31")
    from app.services.research_lab import market_regimes

    monkeypatch.setattr(market_regimes, "_download_backtest_history", lambda *a, **k: full)
    original = load_point_in_time_benchmark_returns("0050", split)
    full.loc[full.index > split.validation_end, "Close"] *= 10
    changed = load_point_in_time_benchmark_returns("0050", split)

    pd.testing.assert_series_equal(original, changed)
    assert original.attrs["data_fingerprint"] == changed.attrs["data_fingerprint"]
