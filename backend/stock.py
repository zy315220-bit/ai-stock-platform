"""
台灣股票歷史資料下載模組。

功能：
1. 下載日線資料
2. 使用5分鐘資料更新最近交易日OHLCV
3. 下載60分鐘K線，供觸發評分使用
4. 自動嘗試上市與上櫃代號

資料來源：
    Yahoo Finance（yfinance）
"""

from typing import Any, Iterable, Optional

import pandas as pd
import yfinance as yf


REQUIRED_OHLCV_COLUMNS = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
]


def normalize_stock_code(stock_code: Any) -> str:
    """
    統一股票代號格式。

    範例：
        2330       -> 2330
        2330.TW    -> 2330
        6488.TWO   -> 6488
    """

    if stock_code is None:
        raise ValueError("股票代號不能是 None。")

    code = str(stock_code).strip().upper()

    if code.endswith(".TWO"):
        code = code[:-4]

    elif code.endswith(".TW"):
        code = code[:-3]

    code = code.strip()

    if not code:
        raise ValueError("股票代號不能空白。")

    return code


def build_ticker_list(stock_code: Any) -> list[str]:
    """
    建立 Yahoo Finance 股票代號候選清單。

    若使用者已指定 .TW 或 .TWO，
    則只下載該市場；否則先嘗試上市，再嘗試上櫃。
    """

    original = str(stock_code).strip().upper()

    if not original:
        raise ValueError("股票代號不能空白。")

    if original.endswith(".TWO"):
        code = normalize_stock_code(original)
        return [f"{code}.TWO"]

    if original.endswith(".TW"):
        code = normalize_stock_code(original)
        return [f"{code}.TW"]

    code = normalize_stock_code(original)

    return [
        f"{code}.TW",
        f"{code}.TWO",
    ]


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    將 yfinance 可能產生的 MultiIndex 欄位轉成一般欄位。

    同時移除重複欄位。
    """

    if df is None:
        return pd.DataFrame()

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    df = df.loc[
        :,
        ~df.columns.duplicated(),
    ].copy()

    return df


def _normalize_datetime_index(
    df: pd.DataFrame,
    timezone: str = "Asia/Taipei",
    remove_timezone: bool = False,
) -> pd.DataFrame:
    """
    整理 DataFrame 的時間索引。

    Parameters
    ----------
    timezone:
        有時區資料時，轉換到指定時區。

    remove_timezone:
        是否移除時區資訊，轉成 timezone-naive index。
    """

    if df is None or df.empty:
        return df

    df = df.copy()

    try:
        index = pd.to_datetime(
            df.index,
            errors="coerce",
        )
    except Exception:
        return df

    valid_mask = ~index.isna()

    if not valid_mask.all():
        df = df.loc[valid_mask].copy()
        index = index[valid_mask]

    if index.tz is not None:
        index = index.tz_convert(timezone)

        if remove_timezone:
            index = index.tz_localize(None)

    df.index = index

    df = df[
        ~df.index.duplicated(
            keep="last"
        )
    ].copy()

    return df.sort_index()


def _clean_ohlcv(
    df: pd.DataFrame,
    require_all_columns: bool = True,
) -> pd.DataFrame:
    """
    清理 OHLCV 資料。

    - 攤平欄位
    - 轉換成數值
    - 移除無效 Close
    - 移除重複索引
    - 排序
    """

    if df is None or df.empty:
        return pd.DataFrame()

    df = flatten_columns(df)

    missing_columns = [
        column
        for column in REQUIRED_OHLCV_COLUMNS
        if column not in df.columns
    ]

    if (
        require_all_columns
        and missing_columns
    ):
        return pd.DataFrame()

    available_columns = [
        column
        for column in REQUIRED_OHLCV_COLUMNS
        if column in df.columns
    ]

    if "Close" not in available_columns:
        return pd.DataFrame()

    df = df[available_columns].copy()

    for column in available_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=["Close"]
    ).copy()

    if df.empty:
        return df

    df = df[
        df["Close"] > 0
    ].copy()

    if "Volume" in df.columns:
        df["Volume"] = (
            df["Volume"]
            .fillna(0)
            .clip(lower=0)
        )

    df = df[
        ~df.index.duplicated(
            keep="last"
        )
    ].copy()

    return df.sort_index()


def _download_yfinance(
    ticker: str,
    period: str,
    interval: str,
    prepost: bool = False,
) -> pd.DataFrame:
    """
    呼叫 yfinance 並回傳清理前資料。

    下載失敗時回傳空 DataFrame，
    讓上層決定是否改試其他市場。
    """

    try:
        df = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False,
            prepost=prepost,
            group_by="column",
        )
    except Exception:
        return pd.DataFrame()

    if df is None:
        return pd.DataFrame()

    return df


def _aggregate_latest_intraday(
    intraday: pd.DataFrame,
) -> Optional[dict]:
    """
    將最近一個交易日的盤中K線合併成日線OHLCV。
    """

    if intraday is None or intraday.empty:
        return None

    intraday = _normalize_datetime_index(
        intraday,
        timezone="Asia/Taipei",
        remove_timezone=False,
    )

    if intraday.empty:
        return None

    latest_timestamp = intraday.index[-1]
    latest_date = latest_timestamp.date()

    date_mask = (
        intraday.index.date
        == latest_date
    )

    latest_data = intraday.loc[
        date_mask
    ].copy()

    if latest_data.empty:
        return None

    open_price = latest_data[
        "Open"
    ].dropna()

    high_price = latest_data[
        "High"
    ].dropna()

    low_price = latest_data[
        "Low"
    ].dropna()

    close_price = latest_data[
        "Close"
    ].dropna()

    volume = latest_data[
        "Volume"
    ].fillna(0)

    if (
        open_price.empty
        or high_price.empty
        or low_price.empty
        or close_price.empty
    ):
        return None

    return {
        "date": pd.Timestamp(latest_date),
        "Open": float(open_price.iloc[0]),
        "High": float(high_price.max()),
        "Low": float(low_price.min()),
        "Close": float(close_price.iloc[-1]),
        "Volume": float(volume.sum()),
        "last_timestamp": latest_timestamp,
    }


def _merge_latest_intraday(
    daily: pd.DataFrame,
    intraday: pd.DataFrame,
) -> pd.DataFrame:
    """
    使用最近交易日的盤中資料更新日線。

    若盤中資料無效，原日線會直接回傳。
    """

    summary = _aggregate_latest_intraday(
        intraday
    )

    if summary is None:
        return daily

    daily = daily.copy()

    # 日線索引統一移除時區，
    # 避免同一天因 timezone 不同而出現兩列。
    daily = _normalize_datetime_index(
        daily,
        timezone="Asia/Taipei",
        remove_timezone=True,
    )

    latest_index = summary["date"]

    for column in REQUIRED_OHLCV_COLUMNS:
        daily.loc[
            latest_index,
            column,
        ] = summary[column]

    daily = daily[
        ~daily.index.duplicated(
            keep="last"
        )
    ].copy()

    return daily.sort_index()


def _set_dataframe_attributes(
    df: pd.DataFrame,
    ticker: str,
    interval: str,
    source: str = "Yahoo Finance",
) -> pd.DataFrame:
    """
    加入資料來源資訊。
    """

    df.attrs["ticker"] = ticker
    df.attrs["stock_code"] = normalize_stock_code(
        ticker
    )
    df.attrs["market"] = (
        "上櫃"
        if ticker.endswith(".TWO")
        else "上市"
    )
    df.attrs["interval"] = interval
    df.attrs["source"] = source

    return df


def download_stock(
    stock_code: Any,
    daily_period: str = "max",
    update_with_intraday: bool = True,
    intraday_period: str = "5d",
    intraday_interval: str = "5m",
) -> pd.DataFrame:
    """
    下載股票日線資料。

    預設會再下載最近5分鐘資料，
    並更新最近交易日的日線OHLCV。

    Parameters
    ----------
    stock_code:
        股票代號，例如 2330、2330.TW、6488.TWO。

    daily_period:
        日線資料期間，預設為一年。

    update_with_intraday:
        是否使用盤中資料更新最近交易日。

    intraday_period:
        盤中資料期間。

    intraday_interval:
        盤中資料間隔。

    Returns
    -------
    pandas.DataFrame
        日線 OHLCV 資料。
    """

    ticker_list = build_ticker_list(
        stock_code
    )

    errors = []

    for ticker in ticker_list:
        # ==========================================
        # 1. 下載日線資料
        # ==========================================

        raw_daily = _download_yfinance(
            ticker=ticker,
            period=daily_period,
            interval="1d",
            prepost=False,
        )

        daily = _clean_ohlcv(
            raw_daily
        )

        if daily.empty:
            errors.append(
                f"{ticker}：沒有有效日線資料"
            )
            continue

        daily = _normalize_datetime_index(
            daily,
            timezone="Asia/Taipei",
            remove_timezone=True,
        )

        # ==========================================
        # 2. 使用盤中資料更新最新交易日
        # ==========================================

        if update_with_intraday:
            raw_intraday = _download_yfinance(
                ticker=ticker,
                period=intraday_period,
                interval=intraday_interval,
                prepost=False,
            )

            intraday = _clean_ohlcv(
                raw_intraday
            )

            if not intraday.empty:
                daily = _merge_latest_intraday(
                    daily=daily,
                    intraday=intraday,
                )

        daily = daily.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close",
            ]
        ).copy()

        if daily.empty:
            errors.append(
                f"{ticker}：清理後沒有可用資料"
            )
            continue

        daily = _set_dataframe_attributes(
            df=daily,
            ticker=ticker,
            interval="1d",
        )

        return daily

    detail = "；".join(errors)

    if detail:
        detail = f" 詳細資訊：{detail}。"

    raise ValueError(
        f"找不到股票代號 "
        f"{normalize_stock_code(stock_code)}，"
        f"請確認股票代號是否正確。"
        f"{detail}"
    )


def download_hourly_stock(
    stock_code: Any,
    period: str = "60d",
    interval: str = "60m",
) -> pd.DataFrame:
    """
    下載60分鐘K線資料。

    這份資料可傳入：

        calculate_score(
            ...,
            hourly_df=hourly_df,
        )

    Parameters
    ----------
    stock_code:
        股票代號，例如 2330、2330.TW、6488.TWO。

    period:
        下載期間，預設60天。

    interval:
        預設60分鐘K線。

    Returns
    -------
    pandas.DataFrame
        60分鐘 OHLCV 資料。
    """

    ticker_list = build_ticker_list(
        stock_code
    )

    errors = []

    for ticker in ticker_list:
        raw_hourly = _download_yfinance(
            ticker=ticker,
            period=period,
            interval=interval,
            prepost=False,
        )

        hourly = _clean_ohlcv(
            raw_hourly
        )

        if hourly.empty:
            errors.append(
                f"{ticker}：沒有有效60分鐘資料"
            )
            continue

        hourly = _normalize_datetime_index(
            hourly,
            timezone="Asia/Taipei",
            remove_timezone=False,
        )

        hourly = hourly.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close",
            ]
        ).copy()

        if hourly.empty:
            errors.append(
                f"{ticker}：清理後沒有可用60分鐘資料"
            )
            continue

        hourly = _set_dataframe_attributes(
            df=hourly,
            ticker=ticker,
            interval=interval,
        )

        return hourly

    detail = "；".join(errors)

    if detail:
        detail = f" 詳細資訊：{detail}。"

    raise ValueError(
        f"無法取得 "
        f"{normalize_stock_code(stock_code)} "
        f"的60分鐘資料。"
        f"{detail}"
    )