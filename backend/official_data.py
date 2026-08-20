"""Free historical daily prices from Taiwan's official exchanges.

Yahoo Finance is still useful for intraday data, but it can rate-limit public
requests.  This module provides a no-key fallback for daily OHLCV data using
the TWSE and TPEx historical price reports.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from functools import lru_cache
import re
import time
from typing import Any, Callable

import pandas as pd
import requests


TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
DEFAULT_MONTHS = 10
REQUEST_TIMEOUT_SECONDS = 8
MAX_MONTH_WORKERS = 5
LONG_HISTORY_MONTH_THRESHOLD = 24
MONTH_MAX_ATTEMPTS = 2
MONTH_RETRY_DELAY_SECONDS = 0.15

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (compatible; AI-Stock-Platform/1.0; "
        "+https://github.com/zy315220-bit/ai-stock-platform)"
    ),
}


def _month_starts(as_of: date, months: int) -> list[date]:
    output: list[date] = []

    for offset in range(max(1, months)):
        month_index = as_of.year * 12 + as_of.month - 1 - offset
        year, zero_based_month = divmod(month_index, 12)
        output.append(date(year, zero_based_month + 1, 1))

    return output


def _month_worker_count(month_count: int) -> int:
    if month_count <= 0:
        return 1
    if month_count > LONG_HISTORY_MONTH_THRESHOLD:
        return 2
    return min(MAX_MONTH_WORKERS, month_count)


def _number(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip().replace(",", "")
    text = text.lstrip("+Xx")

    if text in {"", "-", "--", "---", "N/A"}:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def _roc_date(value: Any) -> pd.Timestamp | None:
    match = re.fullmatch(
        r"\s*(\d{2,3})/(\d{1,2})/(\d{1,2})\s*",
        str(value),
    )

    if not match:
        return None

    year, month, day = (int(part) for part in match.groups())

    try:
        return pd.Timestamp(year=year + 1911, month=month, day=day)
    except ValueError:
        return None


def _rows_to_frame(
    rows: list[list[Any]],
    *,
    volume_multiplier: int,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, list) or len(row) < 7:
            continue

        timestamp = _roc_date(row[0])
        volume = _number(row[1])
        open_price = _number(row[3])
        high_price = _number(row[4])
        low_price = _number(row[5])
        close_price = _number(row[6])

        if (
            timestamp is None
            or open_price is None
            or high_price is None
            or low_price is None
            or close_price is None
        ):
            continue

        records.append(
            {
                "Date": timestamp,
                "Open": open_price,
                "High": high_price,
                "Low": low_price,
                "Close": close_price,
                "Volume": (volume or 0.0) * volume_multiplier,
            }
        )

    if not records:
        return pd.DataFrame()

    frame = pd.DataFrame.from_records(records).set_index("Date")
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame.sort_index()


def _fetch_twse_month(stock_code: str, month: date) -> tuple[pd.DataFrame, str]:
    response = requests.get(
        TWSE_URL,
        params={
            "date": month.strftime("%Y%m%d"),
            "stockNo": stock_code,
            "response": "json",
        },
        headers=_HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()

    if str(payload.get("stat", "")).upper() != "OK":
        return pd.DataFrame(), ""

    frame = _rows_to_frame(payload.get("data") or [], volume_multiplier=1)
    title = str(payload.get("title") or "")
    return frame, title


def _fetch_tpex_month(stock_code: str, month: date) -> tuple[pd.DataFrame, str]:
    response = requests.post(
        TPEX_URL,
        data={
            "code": stock_code,
            "date": month.strftime("%Y/%m/%d"),
            "response": "json",
        },
        headers=_HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()

    if str(payload.get("stat", "")).lower() != "ok":
        return pd.DataFrame(), ""

    tables = payload.get("tables") or []
    table = tables[0] if tables and isinstance(tables[0], dict) else {}
    frame = _rows_to_frame(table.get("data") or [], volume_multiplier=1000)
    name = str(payload.get("name") or "")
    return frame, name


def _download_market(
    stock_code: str,
    months: list[date],
    fetcher: Callable[[str, date], tuple[pd.DataFrame, str]],
) -> tuple[pd.DataFrame, str]:
    frames: list[pd.DataFrame] = []
    name = ""

    def fetch_month(month: date) -> tuple[pd.DataFrame, str]:
        fetched_name = ""

        for attempt in range(MONTH_MAX_ATTEMPTS):
            try:
                frame, current_name = fetcher(stock_code, month)
            except (requests.RequestException, ValueError, TypeError):
                frame, current_name = pd.DataFrame(), ""

            if current_name:
                fetched_name = current_name

            if not frame.empty:
                return frame, fetched_name

            if attempt + 1 < MONTH_MAX_ATTEMPTS:
                time.sleep(MONTH_RETRY_DELAY_SECONDS)

        return pd.DataFrame(), fetched_name

    # TWSE／TPEx 對長期間大量月查詢會暫時限流，且可能只留下近期月份。
    # 兩年內互動圖表維持並行；超過兩年的研究／競賽資料依序下載，
    # 避免不完整結果進入 LRU 快取後持續污染回測。
    worker_count = _month_worker_count(len(months))
    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:
        futures = {
            executor.submit(fetch_month, month): month
            for month in months
        }

        for future in as_completed(futures):
            frame, fetched_name = future.result()

            if not frame.empty:
                frames.append(frame)
            if fetched_name and not name:
                name = fetched_name

    if not frames:
        return pd.DataFrame(), name

    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined, name


@lru_cache(maxsize=128)
def _download_cached(
    stock_code: str,
    market: str,
    months: int,
    current_month: str,
) -> pd.DataFrame:
    as_of = date.fromisoformat(f"{current_month}-01")
    month_list = _month_starts(as_of, months)

    if market == "上市":
        frame, name = _download_market(stock_code, month_list, _fetch_twse_month)
        ticker = f"{stock_code}.TW"
        source = "臺灣證券交易所"
    elif market == "上櫃":
        frame, name = _download_market(stock_code, month_list, _fetch_tpex_month)
        ticker = f"{stock_code}.TWO"
        source = "證券櫃檯買賣中心"
    else:
        raise ValueError(f"不支援的市場：{market}")

    if not frame.empty:
        frame.attrs.update(
            {
                "ticker": ticker,
                "stock_code": stock_code,
                "market": market,
                "interval": "1d",
                "source": source,
                "name": name,
            }
        )

    return frame


def download_official_history(
    stock_code: str,
    *,
    market: str,
    months: int = DEFAULT_MONTHS,
) -> pd.DataFrame:
    """Download official daily OHLCV data and return an independent copy."""

    code = str(stock_code).strip().upper()
    current_month = date.today().strftime("%Y-%m")
    frame = _download_cached(code, market, months, current_month)
    return frame.copy()
