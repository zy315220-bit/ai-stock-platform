from __future__ import annotations

"""
技術指標計算模組。

輸入：
    包含 Open、High、Low、Close、Volume 的 DataFrame。

輸出欄位：
    MA5、MA20、MA60
    EMA5、EMA20、EMA60
    EMA20Slope、EMA60Slope
    RSI
    MACD、Signal、MACD_Hist
    K、D
    Upper、Lower、BBWidth
    TR、ATR、ATRPercent、NATR
    PlusDI、MinusDI、ADX
    VMA20、VolumeRatio、VolumeChange
    PriceChange、PriceChangePercent
"""


import numpy as np
import pandas as pd


# ==================================================
# 共用工具
# ==================================================

def _flatten_columns(df):
    """
    處理新版 yfinance 可能產生的 MultiIndex 欄位。
    """

    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)

    return df


def _validate_dataframe(df):
    """
    整理並檢查輸入資料。
    """

    if df is None:
        raise ValueError("股票資料不能是 None。")

    if not isinstance(df, pd.DataFrame):
        raise TypeError("股票資料必須是 pandas DataFrame。")

    if df.empty:
        raise ValueError("股票資料是空的。")

    df = df.copy()

    df = _flatten_columns(df)

    # 移除重複欄位
    df = df.loc[:, ~df.columns.duplicated()].copy()

    # 日期由舊到新排序。
    # 同時支援：
    # 1. Date 欄位
    # 2. DatetimeIndex
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(
            df["Date"],
            errors="coerce",
        )

        df = df.dropna(
            subset=["Date"]
        )

        df = (
            df
            .sort_values("Date")
            .drop_duplicates(
                subset=["Date"],
                keep="last",
            )
            .reset_index(drop=True)
        )

    else:
        try:
            df.index = pd.to_datetime(
                df.index,
                errors="coerce",
            )

            df = df.loc[
                ~df.index.isna()
            ]

            df = df.sort_index()

        except Exception:
            # 若 index 無法轉換成日期，
            # 至少維持原本順序。
            pass

        if df.index.has_duplicates:
            df = df[
                ~df.index.duplicated(
                    keep="last"
                )
            ].copy()

    required_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "缺少必要欄位："
            + ", ".join(missing_columns)
        )

    numeric_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    # 價格不能小於或等於0
    price_columns = [
        column
        for column in [
            "Open",
            "High",
            "Low",
            "Close",
        ]
        if column in df.columns
    ]

    for column in price_columns:
        df.loc[
            df[column] <= 0,
            column,
        ] = np.nan

    # 成交量不可為負數
    df.loc[
        df["Volume"] < 0,
        "Volume",
    ] = np.nan

    # OHLC 基本合理性檢查：
    # High 不得低於 Open、Close、Low；
    # Low 不得高於 Open、Close、High。
    invalid_ohlc = (
        (df["High"] < df["Low"])
        | (df["High"] < df["Open"])
        | (df["High"] < df["Close"])
        | (df["Low"] > df["Open"])
        | (df["Low"] > df["Close"])
    )

    if invalid_ohlc.any():
        df.loc[
            invalid_ohlc,
            [
                "Open",
                "High",
                "Low",
                "Close",
            ],
        ] = np.nan

    return df


def _wilder_average(series, period):
    """
    Wilder平滑平均。

    RSI、ATR與ADX皆可使用。
    """

    return series.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()


# ==================================================
# RSI
# ==================================================

def _add_rsi(df, period=14):
    close = df["Close"]

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = _wilder_average(
        gain,
        period,
    )

    avg_loss = _wilder_average(
        loss,
        period,
    )

    rs = (
        avg_gain
        / avg_loss.replace(0, np.nan)
    )

    rsi = 100 - (
        100 / (1 + rs)
    )

    # 沒有跌幅但有上漲
    rsi = rsi.mask(
        (avg_loss == 0)
        & (avg_gain > 0),
        100.0,
    )

    # 完全沒有漲跌
    rsi = rsi.mask(
        (avg_loss == 0)
        & (avg_gain == 0),
        50.0,
    )

    df["RSI"] = rsi.clip(
        lower=0,
        upper=100,
    )

    return df


# ==================================================
# MACD
# ==================================================

def _add_macd(
    df,
    fast_period=12,
    slow_period=26,
    signal_period=9,
):
    close = df["Close"]

    ema_fast = close.ewm(
        span=fast_period,
        adjust=False,
        min_periods=fast_period,
    ).mean()

    ema_slow = close.ewm(
        span=slow_period,
        adjust=False,
        min_periods=slow_period,
    ).mean()

    df["MACD"] = (
        ema_fast - ema_slow
    )

    df["Signal"] = df["MACD"].ewm(
        span=signal_period,
        adjust=False,
        min_periods=signal_period,
    ).mean()

    df["MACD_Hist"] = (
        df["MACD"]
        - df["Signal"]
    )

    return df


# ==================================================
# KD隨機指標
# ==================================================

def _add_stochastic(df, period=14):
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    lowest_low = low.rolling(
        window=period,
        min_periods=period,
    ).min()

    highest_high = high.rolling(
        window=period,
        min_periods=period,
    ).max()

    price_range = (
        highest_high - lowest_low
    ).replace(0, np.nan)

    rsv = (
        (close - lowest_low)
        / price_range
        * 100
    )

    df["K"] = rsv.ewm(
        alpha=1 / 3,
        adjust=False,
        min_periods=3,
    ).mean()

    df["D"] = df["K"].ewm(
        alpha=1 / 3,
        adjust=False,
        min_periods=3,
    ).mean()

    df["K"] = df["K"].clip(
        lower=0,
        upper=100,
    )

    df["D"] = df["D"].clip(
        lower=0,
        upper=100,
    )

    return df


# ==================================================
# ATR與True Range
# ==================================================

def _add_atr(df, period=14):
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["TR"] = true_range

    df["ATR"] = _wilder_average(
        true_range,
        period,
    )

    safe_close = close.replace(
        0,
        np.nan,
    )

    df["ATRPercent"] = (
        df["ATR"]
        / safe_close
        * 100
    )

    # NATR與ATRPercent相同概念，
    # 額外保留NATR名稱給評分模組使用
    df["NATR"] = df["ATRPercent"]

    return df


# ==================================================
# ADX、+DI與-DI
# ==================================================

def _add_adx(df, period=14):
    high = df["High"]
    low = df["Low"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where(
            (up_move > down_move)
            & (up_move > 0),
            up_move,
            0.0,
        ),
        index=df.index,
        dtype=float,
    )

    minus_dm = pd.Series(
        np.where(
            (down_move > up_move)
            & (down_move > 0),
            down_move,
            0.0,
        ),
        index=df.index,
        dtype=float,
    )

    if "TR" not in df.columns:
        df = _add_atr(
            df,
            period=period,
        )

    smoothed_plus_dm = _wilder_average(
        plus_dm,
        period,
    )

    smoothed_minus_dm = _wilder_average(
        minus_dm,
        period,
    )

    atr = df["ATR"].replace(
        0,
        np.nan,
    )

    plus_di = (
        100
        * smoothed_plus_dm
        / atr
    )

    minus_di = (
        100
        * smoothed_minus_dm
        / atr
    )

    di_sum = (
        plus_di + minus_di
    ).replace(0, np.nan)

    dx = (
        (plus_di - minus_di).abs()
        / di_sum
        * 100
    )

    adx = _wilder_average(
        dx,
        period,
    )

    df["PlusDI"] = plus_di.clip(
        lower=0,
        upper=100,
    )

    df["MinusDI"] = minus_di.clip(
        lower=0,
        upper=100,
    )

    df["ADX"] = adx.clip(
        lower=0,
        upper=100,
    )

    return df


# ==================================================
# 主函式
# ==================================================

def add_indicators(df):
    """
    將所有技術指標加入股票DataFrame。

    此函式不會直接dropna，
    由main.py依必要欄位決定要移除哪些資料。
    """

    df = _validate_dataframe(df)

    close = df["Close"]
    volume = df["Volume"]

    # ==============================================
    # 價格變化
    # ==============================================

    df["PriceChange"] = close.diff()

    df["PriceChangePercent"] = (
        close.pct_change(
            fill_method=None
        )
        * 100
    )

    # ==============================================
    # SMA簡單移動平均線
    # 保留原本欄位，避免report.py或其他程式壞掉
    # ==============================================

    df["MA5"] = close.rolling(
        window=5,
        min_periods=5,
    ).mean()

    df["MA20"] = close.rolling(
        window=20,
        min_periods=20,
    ).mean()

    df["MA60"] = close.rolling(
        window=60,
        min_periods=60,
    ).mean()

    # ==============================================
    # EMA指數移動平均線
    # 新版趨勢策略優先使用EMA20與EMA60
    # ==============================================

    df["EMA5"] = close.ewm(
        span=5,
        adjust=False,
        min_periods=5,
    ).mean()

    df["EMA20"] = close.ewm(
        span=20,
        adjust=False,
        min_periods=20,
    ).mean()

    df["EMA60"] = close.ewm(
        span=60,
        adjust=False,
        min_periods=60,
    ).mean()

    # ==============================================
    # EMA斜率
    # 使用5根K線變化量除以ATR，
    # 讓不同價位股票可以比較
    # ==============================================

    # ATR先加入，供EMA斜率使用
    df = _add_atr(
        df,
        period=14,
    )

    safe_atr = df["ATR"].replace(
        0,
        np.nan,
    )

    df["EMA20Slope"] = (
        df["EMA20"]
        - df["EMA20"].shift(5)
    ) / safe_atr

    df["EMA60Slope"] = (
        df["EMA60"]
        - df["EMA60"].shift(5)
    ) / safe_atr

    # 每一根K平均斜率
    df["EMA20SlopePerBar"] = (
        df["EMA20Slope"]
        / 5
    )

    df["EMA60SlopePerBar"] = (
        df["EMA60Slope"]
        / 5
    )

    # EMA距離，以ATR標準化
    df["EMA20EMA60DistanceATR"] = (
        df["EMA20"]
        - df["EMA60"]
    ) / safe_atr

    # ==============================================
    # RSI
    # ==============================================

    df = _add_rsi(
        df,
        period=14,
    )

    # ==============================================
    # MACD
    # ==============================================

    df = _add_macd(
        df,
        fast_period=12,
        slow_period=26,
        signal_period=9,
    )

    # ==============================================
    # KD
    # ==============================================

    df = _add_stochastic(
        df,
        period=14,
    )

    # ==============================================
    # 布林通道
    # ==============================================

    std20 = close.rolling(
        window=20,
        min_periods=20,
    ).std(
        ddof=0
    )

    # 布林中軌仍使用SMA20
    df["Middle"] = df["MA20"]

    df["Upper"] = (
        df["Middle"]
        + 2 * std20
    )

    df["Lower"] = (
        df["Middle"]
        - 2 * std20
    )

    safe_middle = df["Middle"].replace(
        0,
        np.nan,
    )

    df["BBWidth"] = (
        (df["Upper"] - df["Lower"])
        / safe_middle
        * 100
    )

    band_range = (
        df["Upper"] - df["Lower"]
    ).replace(0, np.nan)

    df["BBPosition"] = (
        (close - df["Lower"])
        / band_range
    )

    # ==============================================
    # ADX
    # ==============================================

    df = _add_adx(
        df,
        period=14,
    )

    # ==============================================
    # 成交量
    # ==============================================

    df["VMA5"] = volume.rolling(
        window=5,
        min_periods=5,
    ).mean()

    df["VMA20"] = volume.rolling(
        window=20,
        min_periods=20,
    ).mean()

    df["VolumeRatio"] = (
        volume
        / df["VMA20"].replace(
            0,
            np.nan,
        )
    )

    df["VolumeChange"] = (
        volume.pct_change(
            fill_method=None
        )
        * 100
    )

    # ==============================================
    # 常用價格位置
    # ==============================================

    df["DistanceEMA20Percent"] = (
        (close - df["EMA20"])
        / df["EMA20"].replace(
            0,
            np.nan,
        )
        * 100
    )

    df["DistanceEMA60Percent"] = (
        (close - df["EMA60"])
        / df["EMA60"].replace(
            0,
            np.nan,
        )
        * 100
    )

    df["DistanceEMA20ATR"] = (
        close - df["EMA20"]
    ) / safe_atr

    df["DistanceEMA60ATR"] = (
        close - df["EMA60"]
    ) / safe_atr

    # ==============================================
    # 資料清理
    # ==============================================

    df = df.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    return df