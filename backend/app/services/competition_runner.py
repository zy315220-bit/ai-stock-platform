from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
import time
from typing import Any, Callable

import pandas as pd

from corporate_actions import dividends_by_ex_date
from indicators import add_indicators

from app.services.competition_service import (
    freeze_robot_spec,
    rank_robot_results,
)
from app.services.history_policy import (
    BACKTEST_WARMUP_MONTHS,
    FORWARD_HOLDOUT_MONTHS,
    PREFERRED_RESEARCH_YEARS,
    RESEARCH_HISTORY_MONTHS,
)
from app.services.research_history import frame_coverage


COMPETITION_UNIVERSE = ("0050", "0056", "00878", "00919")
DEFAULT_INITIAL_CAPITAL = 100_000.0
MAX_INITIAL_CAPITAL = 2_000_000.0
COMMISSION_RATE = 0.001425
ETF_TRANSACTION_TAX_RATE = 0.001
STOP_ATR_MULTIPLE = 2.0
TARGET_ATR_MULTIPLE = 4.0
MIN_FORWARD_TRADES_FOR_CHAMPION = 30
COMPETITION_LISTING_DATES = {
    "0050": date(2003, 6, 25),
    "0056": date(2007, 12, 26),
    "00878": date(2020, 7, 20),
    "00919": date(2022, 10, 20),
}
COMPETITION_DOWNLOAD_PAUSE_SECONDS = 1.0

BROCK_REFERENCE = {
    "title": "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns",
    "authors": "William Brock, Josef Lakonishok, Blake LeBaron",
    "year": 1992,
    "journal": "The Journal of Finance",
    "doi": "10.1111/j.1540-6261.1992.tb04681.x",
    "use": "moving-average and trading-range-break rule families",
}

MOMENTUM_REFERENCE = {
    "title": "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency",
    "authors": "Narasimhan Jegadeesh, Sheridan Titman",
    "year": 1993,
    "journal": "The Journal of Finance",
    "doi": "10.1111/j.1540-6261.1993.tb04702.x",
    "use": "momentum as a research basis; short-window thresholds remain platform parameters",
}

TIME_SERIES_MOMENTUM_REFERENCE = {
    "title": "Time Series Momentum",
    "authors": "Tobias J. Moskowitz, Yao Hua Ooi, Lasse Heje Pedersen",
    "year": 2012,
    "journal": "Journal of Financial Economics",
    "doi": "10.1016/j.jfineco.2011.11.003",
    "use": "time-series momentum research basis; 60-session threshold is a platform parameter",
}

REVERSAL_REFERENCE = {
    "title": "Evidence of Predictable Behavior of Security Returns",
    "author": "Narasimhan Jegadeesh",
    "year": 1990,
    "journal": "The Journal of Finance",
    "doi": "10.1111/j.1540-6261.1990.tb05110.x",
    "use": "short-horizon return reversal research basis; RSI thresholds are platform parameters",
}

VOLUME_MOMENTUM_REFERENCE = {
    "title": "Price Momentum and Trading Volume",
    "authors": "Charles M. C. Lee, Bhaskaran Swaminathan",
    "year": 2000,
    "journal": "The Journal of Finance",
    "doi": "10.1111/0022-1082.00280",
    "use": "interaction between past volume and momentum; volume-ratio thresholds are platform parameters",
}

VOLATILITY_REFERENCE = {
    "title": "Volatility-Managed Portfolios",
    "authors": "Alan Moreira, Tyler Muir",
    "year": 2017,
    "journal": "The Journal of Finance",
    "doi": "10.1111/jofi.12513",
    "use": "lower exposure during high volatility; ATR-percent thresholds are platform parameters",
}


TECHNICAL_PATTERN_REFERENCE = {
    "title": (
        "Foundations of Technical Analysis: Computational Algorithms, "
        "Statistical Inference, and Empirical Implementation"
    ),
    "authors": "Andrew W. Lo, Harry Mamaysky, Jiang Wang",
    "year": 2000,
    "journal": "The Journal of Finance",
    "doi": "10.1111/0022-1082.00265",
    "use": (
        "systematic technical-pattern research basis; MACD, RSI, Bollinger, "
        "and KD thresholds remain platform parameters"
    ),
}


ROBOT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "robot_id": "EMA20-TREND-v1",
        "name": "EMA20 趨勢機器人",
        "family": "moving_average",
        "entry": "Close > EMA20 and EMA20SlopePerBar > 0",
        "exit": "Close < EMA20 or EMA20SlopePerBar < 0",
        "parameters": {"ema_period": 20},
        "research": [BROCK_REFERENCE],
    },
    {
        "robot_id": "TECHNICAL-v1",
        "name": "純技術面機器人",
        "family": "trend_momentum_confirmation",
        "entry": (
            "Close > EMA20 > EMA60, RSI in [50, 70], MACD histogram > 0, ADX >= 18"
        ),
        "exit": "Close < EMA20 or RSI < 45 or MACD histogram < 0",
        "parameters": {
            "ema_fast": 20,
            "ema_slow": 60,
            "rsi_entry_min": 50,
            "rsi_entry_max": 70,
            "rsi_exit": 45,
            "adx_min": 18,
        },
        "research": [BROCK_REFERENCE, MOMENTUM_REFERENCE],
    },
    {
        "robot_id": "BREAKOUT-v1",
        "name": "突破機器人",
        "family": "trading_range_break",
        "entry": "Close > prior 20-session high and Volume / VMA20 >= 1.0",
        "exit": "Close < EMA20",
        "parameters": {"breakout_sessions": 20, "minimum_volume_ratio": 1.0},
        "research": [BROCK_REFERENCE],
    },
    {
        "robot_id": "PULLBACK-v1",
        "name": "均線回檔機器人",
        "family": "trend_pullback",
        "entry": (
            "EMA20 > EMA60 and price crosses back above EMA20 with RSI in [40, 65]"
        ),
        "exit": "Close < EMA60 or RSI < 40",
        "parameters": {
            "ema_fast": 20,
            "ema_slow": 60,
            "rsi_entry_min": 40,
            "rsi_entry_max": 65,
            "rsi_exit": 40,
        },
        "research": [BROCK_REFERENCE, MOMENTUM_REFERENCE],
    },
    {
        "robot_id": "EMA-CROSS-v1",
        "name": "均線黃金交叉機器人",
        "family": "moving_average_crossover",
        "entry": "EMA20 crosses above EMA60",
        "exit": "EMA20 crosses below EMA60",
        "parameters": {"ema_fast": 20, "ema_slow": 60},
        "research": [BROCK_REFERENCE],
    },
    {
        "robot_id": "MOMENTUM60-v1",
        "name": "60日動能機器人",
        "family": "time_series_momentum",
        "entry": "60-session return > 5% and Close > EMA20",
        "exit": "60-session return <= 0% or Close < EMA20",
        "parameters": {"lookback_sessions": 60, "entry_return_percent": 5},
        "research": [MOMENTUM_REFERENCE, TIME_SERIES_MOMENTUM_REFERENCE],
    },
    {
        "robot_id": "REVERSAL-v1",
        "name": "短期反轉機器人",
        "family": "short_term_reversal",
        "entry": "Close > EMA60, Close < EMA20, and RSI <= 35",
        "exit": "RSI >= 55 or Close < EMA60",
        "parameters": {"rsi_entry_max": 35, "rsi_exit_min": 55},
        "research": [REVERSAL_REFERENCE],
    },
    {
        "robot_id": "VOLUME-MOMENTUM-v1",
        "name": "量價動能機器人",
        "family": "volume_conditioned_momentum",
        "entry": (
            "60-session return > 0, Close > EMA20 > EMA60, "
            "and Volume / VMA20 in [0.5, 1.2]"
        ),
        "exit": "60-session return <= 0 or Close < EMA20",
        "parameters": {
            "lookback_sessions": 60,
            "minimum_volume_ratio": 0.5,
            "maximum_volume_ratio": 1.2,
        },
        "research": [
            MOMENTUM_REFERENCE,
            TIME_SERIES_MOMENTUM_REFERENCE,
            VOLUME_MOMENTUM_REFERENCE,
        ],
    },
    {
        "robot_id": "LOW-VOL-TREND-v1",
        "name": "低波動趨勢機器人",
        "family": "volatility_filtered_trend",
        "entry": (
            "Close > EMA20 > EMA60, ATRPercent <= 2.5%, and ADX >= 18"
        ),
        "exit": "Close < EMA20 or ATRPercent > 4%",
        "parameters": {
            "maximum_entry_atr_percent": 2.5,
            "maximum_hold_atr_percent": 4.0,
            "adx_min": 18,
        },
        "research": [BROCK_REFERENCE, VOLATILITY_REFERENCE],
    },
    {
        "robot_id": "BREAKOUT55-v1",
        "name": "55日突破機器人",
        "family": "long_trading_range_break",
        "entry": "Close > prior 55-session high and Volume / VMA20 >= 1.0",
        "exit": "Close < EMA20",
        "parameters": {"breakout_sessions": 55, "minimum_volume_ratio": 1.0},
        "research": [BROCK_REFERENCE],
    },
    {
        "robot_id": "MACD-CROSS-v1",
        "name": "MACD翻多機器人",
        "family": "macd_trend_confirmation",
        "entry": "MACD histogram crosses above zero while Close > EMA60",
        "exit": "MACD histogram < 0 or Close < EMA60",
        "parameters": {"ema_trend_period": 60, "macd_zero_cross": True},
        "research": [BROCK_REFERENCE, TECHNICAL_PATTERN_REFERENCE],
    },
    {
        "robot_id": "RSI-RECOVERY-v1",
        "name": "RSI反轉確認機器人",
        "family": "rsi_reversal_confirmation",
        "entry": "RSI crosses above 35 after oversold while Close > EMA60",
        "exit": "RSI >= 60 or Close < EMA60",
        "parameters": {
            "rsi_recovery_level": 35,
            "rsi_exit_level": 60,
            "ema_trend_period": 60,
        },
        "research": [REVERSAL_REFERENCE, TECHNICAL_PATTERN_REFERENCE],
    },
    {
        "robot_id": "BOLLINGER-REBOUND-v1",
        "name": "布林通道反彈機器人",
        "family": "bollinger_mean_reversion",
        "entry": (
            "Price crosses back above the lower Bollinger band with RSI < 50"
        ),
        "exit": "Close >= MA20 or Close < lower Bollinger band",
        "parameters": {
            "bollinger_period": 20,
            "bollinger_standard_deviations": 2,
            "rsi_entry_max": 50,
        },
        "research": [REVERSAL_REFERENCE, TECHNICAL_PATTERN_REFERENCE],
    },
    {
        "robot_id": "BOLLINGER-BREAKOUT-v1",
        "name": "布林通道突破機器人",
        "family": "bollinger_breakout",
        "entry": (
            "Price crosses above the upper Bollinger band "
            "and Volume / VMA20 >= 1.0"
        ),
        "exit": "Close < MA20",
        "parameters": {
            "bollinger_period": 20,
            "bollinger_standard_deviations": 2,
            "minimum_volume_ratio": 1.0,
        },
        "research": [BROCK_REFERENCE, TECHNICAL_PATTERN_REFERENCE],
    },
    {
        "robot_id": "KD-RECOVERY-v1",
        "name": "KD低檔翻多機器人",
        "family": "stochastic_reversal",
        "entry": "K crosses above D below 35 while Close > EMA60",
        "exit": "K crosses below D above 65 or Close < EMA60",
        "parameters": {
            "entry_zone_max": 35,
            "exit_zone_min": 65,
            "ema_trend_period": 60,
        },
        "research": [REVERSAL_REFERENCE, TECHNICAL_PATTERN_REFERENCE],
    },
    {
        "robot_id": "MOMENTUM126-v1",
        "name": "126日動能機器人",
        "family": "medium_term_time_series_momentum",
        "entry": "126-session return > 10% and Close > EMA60",
        "exit": "126-session return <= 0 or Close < EMA60",
        "parameters": {
            "lookback_sessions": 126,
            "entry_return_percent": 10,
            "ema_trend_period": 60,
        },
        "research": [MOMENTUM_REFERENCE, TIME_SERIES_MOMENTUM_REFERENCE],
    },
)


def _calculate_buy_cost(
    *,
    price: float,
    shares: int,
    commission_rate: float,
) -> dict[str, float]:
    gross_amount = price * shares
    commission = gross_amount * commission_rate
    return {
        "gross_amount": gross_amount,
        "commission": commission,
        "total_cost": gross_amount + commission,
    }


def _calculate_sell_value(
    *,
    price: float,
    shares: int,
    commission_rate: float,
    transaction_tax_rate: float,
) -> dict[str, float]:
    gross_amount = price * shares
    commission = gross_amount * commission_rate
    transaction_tax = gross_amount * transaction_tax_rate
    return {
        "gross_amount": gross_amount,
        "commission": commission,
        "transaction_tax": transaction_tax,
        "net_amount": gross_amount - commission - transaction_tax,
    }


def _calculate_purchasable_shares(
    *,
    cash: float,
    price: float,
    commission_rate: float,
) -> int:
    if cash <= 0 or price <= 0:
        return 0
    return max(0, int(cash // (price * (1 + commission_rate))))


def _number(row: pd.Series, key: str) -> float:
    value = row.get(key)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _all_finite(*values: float) -> bool:
    return all(math.isfinite(value) for value in values)


def _ema20_signal(row: pd.Series, previous: pd.Series) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema20 = _number(row, "EMA20")
    slope = _number(row, "EMA20SlopePerBar")
    if not _all_finite(close, ema20, slope):
        return False, False, "insufficient_indicators"
    return (
        close > ema20 and slope > 0,
        close < ema20 or slope < 0,
        "ema20_trend",
    )


def _technical_signal(row: pd.Series, previous: pd.Series) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema20 = _number(row, "EMA20")
    ema60 = _number(row, "EMA60")
    rsi = _number(row, "RSI")
    macd_hist = _number(row, "MACD_Hist")
    adx = _number(row, "ADX")
    if not _all_finite(close, ema20, ema60, rsi, macd_hist, adx):
        return False, False, "insufficient_indicators"
    return (
        close > ema20 > ema60 and 50 <= rsi <= 70 and macd_hist > 0 and adx >= 18,
        close < ema20 or rsi < 45 or macd_hist < 0,
        "trend_momentum_confirmation",
    )


def _breakout_signal(row: pd.Series, previous: pd.Series) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    prior_high = _number(row, "Prior20High")
    volume_ratio = _number(row, "VolumeRatio")
    ema20 = _number(row, "EMA20")
    if not _all_finite(close, prior_high, volume_ratio, ema20):
        return False, False, "insufficient_indicators"
    return (
        close > prior_high and volume_ratio >= 1.0,
        close < ema20,
        "20_session_range_break",
    )


def _pullback_signal(row: pd.Series, previous: pd.Series) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema20 = _number(row, "EMA20")
    ema60 = _number(row, "EMA60")
    rsi = _number(row, "RSI")
    previous_close = _number(previous, "Close")
    previous_ema20 = _number(previous, "EMA20")
    if not _all_finite(close, ema20, ema60, rsi, previous_close, previous_ema20):
        return False, False, "insufficient_indicators"
    return (
        ema20 > ema60
        and previous_close <= previous_ema20
        and close > ema20
        and 40 <= rsi <= 65,
        close < ema60 or rsi < 40,
        "ema20_pullback_in_uptrend",
    )


def _ema_cross_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    ema20 = _number(row, "EMA20")
    ema60 = _number(row, "EMA60")
    previous_ema20 = _number(previous, "EMA20")
    previous_ema60 = _number(previous, "EMA60")
    if not _all_finite(ema20, ema60, previous_ema20, previous_ema60):
        return False, False, "insufficient_indicators"
    return (
        previous_ema20 <= previous_ema60 and ema20 > ema60,
        previous_ema20 >= previous_ema60 and ema20 < ema60,
        "ema20_ema60_cross",
    )


def _momentum60_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema20 = _number(row, "EMA20")
    return60 = _number(row, "Return60")
    if not _all_finite(close, ema20, return60):
        return False, False, "insufficient_indicators"
    return (
        return60 > 0.05 and close > ema20,
        return60 <= 0 or close < ema20,
        "60_session_time_series_momentum",
    )


def _reversal_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema20 = _number(row, "EMA20")
    ema60 = _number(row, "EMA60")
    rsi = _number(row, "RSI")
    if not _all_finite(close, ema20, ema60, rsi):
        return False, False, "insufficient_indicators"
    return (
        close > ema60 and close < ema20 and rsi <= 35,
        rsi >= 55 or close < ema60,
        "short_term_reversal_in_long_trend",
    )


def _volume_momentum_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema20 = _number(row, "EMA20")
    ema60 = _number(row, "EMA60")
    return60 = _number(row, "Return60")
    volume_ratio = _number(row, "VolumeRatio")
    if not _all_finite(close, ema20, ema60, return60, volume_ratio):
        return False, False, "insufficient_indicators"
    return (
        return60 > 0
        and close > ema20 > ema60
        and 0.5 <= volume_ratio <= 1.2,
        return60 <= 0 or close < ema20,
        "low_volume_winner_momentum",
    )


def _low_vol_trend_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema20 = _number(row, "EMA20")
    ema60 = _number(row, "EMA60")
    atr_percent = _number(row, "ATRPercent")
    adx = _number(row, "ADX")
    if not _all_finite(close, ema20, ema60, atr_percent, adx):
        return False, False, "insufficient_indicators"
    return (
        close > ema20 > ema60 and atr_percent <= 2.5 and adx >= 18,
        close < ema20 or atr_percent > 4.0,
        "low_volatility_trend",
    )


def _breakout55_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    prior_high = _number(row, "Prior55High")
    volume_ratio = _number(row, "VolumeRatio")
    ema20 = _number(row, "EMA20")
    if not _all_finite(close, prior_high, volume_ratio, ema20):
        return False, False, "insufficient_indicators"
    return (
        close > prior_high and volume_ratio >= 1.0,
        close < ema20,
        "55_session_range_break",
    )


def _macd_cross_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema60 = _number(row, "EMA60")
    macd_hist = _number(row, "MACD_Hist")
    previous_macd_hist = _number(previous, "MACD_Hist")
    if not _all_finite(close, ema60, macd_hist, previous_macd_hist):
        return False, False, "insufficient_indicators"
    return (
        previous_macd_hist <= 0 < macd_hist and close > ema60,
        macd_hist < 0 or close < ema60,
        "macd_histogram_zero_cross",
    )


def _rsi_recovery_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema60 = _number(row, "EMA60")
    rsi = _number(row, "RSI")
    previous_rsi = _number(previous, "RSI")
    if not _all_finite(close, ema60, rsi, previous_rsi):
        return False, False, "insufficient_indicators"
    return (
        previous_rsi <= 35 < rsi and close > ema60,
        rsi >= 60 or close < ema60,
        "rsi_oversold_recovery",
    )


def _bollinger_rebound_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    lower = _number(row, "Lower")
    ma20 = _number(row, "MA20")
    rsi = _number(row, "RSI")
    previous_close = _number(previous, "Close")
    previous_lower = _number(previous, "Lower")
    if not _all_finite(
        close,
        lower,
        ma20,
        rsi,
        previous_close,
        previous_lower,
    ):
        return False, False, "insufficient_indicators"
    return (
        previous_close <= previous_lower and close > lower and rsi < 50,
        close >= ma20 or close < lower,
        "bollinger_lower_band_rebound",
    )


def _bollinger_breakout_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    upper = _number(row, "Upper")
    ma20 = _number(row, "MA20")
    volume_ratio = _number(row, "VolumeRatio")
    previous_close = _number(previous, "Close")
    previous_upper = _number(previous, "Upper")
    if not _all_finite(
        close,
        upper,
        ma20,
        volume_ratio,
        previous_close,
        previous_upper,
    ):
        return False, False, "insufficient_indicators"
    return (
        previous_close <= previous_upper
        and close > upper
        and volume_ratio >= 1.0,
        close < ma20,
        "bollinger_upper_band_breakout",
    )


def _kd_recovery_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema60 = _number(row, "EMA60")
    k_value = _number(row, "K")
    d_value = _number(row, "D")
    previous_k = _number(previous, "K")
    previous_d = _number(previous, "D")
    if not _all_finite(
        close,
        ema60,
        k_value,
        d_value,
        previous_k,
        previous_d,
    ):
        return False, False, "insufficient_indicators"
    return (
        previous_k <= previous_d
        and k_value > d_value
        and k_value <= 35
        and close > ema60,
        (
            previous_k >= previous_d
            and k_value < d_value
            and k_value >= 65
        )
        or close < ema60,
        "kd_oversold_recovery",
    )


def _momentum126_signal(
    row: pd.Series,
    previous: pd.Series,
) -> tuple[bool, bool, str]:
    close = _number(row, "Close")
    ema60 = _number(row, "EMA60")
    return126 = _number(row, "Return126")
    if not _all_finite(close, ema60, return126):
        return False, False, "insufficient_indicators"
    return (
        return126 > 0.10 and close > ema60,
        return126 <= 0 or close < ema60,
        "126_session_time_series_momentum",
    )


SIGNAL_FUNCTIONS: dict[
    str,
    Callable[[pd.Series, pd.Series], tuple[bool, bool, str]],
] = {
    "EMA20-TREND-v1": _ema20_signal,
    "TECHNICAL-v1": _technical_signal,
    "BREAKOUT-v1": _breakout_signal,
    "PULLBACK-v1": _pullback_signal,
    "EMA-CROSS-v1": _ema_cross_signal,
    "MOMENTUM60-v1": _momentum60_signal,
    "REVERSAL-v1": _reversal_signal,
    "VOLUME-MOMENTUM-v1": _volume_momentum_signal,
    "LOW-VOL-TREND-v1": _low_vol_trend_signal,
    "BREAKOUT55-v1": _breakout55_signal,
    "MACD-CROSS-v1": _macd_cross_signal,
    "RSI-RECOVERY-v1": _rsi_recovery_signal,
    "BOLLINGER-REBOUND-v1": _bollinger_rebound_signal,
    "BOLLINGER-BREAKOUT-v1": _bollinger_breakout_signal,
    "KD-RECOVERY-v1": _kd_recovery_signal,
    "MOMENTUM126-v1": _momentum126_signal,
}


def _date_text(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("競賽股票資料為空白。")
    corporate_action_attrs = {
        "dividends": list(frame.attrs.get("dividends", [])),
        "split_adjustments": list(frame.attrs.get("split_adjustments", [])),
        "dividend_source": frame.attrs.get("dividend_source"),
        "price_basis": frame.attrs.get("price_basis"),
    }
    prepared = add_indicators(frame.copy()).sort_index()
    prepared["Prior20High"] = (
        prepared["High"].shift(1).rolling(window=20, min_periods=20).max()
    )
    prepared["Prior55High"] = (
        prepared["High"].shift(1).rolling(window=55, min_periods=55).max()
    )
    prepared["Return60"] = (
        prepared["Close"] / prepared["Close"].shift(60) - 1
    )
    prepared["Return126"] = (
        prepared["Close"] / prepared["Close"].shift(126) - 1
    )
    prepared = prepared.replace([math.inf, -math.inf], math.nan)
    prepared.attrs.update(corporate_action_attrs)
    return prepared


def _close_position(
    *,
    cash: float,
    shares: int,
    price: float,
    commission_rate: float,
    transaction_tax_rate: float,
) -> tuple[float, dict[str, float]]:
    sale = _calculate_sell_value(
        price=price,
        shares=shares,
        commission_rate=commission_rate,
        transaction_tax_rate=transaction_tax_rate,
    )
    return cash + sale["net_amount"], sale


def _simulate_symbol(
    *,
    frame: pd.DataFrame,
    stock_code: str,
    robot_id: str,
    segment: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    initial_capital: float,
    commission_rate: float,
    transaction_tax_rate: float,
) -> dict[str, Any]:
    signal_function = SIGNAL_FUNCTIONS[robot_id]
    positions = [
        index
        for index, timestamp in enumerate(frame.index)
        if start <= pd.Timestamp(timestamp) <= end
    ]
    if not positions:
        return {
            "stock_code": stock_code,
            "data_available": False,
            "actual_start": None,
            "actual_end": None,
            "initial_capital": round(initial_capital, 2),
            "final_capital": round(initial_capital, 2),
            "total_commission": 0.0,
            "total_transaction_tax": 0.0,
            "total_dividends": 0.0,
            "trades": [],
            "equity_curve": [
                {"date": _date_text(start), "equity": round(initial_capital, 2)},
                {"date": _date_text(end), "equity": round(initial_capital, 2)},
            ],
        }

    cash = float(initial_capital)
    shares = 0
    entry_price: float | None = None
    entry_date: str | None = None
    entry_reason = ""
    entry_total_cost = 0.0
    entry_commission = 0.0
    stop_price: float | None = None
    target_price: float | None = None
    pending_entry: tuple[str, float] | None = None
    pending_exit: str | None = None
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    total_commission = 0.0
    total_transaction_tax = 0.0
    total_dividends = 0.0
    position_dividends = 0.0
    dividend_schedule = dividends_by_ex_date(frame)

    first_position = positions[0]
    if first_position > 0:
        prior = frame.iloc[first_position - 1]
        prior_previous = frame.iloc[max(0, first_position - 2)]
        enter, _, reason = signal_function(prior, prior_previous)
        prior_atr = _number(prior, "ATR")
        if enter and math.isfinite(prior_atr) and prior_atr > 0:
            pending_entry = (reason, prior_atr)

    for position in positions:
        row = frame.iloc[position]
        previous = frame.iloc[max(0, position - 1)]
        session_date = _date_text(frame.index[position])
        open_price = _number(row, "Open")
        high_price = _number(row, "High")
        low_price = _number(row, "Low")
        close_price = _number(row, "Close")

        if not _all_finite(open_price, high_price, low_price, close_price):
            continue

        # The holder before the ex-date open receives the distribution.  This
        # runs before open exits/entries so same-day buyers cannot receive it.
        dividend_per_share = dividend_schedule.get(session_date, 0.0)
        if shares > 0 and dividend_per_share > 0:
            received_dividend = shares * dividend_per_share
            cash += received_dividend
            total_dividends += received_dividend
            position_dividends += received_dividend

        if pending_exit and shares > 0:
            cash, sale = _close_position(
                cash=cash,
                shares=shares,
                price=open_price,
                commission_rate=commission_rate,
                transaction_tax_rate=transaction_tax_rate,
            )
            profit = sale["net_amount"] + position_dividends - entry_total_cost
            trades.append(
                {
                    "robot_id": robot_id,
                    "stock_code": stock_code,
                    "segment": segment,
                    "entry_date": entry_date,
                    "exit_date": session_date,
                    "entry_price": round(entry_price or 0.0, 4),
                    "exit_price": round(open_price, 4),
                    "shares": shares,
                    "profit": round(profit, 2),
                    "return_percent": round(
                        profit / entry_total_cost * 100 if entry_total_cost else 0.0,
                        4,
                    ),
                    "entry_reason": entry_reason,
                    "exit_reason": pending_exit,
                    "entry_commission": round(entry_commission, 2),
                    "exit_commission": round(sale["commission"], 2),
                    "transaction_tax": round(sale["transaction_tax"], 2),
                    "dividends": round(position_dividends, 2),
                    "stop_price": round(stop_price or 0.0, 4),
                    "target_price": round(target_price or 0.0, 4),
                }
            )
            total_commission += sale["commission"]
            total_transaction_tax += sale["transaction_tax"]
            shares = 0
            entry_price = None
            entry_date = None
            entry_total_cost = 0.0
            entry_commission = 0.0
            stop_price = None
            target_price = None
            pending_exit = None
            position_dividends = 0.0

        if pending_entry and shares == 0:
            reason, signal_atr = pending_entry
            purchasable_shares = _calculate_purchasable_shares(
                cash=cash,
                price=open_price,
                commission_rate=commission_rate,
            )
            if purchasable_shares > 0:
                purchase = _calculate_buy_cost(
                    price=open_price,
                    shares=purchasable_shares,
                    commission_rate=commission_rate,
                )
                cash -= purchase["total_cost"]
                shares = purchasable_shares
                entry_price = open_price
                entry_date = session_date
                entry_reason = reason
                entry_total_cost = purchase["total_cost"]
                entry_commission = purchase["commission"]
                stop_price = max(0.01, open_price - STOP_ATR_MULTIPLE * signal_atr)
                target_price = open_price + TARGET_ATR_MULTIPLE * signal_atr
                total_commission += purchase["commission"]
            pending_entry = None

        intraday_exit: tuple[float, str] | None = None
        if shares > 0 and stop_price is not None and target_price is not None:
            if low_price <= stop_price:
                intraday_exit = (min(open_price, stop_price), "2atr_stop")
            elif high_price >= target_price:
                intraday_exit = (max(open_price, target_price), "4atr_target")

        if intraday_exit is not None and shares > 0:
            exit_price, exit_reason = intraday_exit
            cash, sale = _close_position(
                cash=cash,
                shares=shares,
                price=exit_price,
                commission_rate=commission_rate,
                transaction_tax_rate=transaction_tax_rate,
            )
            profit = sale["net_amount"] + position_dividends - entry_total_cost
            trades.append(
                {
                    "robot_id": robot_id,
                    "stock_code": stock_code,
                    "segment": segment,
                    "entry_date": entry_date,
                    "exit_date": session_date,
                    "entry_price": round(entry_price or 0.0, 4),
                    "exit_price": round(exit_price, 4),
                    "shares": shares,
                    "profit": round(profit, 2),
                    "return_percent": round(
                        profit / entry_total_cost * 100 if entry_total_cost else 0.0,
                        4,
                    ),
                    "entry_reason": entry_reason,
                    "exit_reason": exit_reason,
                    "entry_commission": round(entry_commission, 2),
                    "exit_commission": round(sale["commission"], 2),
                    "transaction_tax": round(sale["transaction_tax"], 2),
                    "dividends": round(position_dividends, 2),
                    "stop_price": round(stop_price, 4),
                    "target_price": round(target_price, 4),
                }
            )
            total_commission += sale["commission"]
            total_transaction_tax += sale["transaction_tax"]
            shares = 0
            entry_price = None
            entry_date = None
            entry_total_cost = 0.0
            entry_commission = 0.0
            stop_price = None
            target_price = None
            position_dividends = 0.0

        equity_curve.append(
            {
                "date": session_date,
                "equity": round(cash + shares * close_price, 2),
            }
        )

        enter, exit_now, reason = signal_function(row, previous)
        if shares > 0 and exit_now:
            pending_exit = f"strategy_exit:{reason}"
            pending_entry = None
        elif shares == 0 and enter:
            atr = _number(row, "ATR")
            if math.isfinite(atr) and atr > 0:
                pending_entry = (reason, atr)
            pending_exit = None
        else:
            pending_entry = None
            if shares == 0:
                pending_exit = None

    if shares > 0:
        final_row = frame.iloc[positions[-1]]
        final_price = _number(final_row, "Close")
        final_date = _date_text(frame.index[positions[-1]])
        cash, sale = _close_position(
            cash=cash,
            shares=shares,
            price=final_price,
            commission_rate=commission_rate,
            transaction_tax_rate=transaction_tax_rate,
        )
        profit = sale["net_amount"] + position_dividends - entry_total_cost
        trades.append(
            {
                "robot_id": robot_id,
                "stock_code": stock_code,
                "segment": segment,
                "entry_date": entry_date,
                "exit_date": final_date,
                "entry_price": round(entry_price or 0.0, 4),
                "exit_price": round(final_price, 4),
                "shares": shares,
                "profit": round(profit, 2),
                "return_percent": round(
                    profit / entry_total_cost * 100 if entry_total_cost else 0.0,
                    4,
                ),
                "entry_reason": entry_reason,
                "exit_reason": "segment_end",
                "entry_commission": round(entry_commission, 2),
                "exit_commission": round(sale["commission"], 2),
                "transaction_tax": round(sale["transaction_tax"], 2),
                "dividends": round(position_dividends, 2),
                "stop_price": round(stop_price or 0.0, 4),
                "target_price": round(target_price or 0.0, 4),
            }
        )
        total_commission += sale["commission"]
        total_transaction_tax += sale["transaction_tax"]
        if equity_curve:
            equity_curve[-1]["equity"] = round(cash, 2)

    return {
        "stock_code": stock_code,
        "data_available": True,
        "actual_start": _date_text(frame.index[positions[0]]),
        "actual_end": _date_text(frame.index[positions[-1]]),
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(cash, 2),
        "total_commission": round(total_commission, 2),
        "total_transaction_tax": round(total_transaction_tax, 2),
        "total_dividends": round(total_dividends, 2),
        "trades": trades,
        "equity_curve": equity_curve,
    }


def _aggregate_portfolio(
    symbol_results: list[dict[str, Any]],
    *,
    initial_capital: float,
) -> dict[str, Any]:
    trades = [trade for result in symbol_results for trade in result["trades"]]
    final_capital = sum(float(result["final_capital"]) for result in symbol_results)
    winning_trade_count = sum(float(trade["profit"]) > 0 for trade in trades)
    series: list[pd.Series] = []
    for result in symbol_results:
        curve = result["equity_curve"]
        if not curve:
            continue
        series.append(
            pd.Series(
                [float(point["equity"]) for point in curve],
                index=pd.to_datetime([point["date"] for point in curve]),
            )
        )
    if series:
        portfolio = pd.concat(series, axis=1).sort_index().ffill().bfill().sum(axis=1)
        peak = portfolio.cummax().replace(0, math.nan)
        drawdown = ((peak - portfolio) / peak * 100).fillna(0.0)
        max_drawdown = float(drawdown.max())
        equity_curve = [
            {"date": _date_text(index), "equity": round(float(value), 2)}
            for index, value in portfolio.items()
        ]
    else:
        max_drawdown = 0.0
        equity_curve = []
    trade_count = len(trades)
    return {
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(final_capital, 2),
        "total_return_percent": round(
            (final_capital - initial_capital) / initial_capital * 100,
            4,
        ),
        "trade_count": trade_count,
        "winning_trade_count": int(winning_trade_count),
        "win_rate_percent": round(
            winning_trade_count / trade_count * 100 if trade_count else 0.0,
            4,
        ),
        "max_drawdown_percent": round(max_drawdown, 4),
        "total_commission": round(
            sum(float(result["total_commission"]) for result in symbol_results),
            2,
        ),
        "total_transaction_tax": round(
            sum(float(result["total_transaction_tax"]) for result in symbol_results),
            2,
        ),
        "total_dividends": round(
            sum(float(result.get("total_dividends", 0.0)) for result in symbol_results),
            2,
        ),
        "trades": trades,
        "equity_curve": equity_curve,
    }


def _competition_official_months(
    stock_code: str,
    *,
    as_of: date | None = None,
) -> int:
    current = as_of or date.today()
    requested = RESEARCH_HISTORY_MONTHS + BACKTEST_WARMUP_MONTHS
    listing = COMPETITION_LISTING_DATES.get(stock_code)

    if listing is None:
        return requested

    months_since_listing = (
        (current.year - listing.year) * 12
        + current.month
        - listing.month
        + 1
    )
    return min(requested, max(1, months_since_listing))


def _expected_competition_history_month(
    stock_code: str,
    *,
    as_of: date | None = None,
) -> str:
    current = as_of or date.today()
    month_count = _competition_official_months(stock_code, as_of=current)
    current_month_index = current.year * 12 + current.month - 1
    expected_month_index = current_month_index - month_count + 1
    listing = COMPETITION_LISTING_DATES.get(stock_code)

    if listing is not None:
        listing_month_index = listing.year * 12 + listing.month - 1
        expected_month_index = max(expected_month_index, listing_month_index)

    year, zero_based_month = divmod(expected_month_index, 12)
    return f"{year:04d}-{zero_based_month + 1:02d}"


def _competition_coverage_is_complete(
    stock_code: str,
    item: dict[str, Any],
    *,
    as_of: date | None = None,
) -> bool:
    current = as_of or date.today()
    expected_start_month = _expected_competition_history_month(
        stock_code,
        as_of=current,
    )
    start = item.get("start")
    end = item.get("end")

    if not start or not end or not item.get("complete_month_coverage"):
        return False

    actual_start_month = str(start)[:7]
    fresh_cutoff = pd.Timestamp(current) - pd.Timedelta(days=10)
    actual_end = pd.Timestamp(str(end)).normalize()
    return actual_start_month <= expected_start_month and actual_end >= fresh_cutoff


def _download_competition_frames() -> tuple[
    dict[str, pd.DataFrame],
    dict[str, str],
    dict[str, dict[str, Any]],
]:
    from stock import download_stock

    frames: dict[str, pd.DataFrame] = {}
    sources: dict[str, str] = {}
    coverage: dict[str, dict[str, Any]] = {}
    # 長期行情優先一次下載，避免官方免費逐月介面在冷啟動時因大量查詢遭限流；
    # 分割與配息仍由證交所資料校正。只有長期來源不完整時才受控回退官方逐月資料。
    for index, code in enumerate(COMPETITION_UNIVERSE):
        if index:
            time.sleep(COMPETITION_DOWNLOAD_PAUSE_SECONDS)
        requested_months = _competition_official_months(code)
        candidates = (
            {
                "prefer_official": False,
                "daily_period": "10y",
                "force_official_refresh": False,
            },
            {
                "prefer_official": True,
                "daily_period": "max",
                "force_official_refresh": True,
            },
        )
        last_item: dict[str, Any] = {}

        for candidate in candidates:
            frame = download_stock(
                code,
                daily_period=str(candidate["daily_period"]),
                prefer_official=bool(candidate["prefer_official"]),
                update_with_intraday=False,
                official_months=requested_months,
                force_official_refresh=bool(candidate["force_official_refresh"]),
                include_corporate_actions=True,
            )
            prepared = _prepare_frame(frame)
            item = frame_coverage(prepared)
            required_start_month = _expected_competition_history_month(code)
            item["required_start_month"] = required_start_month
            item["requested_span_complete"] = _competition_coverage_is_complete(
                code,
                item,
            )
            last_item = item

            if item["requested_span_complete"]:
                sources[code] = str(frame.attrs.get("source", "官方交易所資料"))
                frames[code] = prepared
                coverage[code] = item
                break
        else:
            raise TimeoutError(
                f"{code} 歷史資料不完整："
                f"需要從 {required_start_month} 起，實際僅有 {last_item.get('start') or '無資料'} 起。"
            )
    return frames, sources, coverage


def run_competition_on_frames(
    frames: dict[str, pd.DataFrame],
    *,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    sources: dict[str, str] | None = None,
    coverage: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    capital = float(initial_capital)
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("競賽初始資金必須大於 0。")
    if capital > MAX_INITIAL_CAPITAL:
        raise ValueError("競賽初始資金不能超過 2,000,000 元。")
    missing = [code for code in COMPETITION_UNIVERSE if code not in frames]
    if missing:
        raise ValueError("競賽缺少股票資料：" + "、".join(missing))

    latest_date = min(pd.Timestamp(frames[code].index.max()) for code in COMPETITION_UNIVERSE)
    competition_start = (
        latest_date - pd.DateOffset(years=PREFERRED_RESEARCH_YEARS)
    ).normalize()
    forward_start = (
        latest_date - pd.DateOffset(months=FORWARD_HOLDOUT_MONTHS)
    ).normalize()
    backtest_start = competition_start
    backtest_end = forward_start - pd.Timedelta(days=1)
    per_symbol_capital = capital / len(COMPETITION_UNIVERSE)
    robot_outputs: list[dict[str, Any]] = []
    ranking_rows: list[dict[str, Any]] = []

    for spec in ROBOT_SPECS:
        frozen = freeze_robot_spec(spec)
        robot_id = str(spec["robot_id"])
        segment_outputs: dict[str, dict[str, Any]] = {}
        for segment, start, end in (
            ("backtest", backtest_start, backtest_end),
            ("forward", forward_start, latest_date),
        ):
            symbol_results = [
                _simulate_symbol(
                    frame=frames[code],
                    stock_code=code,
                    robot_id=robot_id,
                    segment=segment,
                    start=start,
                    end=end,
                    initial_capital=per_symbol_capital,
                    commission_rate=COMMISSION_RATE,
                    transaction_tax_rate=ETF_TRANSACTION_TAX_RATE,
                )
                for code in COMPETITION_UNIVERSE
            ]
            segment_outputs[segment] = _aggregate_portfolio(
                symbol_results,
                initial_capital=capital,
            )
        forward = segment_outputs["forward"]
        ranking_rows.append(
            {
                "robot_id": robot_id,
                "robot_version": "1",
                "rule_fingerprint": frozen["rule_fingerprint"],
                "initial_capital": capital,
                "period_start": _date_text(forward_start),
                "period_end": _date_text(latest_date),
                "cost_model_id": "TWSE-ETF-0.1425-0.1-CORP-ACTIONS-v2",
                "risk_model_id": "ATR-2R-STOP-4R-TARGET-v1",
                "market_universe_id": "TW-ETF-CORE-4-v1",
                "trade_count": forward["trade_count"],
                "winning_trade_count": forward["winning_trade_count"],
                "total_return_percent": forward["total_return_percent"],
                "max_drawdown_percent": forward["max_drawdown_percent"],
            }
        )
        robot_outputs.append(
            {
                "robot_id": robot_id,
                "name": spec["name"],
                "family": spec["family"],
                "rule_fingerprint": frozen["rule_fingerprint"],
                "spec": spec,
                "backtest": segment_outputs["backtest"],
                "forward": forward,
            }
        )

    ranking = rank_robot_results(ranking_rows)
    rank_by_id = {row["robot_id"]: row for row in ranking["robots"]}
    for output in robot_outputs:
        rank_row = rank_by_id[output["robot_id"]]
        output["rank"] = rank_row["rank"]
        output["wilson_lower_percent"] = rank_row["wilson_lower_percent"]
        output["wilson_upper_percent"] = rank_row["wilson_upper_percent"]
    robot_outputs.sort(key=lambda item: int(item["rank"]))

    leader = robot_outputs[0]
    forward_trades = int(leader["forward"]["trade_count"])
    qualified = forward_trades >= MIN_FORWARD_TRADES_FOR_CHAMPION
    run_basis = {
        "latest_date": _date_text(latest_date),
        "capital": capital,
        "universe": list(COMPETITION_UNIVERSE),
        "corporate_actions_version": "TWSE-SPLIT-DIVIDEND-v1",
        "fingerprints": [robot["rule_fingerprint"] for robot in robot_outputs],
    }
    run_id = hashlib.sha256(
        json.dumps(run_basis, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]

    return {
        "run_id": run_id,
        "status": "completed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": sources or {},
        "history_coverage": coverage or {
            code: frame_coverage(frames[code])
            for code in COMPETITION_UNIVERSE
        },
        "requested_history_months": RESEARCH_HISTORY_MONTHS,
        "periods": {
            "backtest": {
                "start": _date_text(backtest_start),
                "end": _date_text(backtest_end),
                "purpose": "前 4 年固定規則歷史檢查，不在執行中調參。",
            },
            "forward": {
                "start": _date_text(forward_start),
                "end": _date_text(latest_date),
                "purpose": "最後 1 年 walk-forward 樣本外模擬；正式排名只使用此區間。",
            },
        },
        "fairness": {
            "initial_capital": round(capital, 2),
            "capital_per_symbol": round(per_symbol_capital, 2),
            "market_universe": list(COMPETITION_UNIVERSE),
            "commission_rate": COMMISSION_RATE,
            "transaction_tax_rate": ETF_TRANSACTION_TAX_RATE,
            "execution": "signal at close, execute next session open",
            "stop_model": f"{STOP_ATR_MULTIPLE:g} ATR",
            "target_model": f"{TARGET_ATR_MULTIPLE:g} ATR",
            "same_bar_stop_target_policy": "stop first (conservative)",
        },
        "ranking": {
            "primary_metric": "forward Wilson 95% win-rate lower bound",
            "objective": ranking["objective"],
            "method": ranking["ranking_method"],
            "return_role": "總報酬只在 Wilson 下界與原始勝率同分時作為下一順位比較。",
            "minimum_forward_trades_for_champion": MIN_FORWARD_TRADES_FOR_CHAMPION,
            "leader_status": "qualified" if qualified else "provisional",
        },
        "leader": {
            "robot_id": leader["robot_id"],
            "name": leader["name"],
            "rank": 1,
            "qualified": qualified,
            "reason": (
                "已達最低前瞻交易樣本門檻。"
                if qualified
                else f"目前僅 {forward_trades} 筆前瞻交易，未達 {MIN_FORWARD_TRADES_FOR_CHAMPION} 筆門檻。"
            ),
        },
        "robots": robot_outputs,
        "disclosures": [
            "競賽優先使用五年資料：前 4 年做固定規則歷史檢查，最後 1 年做 walk-forward 樣本外排名。",
            "長期 OHLCV 會逐檔揭露實際來源；現行優先一次下載 Yahoo Finance 未調整行情，ETF 分割與現金配息仍使用證交所資料校正。",
            "每檔資料必須涵蓋要求的起始月份且中間沒有缺月，否則整場競賽直接中止，不會用殘缺資料產生排名。",
            "成立未滿五年的 ETF 只會使用上市後的真實資料，不會補造不存在的行情。",
            "個別 ETF 在尚無行情的區間，其等額配置會保留為現金；所有機器人適用完全相同規則。",
            "歷史價格會依 ETF 分割／反分割調整，持有期間並納入證交所公告的現金配息。",
            "最後 1 年區間是 walk-forward 歷史模擬，不冒充部署後累積的真實實盤前瞻紀錄。",
            "EMA、RSI、MACD、布林通道、KD、成交量與 ATR 的具體期間／門檻是固定的 v1 實證參數，不代表論文證明其為最優值。",
            "現階段只做多、無槓桿，且每檔 ETF 使用固定等額資金；所有交易均保存進出場與成本。",
        ],
        "references": [
            BROCK_REFERENCE,
            MOMENTUM_REFERENCE,
            TIME_SERIES_MOMENTUM_REFERENCE,
            REVERSAL_REFERENCE,
            VOLUME_MOMENTUM_REFERENCE,
            VOLATILITY_REFERENCE,
            TECHNICAL_PATTERN_REFERENCE,
        ],
    }


@lru_cache(maxsize=8)
def _run_competition_cached(initial_capital: float, cache_date: str) -> dict[str, Any]:
    frames, sources, coverage = _download_competition_frames()
    return run_competition_on_frames(
        frames,
        initial_capital=initial_capital,
        sources=sources,
        coverage=coverage,
    )


def run_competition(initial_capital: float = DEFAULT_INITIAL_CAPITAL) -> dict[str, Any]:
    capital = round(float(initial_capital), 2)
    return _run_competition_cached(capital, date.today().isoformat())
