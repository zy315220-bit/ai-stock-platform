from __future__ import annotations

import pandas as pd
import numpy as np

from app.services.backtest import engine
from indicators import add_indicators
from app.services.backtest.report import _extract_score
from score_engine.calculate import calculate_score


def _frame() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=65)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0 + index for index in range(65)],
            "High": [101.0 + index for index in range(65)],
            "Low": [99.0 + index for index in range(65)],
            "Close": [100.5 + index for index in range(65)],
            "Volume": [1_000_000 + index for index in range(65)],
        }
    )


def test_score_series_cache_reuses_identical_data_and_invalidates_changes(
    monkeypatch,
) -> None:
    calls = 0

    def fake_calculate_score(frame):
        nonlocal calls
        calls += 1
        return {"total_score": float(len(frame))}

    monkeypatch.setattr(engine, "calculate_score", fake_calculate_score)
    engine._clear_score_series_cache()
    frame = _frame()

    first, first_hit, first_fingerprint = engine._score_series_for_frame(
        "2330",
        frame,
    )
    first_calls = calls
    second, second_hit, second_fingerprint = engine._score_series_for_frame(
        "2330",
        frame.copy(),
    )

    assert first_hit is False
    assert second_hit is True
    assert first == second
    assert first_fingerprint == second_fingerprint
    assert calls == first_calls

    changed = frame.copy()
    changed.loc[63, "Close"] += 1.0
    _, changed_hit, changed_fingerprint = engine._score_series_for_frame(
        "2330",
        changed,
    )
    assert changed_hit is False
    assert changed_fingerprint != first_fingerprint
    assert calls > first_calls

    changed_action = frame.copy()
    changed_action.attrs["dividends"] = [
        {"ex_date": "2024-03-01", "amount": 1.0}
    ]
    _, action_hit, action_fingerprint = engine._score_series_for_frame(
        "2330",
        changed_action,
    )
    assert action_hit is False
    assert action_fingerprint != first_fingerprint


def test_sixty_session_score_window_matches_full_causal_prefix() -> None:
    rng = np.random.default_rng(41)
    close = 100.0 + np.cumsum(rng.normal(0.1, 1.0, 180))
    frame = pd.DataFrame(
        {
            "Date": pd.bdate_range("2023-01-01", periods=180),
            "Open": close + rng.normal(0.0, 0.3, 180),
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": rng.integers(800_000, 1_200_000, 180),
        }
    )
    enriched = add_indicators(frame).dropna().reset_index(drop=True)

    for index in range(60, len(enriched), 11):
        full_score = _extract_score(
            calculate_score(enriched.iloc[: index + 1])
        )
        window_score = _extract_score(
            calculate_score(enriched.iloc[index - 59 : index + 1])
        )
        assert window_score == full_score


def test_daily_score_cache_reuses_overlapping_date_windows(monkeypatch) -> None:
    calls = 0

    def fake_calculate_score(frame):
        nonlocal calls
        calls += 1
        return {"total_score": float(frame.iloc[-1]["Close"])}

    monkeypatch.setattr(engine, "calculate_score", fake_calculate_score)
    engine._clear_score_series_cache()
    dates = pd.bdate_range("2023-01-01", periods=180)
    close = np.arange(180, dtype=float) + 100.0
    frame = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
        "Volume": 1_000_000.0,
    })

    engine._score_series_for_frame("2330", frame)
    first_calls = calls
    _, frame_hit, _ = engine._score_series_for_frame(
        "2330",
        frame.iloc[30:].reset_index(drop=True),
    )

    assert frame_hit is False
    assert calls == first_calls


def test_daily_history_snapshot_avoids_repeated_provider_downloads(
    monkeypatch,
) -> None:
    calls = 0
    dates = pd.bdate_range("2020-01-01", "2025-12-31")
    source = pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.0,
            "Volume": 1_000_000,
        },
        index=dates,
    )
    source.attrs.update(
        source="test",
        split_adjusted=True,
        corporate_action_validated=True,
        price_basis="split_adjusted",
    )

    def fake_download(*args, **kwargs):
        nonlocal calls
        calls += 1
        return source.copy()

    monkeypatch.setattr(engine, "download_stock", fake_download)
    engine._clear_history_snapshot_cache()
    first = engine._download_backtest_history(
        "2330",
        required_start_date="2021-01-01",
        required_end_date="2024-12-31",
    )
    second = engine._download_backtest_history(
        "2330",
        required_start_date="2021-01-01",
        required_end_date="2024-12-31",
    )

    assert calls == 1
    assert first.attrs["history_recovery"]["cache_hit"] is False
    assert second.attrs["history_recovery"]["cache_hit"] is True


def test_listing_aware_snapshot_does_not_retry_pre_listing_months(
    monkeypatch,
) -> None:
    calls = 0
    dates = pd.bdate_range("2020-07-20", "2025-12-31")
    source = pd.DataFrame(
        {
            "Open": 20.0,
            "High": 20.5,
            "Low": 19.5,
            "Close": 20.0,
            "Volume": 1_000_000,
        },
        index=dates,
    )
    source.attrs.update(
        source="test",
        split_adjusted=True,
        corporate_action_validated=True,
        price_basis="split_adjusted",
    )

    def fake_download(*args, **kwargs):
        nonlocal calls
        calls += 1
        return source.copy()

    monkeypatch.setattr(engine, "download_stock", fake_download)
    engine._clear_history_snapshot_cache()
    first = engine._download_backtest_history(
        "00878",
        required_start_date="2020-01-01",
        required_end_date="2025-12-31",
    )
    second = engine._download_backtest_history(
        "00878",
        required_start_date="2020-01-01",
        required_end_date="2025-12-31",
    )

    assert calls == 1
    assert first.attrs["history_recovery"]["attempts"] == 1
    assert first.attrs["history_recovery"]["cache_hit"] is False
    assert second.attrs["history_recovery"]["cache_hit"] is True
