from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from app.services.backtest.engine import (
    _position_fraction_for_atr,
    backtest_stock,
)
from app.services.research_lab.evolution import (
    ADVANCED_ALPHA_SEEDS,
    SEARCH_SPACE_SCHEMA,
    generate_parameter_candidates,
)


def _frame(periods: int = 90) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    frame = pd.DataFrame(
        {
            "Open": [100.0] * periods,
            "High": [101.0] * periods,
            "Low": [99.0] * periods,
            "Close": [100.0] * periods,
            "Volume": [1000.0] * periods,
        },
        index=dates,
    )
    frame.attrs.update(
        {
            "stock_code": "TEST",
            "source": "synthetic-test",
            "split_adjusted": True,
            "price_basis": "latest-unit split-adjusted",
            "corporate_action_validated": True,
            "split_adjustments": [],
            "dividends": [],
            "corporate_action_events": [],
            "corporate_action_resolutions": [],
        }
    )
    return frame


def _indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["EMA5"] = 101.0
    out["EMA20"] = 100.0
    out["EMA60"] = 99.0
    out["MA20"] = 101.0
    out["ATR"] = 4.0
    out["NATR"] = 4.0
    out["RSI"] = 50.0
    out["Upper"] = 101.0
    out["Lower"] = 99.0
    out["VolumeRatio"] = 1.0
    return out


def test_advanced_alpha_seeds_are_in_daily_candidate_universe() -> None:
    candidates = generate_parameter_candidates()
    families = {candidate.strategy_family for candidate in candidates}
    expected = {str(seed["family"]) for seed in ADVANCED_ALPHA_SEEDS}
    assert expected <= families
    assert SEARCH_SPACE_SCHEMA == "alpha-family-diversity-v5"
    assert len({candidate.candidate_id for candidate in candidates}) == len(candidates)


def test_atr_target_fraction_is_bounded_and_monotone() -> None:
    low_vol = _position_fraction_for_atr(
        atr_percent=1.0,
        atr_target_percent=2.0,
        min_position_fraction=0.25,
        max_position_fraction=0.80,
    )
    medium_vol = _position_fraction_for_atr(
        atr_percent=4.0,
        atr_target_percent=2.0,
        min_position_fraction=0.25,
        max_position_fraction=0.80,
    )
    high_vol = _position_fraction_for_atr(
        atr_percent=20.0,
        atr_target_percent=2.0,
        min_position_fraction=0.25,
        max_position_fraction=0.80,
    )
    assert low_vol == pytest.approx(0.80)
    assert medium_vol == pytest.approx(0.50)
    assert high_vol == pytest.approx(0.25)
    assert low_vol > medium_vol > high_vol


@patch("app.services.backtest.engine._download_backtest_history")
@patch("app.services.backtest.engine.add_indicators")
@patch("app.services.backtest.engine.calculate_score")
def test_mean_reversion_uses_t_signal_and_t_plus_1_execution(
    score, add_indicators, download
) -> None:
    raw = _frame()
    download.return_value = raw
    indicators = _indicator_frame(raw)
    indicators.iloc[60, indicators.columns.get_loc("Lower")] = 101.0
    indicators.iloc[60, indicators.columns.get_loc("RSI")] = 30.0
    indicators.iloc[61, indicators.columns.get_loc("RSI")] = 30.0
    indicators.iloc[62, indicators.columns.get_loc("RSI")] = 60.0
    add_indicators.return_value = indicators
    score.return_value = {"total_score": 100.0}

    result = backtest_stock(
        "TEST",
        start_date="2024-01-01",
        end_date="2024-03-30",
        entry_score=1,
        exit_score=0,
        initial_capital=100_000,
        entry_mode="mean_reversion_bollinger_rsi",
        exit_mode="mean_reversion_or_time",
        max_holding_days=20,
    )

    assert result["trades"]
    first = result["trades"][0]
    assert first["entry_date"] == raw.index[61].strftime("%Y-%m-%d")
    assert first["exit_date"] == raw.index[63].strftime("%Y-%m-%d")
    assert first["exit_reason"] == "mean_reversion_recovered"


@patch("app.services.backtest.engine._download_backtest_history")
@patch("app.services.backtest.engine.add_indicators")
@patch("app.services.backtest.engine.calculate_score")
def test_volatility_sizing_uses_current_not_future_natr(
    score, add_indicators, download
) -> None:
    raw = _frame()
    download.return_value = raw
    indicators = _indicator_frame(raw)
    indicators.iloc[60, indicators.columns.get_loc("NATR")] = 4.0
    indicators.iloc[61, indicators.columns.get_loc("NATR")] = 0.5
    add_indicators.return_value = indicators
    score.return_value = {"total_score": 100.0}

    result = backtest_stock(
        "TEST",
        start_date="2024-01-01",
        end_date="2024-03-30",
        entry_score=1,
        exit_score=0,
        initial_capital=100_000,
        require_ema_trend=True,
        ema_fast_column="EMA20",
        ema_slow_column="EMA60",
        entry_mode="score",
        exit_mode="score_or_time_or_ema_reversal",
        max_holding_days=20,
        atr_target_percent=2.0,
        min_position_fraction=0.20,
        max_position_fraction=1.0,
    )

    assert result["trades"]
    first = result["trades"][0]
    assert first["entry_position_fraction"] == pytest.approx(0.5)
    assert 450 <= first["shares"] <= 550
    assert first["entry_date"] == raw.index[61].strftime("%Y-%m-%d")


def test_invalid_volatility_allocation_fails_closed() -> None:
    with pytest.raises(ValueError, match="position fractions"):
        backtest_stock(
            "TEST",
            entry_score=75,
            exit_score=55,
            min_position_fraction=0.9,
            max_position_fraction=0.8,
        )
