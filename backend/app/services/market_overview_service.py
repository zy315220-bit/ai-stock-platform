from __future__ import annotations

import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any

import requests


TWSE_INDEX_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
TWSE_QUOTES_URL = (
    "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
)
TPEX_INDEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_index"
TPEX_QUOTES_URL = (
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
)
TWSE_TRADING_CALENDAR_URL = (
    "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK"
)
TWSE_DAILY_INDEX_URL = (
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
)

REQUEST_TIMEOUT = 10
CACHE_SECONDS = 60 * 5

_cache_lock = threading.Lock()
_market_cache: tuple[float, dict[str, Any]] | None = None

_equity_code = re.compile(r"^[1-9]\d{3}$")

SECTOR_INDICES = (
    ("半導體", "半導體類指數"),
    ("電子", "電子工業類指數"),
    ("電腦週邊", "電腦及週邊設備類指數"),
    ("電子零組件", "電子零組件類指數"),
    ("光電", "光電類指數"),
    ("通信網路", "通信網路類指數"),
    ("資訊服務", "資訊服務類指數"),
    ("金融保險", "金融保險類指數"),
    ("航運", "航運類指數"),
    ("鋼鐵", "鋼鐵類指數"),
    ("電機機械", "電機機械類指數"),
    ("汽車", "汽車類指數"),
    ("生技醫療", "生技醫療類指數"),
    ("化學生技", "化學生技醫療類指數"),
    ("塑膠", "塑膠類指數"),
)


def _safe_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")

    if text in {"", "-", "--", "N/A", "nan", "None"}:
        return None

    try:
        number = float(text)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def _signed_change(item: dict[str, Any], value_key: str) -> float | None:
    value = _safe_float(item.get(value_key))

    if value is None:
        return None

    direction = str(item.get("漲跌", "")).strip()
    if direction == "-" and value > 0:
        return -value

    return value


def _request_rows(url: str) -> list[dict[str, Any]]:
    response = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "AI-Stock-Platform/2.0 (+official market overview)",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, list):
        raise RuntimeError("交易所市場資料格式不正確。")

    return [item for item in payload if isinstance(item, dict)]


def _request_payload(
    url: str,
    *,
    params: dict[str, str],
) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        headers={
            "Accept": "application/json",
            "User-Agent": "AI-Stock-Platform/2.0 (+official sector trend)",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        raise RuntimeError("交易所歷史指數格式不正確。")

    return payload


def _iso_market_date(value: Any) -> str:
    text = str(value or "").strip().replace("/", "")

    if len(text) != 7 and len(text) != 8:
        return text

    try:
        if len(text) == 7:
            year = int(text[:3]) + 1911
            month = int(text[3:5])
            day = int(text[5:7])
        else:
            year = int(text[:4])
            month = int(text[4:6])
            day = int(text[6:8])

        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return text


def _calendar_dates_from_payload(payload: dict[str, Any]) -> list[date]:
    trading_dates: list[date] = []

    for row in payload.get("data", []):
        if not isinstance(row, list) or not row:
            continue

        iso_date = _iso_market_date(row[0])
        try:
            trading_dates.append(date.fromisoformat(iso_date))
        except ValueError:
            continue

    return trading_dates


def _price_index_rows_from_payload(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    payload_date = _iso_market_date(payload.get("date"))

    for table in payload.get("tables", []):
        if not isinstance(table, dict):
            continue

        fields = table.get("fields")
        rows = table.get("data")

        if (
            not isinstance(fields, list)
            or not isinstance(rows, list)
            or "指數" not in fields
            or "收盤指數" not in fields
            or "臺灣證券交易所" not in str(table.get("title", ""))
        ):
            continue

        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, list):
                continue

            item = dict(zip(fields, row, strict=False))
            item["日期"] = payload_date
            normalized.append(item)

        return normalized

    raise RuntimeError("交易所歷史價格指數欄位不完整。")


def _recent_month_starts(as_of: date, count: int = 3) -> list[date]:
    starts: list[date] = []
    year = as_of.year
    month = as_of.month

    for _ in range(count):
        starts.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    return starts


def _load_sector_trend_history(as_of_text: str) -> dict[str, Any]:
    as_of = date.fromisoformat(as_of_text)
    month_starts = _recent_month_starts(as_of)

    with ThreadPoolExecutor(max_workers=3) as executor:
        calendar_payloads = list(
            executor.map(
                lambda month_start: _request_payload(
                    TWSE_TRADING_CALENDAR_URL,
                    params={
                        "date": month_start.strftime("%Y%m%d"),
                        "response": "json",
                    },
                ),
                month_starts,
            )
        )

    trading_dates = sorted(
        {
            trading_date
            for payload in calendar_payloads
            for trading_date in _calendar_dates_from_payload(payload)
            if trading_date <= as_of
        }
    )

    if len(trading_dates) < 21:
        raise RuntimeError("官方交易日資料不足 21 個交易日。")

    five_session_start = trading_dates[-6]
    twenty_session_start = trading_dates[-21]
    anchor_dates = (five_session_start, twenty_session_start)

    with ThreadPoolExecutor(max_workers=2) as executor:
        anchor_payloads = list(
            executor.map(
                lambda anchor_date: _request_payload(
                    TWSE_DAILY_INDEX_URL,
                    params={
                        "date": anchor_date.strftime("%Y%m%d"),
                        "type": "IND",
                        "response": "json",
                    },
                ),
                anchor_dates,
            )
        )

    return {
        "as_of": as_of.isoformat(),
        "five_session_start": five_session_start.isoformat(),
        "twenty_session_start": twenty_session_start.isoformat(),
        "five_session_rows": _price_index_rows_from_payload(anchor_payloads[0]),
        "twenty_session_rows": _price_index_rows_from_payload(anchor_payloads[1]),
    }

def _index_entry(
    rows: list[dict[str, Any]],
    index_name: str,
) -> dict[str, Any] | None:
    item = next(
        (row for row in rows if row.get("指數") == index_name),
        None,
    )

    if item is None:
        return None

    return {
        "name": index_name,
        "date": _iso_market_date(item.get("日期")),
        "close": _safe_float(item.get("收盤指數")),
        "change": _signed_change(item, "漲跌點數"),
        "change_percent": _safe_float(item.get("漲跌百分比")),
        "source": "臺灣證券交易所 OpenAPI",
    }


def _tpex_index_entry(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None

    item = max(rows, key=lambda row: str(row.get("Date", "")))
    close = _safe_float(item.get("Close"))
    change = _safe_float(item.get("Change"))
    previous_close = (
        close - change
        if close is not None and change is not None
        else None
    )
    change_percent = (
        change / previous_close * 100
        if change is not None and previous_close not in {None, 0}
        else None
    )

    return {
        "name": "櫃買指數",
        "date": _iso_market_date(item.get("Date")),
        "close": close,
        "change": change,
        "change_percent": (
            round(change_percent, 2)
            if change_percent is not None
            else None
        ),
        "source": "證券櫃檯買賣中心 OpenAPI",
    }


def _breadth(
    rows: list[dict[str, Any]],
    *,
    code_key: str,
    change_key: str,
    value_key: str,
) -> dict[str, Any]:
    advancing = 0
    declining = 0
    unchanged = 0
    turnover = 0.0

    for item in rows:
        code = str(item.get(code_key, "")).strip()
        if not _equity_code.fullmatch(code):
            continue

        change = _safe_float(item.get(change_key))
        trade_value = _safe_float(item.get(value_key))

        if change is None:
            continue

        if change > 0:
            advancing += 1
        elif change < 0:
            declining += 1
        else:
            unchanged += 1

        if trade_value is not None and trade_value > 0:
            turnover += trade_value

    counted = advancing + declining + unchanged
    return {
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "counted": counted,
        "turnover": turnover,
    }


def _return_percent(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in {None, 0}:
        return None

    return round((current / previous - 1) * 100, 2)


def _percentile_scores(
    sectors: list[dict[str, Any]],
    key: str,
) -> dict[str, float]:
    values = [
        float(item[key])
        for item in sectors
        if item.get(key) is not None
    ]

    if len(values) < 2:
        return {
            str(item["index_name"]): 50.0
            for item in sectors
        }

    denominator = len(values) - 1
    return {
        str(item["index_name"]): round(
            sum(value < float(item[key]) for value in values)
            / denominator
            * 100,
            2,
        )
        if item.get(key) is not None
        else 50.0
        for item in sectors
    }


def _trend_label(
    return_5d: float | None,
    return_20d: float | None,
    excess_20d: float | None,
) -> str:
    if return_5d is None or return_20d is None:
        return "資料不足"
    if return_5d > 0 and return_20d > 0 and (excess_20d or 0) > 0:
        return "持續轉強"
    if return_5d > 0 and return_20d <= 0:
        return "短線轉強"
    if return_5d < 0 and return_20d < 0:
        return "持續轉弱"
    if return_5d < 0 and return_20d >= 0:
        return "短線轉弱"
    return "震盪整理"


def _sector_rows(
    index_rows: list[dict[str, Any]],
    *,
    five_session_rows: list[dict[str, Any]] | None = None,
    twenty_session_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    sectors: list[dict[str, Any]] = []
    benchmark_current = _index_entry(index_rows, "發行量加權股價指數")
    benchmark_5d = _index_entry(five_session_rows or [], "發行量加權股價指數")
    benchmark_20d = _index_entry(twenty_session_rows or [], "發行量加權股價指數")
    benchmark_return_5d = _return_percent(
        benchmark_current.get("close") if benchmark_current else None,
        benchmark_5d.get("close") if benchmark_5d else None,
    )
    benchmark_return_20d = _return_percent(
        benchmark_current.get("close") if benchmark_current else None,
        benchmark_20d.get("close") if benchmark_20d else None,
    )

    for sector_name, index_name in SECTOR_INDICES:
        entry = _index_entry(index_rows, index_name)
        if entry is None or entry["change_percent"] is None:
            continue

        change_percent = float(entry["change_percent"])
        five_session_entry = _index_entry(five_session_rows or [], index_name)
        twenty_session_entry = _index_entry(twenty_session_rows or [], index_name)
        return_5d = _return_percent(
            entry["close"],
            five_session_entry.get("close") if five_session_entry else None,
        )
        return_20d = _return_percent(
            entry["close"],
            twenty_session_entry.get("close") if twenty_session_entry else None,
        )
        excess_5d = (
            round(return_5d - benchmark_return_5d, 2)
            if return_5d is not None and benchmark_return_5d is not None
            else None
        )
        excess_20d = (
            round(return_20d - benchmark_return_20d, 2)
            if return_20d is not None and benchmark_return_20d is not None
            else None
        )
        sectors.append(
            {
                "name": sector_name,
                "index_name": index_name,
                "date": entry["date"],
                "close": entry["close"],
                "change_percent": change_percent,
                "direction": (
                    "上漲"
                    if change_percent > 0
                    else "下跌"
                    if change_percent < 0
                    else "持平"
                ),
                "return_5d": return_5d,
                "return_20d": return_20d,
                "excess_5d": excess_5d,
                "excess_20d": excess_20d,
                "trend_score": None,
                "trend_rank": None,
                "trend_label": _trend_label(return_5d, return_20d, excess_20d),
            }
        )

    sectors.sort(key=lambda item: item["change_percent"], reverse=True)

    for rank, item in enumerate(sectors, start=1):
        item["rank"] = rank

    daily_scores = _percentile_scores(sectors, "change_percent")
    five_day_scores = _percentile_scores(sectors, "return_5d")
    twenty_day_scores = _percentile_scores(sectors, "return_20d")

    for item in sectors:
        if item["return_5d"] is None or item["return_20d"] is None:
            continue

        index_name = str(item["index_name"])
        item["trend_score"] = round(
            daily_scores[index_name] * 0.2
            + five_day_scores[index_name] * 0.35
            + twenty_day_scores[index_name] * 0.45,
            1,
        )

    trend_ready = sorted(
        (item for item in sectors if item["trend_score"] is not None),
        key=lambda item: (item["trend_score"], item["return_20d"]),
        reverse=True,
    )
    for trend_rank, item in enumerate(trend_ready, start=1):
        item["trend_rank"] = trend_rank

    return sectors


def _market_regime(
    indices: list[dict[str, Any]],
    advancing: int,
    declining: int,
) -> tuple[str, float, str]:
    index_changes = [
        float(item["change_percent"])
        for item in indices
        if item.get("change_percent") is not None
    ]
    average_change = (
        sum(index_changes) / len(index_changes)
        if index_changes
        else 0.0
    )
    directional_count = advancing + declining
    breadth = (
        (advancing - declining) / directional_count
        if directional_count
        else 0.0
    )
    score = max(
        0.0,
        min(100.0, 50 + average_change * 8 + breadth * 25),
    )

    if score >= 60:
        return "偏多", round(score, 1), "主要指數與上漲家數整體偏強"
    if score <= 40:
        return "偏空", round(score, 1), "主要指數與下跌家數整體偏弱"

    return "中性", round(score, 1), "指數漲跌與市場廣度尚未形成一致方向"


def build_market_overview(
    twse_indices: list[dict[str, Any]],
    twse_quotes: list[dict[str, Any]],
    tpex_indices: list[dict[str, Any]],
    tpex_quotes: list[dict[str, Any]],
    sector_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    twse_index = _index_entry(twse_indices, "發行量加權股價指數")
    tpex_index = _tpex_index_entry(tpex_indices)
    indices = [item for item in (twse_index, tpex_index) if item is not None]

    twse_breadth = _breadth(
        twse_quotes,
        code_key="Code",
        change_key="Change",
        value_key="TradeValue",
    )
    tpex_breadth = _breadth(
        tpex_quotes,
        code_key="SecuritiesCompanyCode",
        change_key="Change",
        value_key="TransactionAmount",
    )

    advancing = twse_breadth["advancing"] + tpex_breadth["advancing"]
    declining = twse_breadth["declining"] + tpex_breadth["declining"]
    unchanged = twse_breadth["unchanged"] + tpex_breadth["unchanged"]
    turnover = twse_breadth["turnover"] + tpex_breadth["turnover"]
    regime, regime_score, regime_reason = _market_regime(
        indices,
        advancing,
        declining,
    )
    history = sector_history or {}
    sectors = _sector_rows(
        twse_indices,
        five_session_rows=history.get("five_session_rows"),
        twenty_session_rows=history.get("twenty_session_rows"),
    )
    trend_available = bool(
        sectors and all(item["trend_score"] is not None for item in sectors)
    )
    dates = sorted(
        {
            item["date"]
            for item in indices
            if item.get("date")
        }
    )

    return {
        "updated_at": dates[-1] if dates else "",
        "source_dates": dates,
        "dates_aligned": len(dates) <= 1,
        "indices": {
            "twse": twse_index,
            "tpex": tpex_index,
        },
        "market": {
            "turnover_billion": round(turnover / 1_000_000_000, 1),
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "breadth_ratio": (
                round(advancing / declining, 2)
                if declining
                else None
            ),
            "regime": regime,
            "regime_score": regime_score,
            "regime_reason": regime_reason,
        },
        "sectors": sectors,
        "sector_trend": {
            "available": trend_available,
            "as_of": history.get("as_of") if trend_available else None,
            "five_session_start": (
                history.get("five_session_start") if trend_available else None
            ),
            "twenty_session_start": (
                history.get("twenty_session_start") if trend_available else None
            ),
            "method": (
                "以最近 1、5、20 個交易日的產業價格指數橫斷面百分位，"
                "分別給予 20%、35%、45% 權重；另揭露相對加權指數超額報酬。"
            ),
        },
        "method": (
            "盤後資料取自證交所與櫃買中心 OpenAPI；市場狀態綜合加權指數、"
            "櫃買指數與上市櫃普通股漲跌家數。產業頁同時揭露當日、5 日、"
            "20 日價格表現與相對大盤超額報酬。"
        ),
        "sources": [
            {
                "name": "臺灣證券交易所 OpenAPI",
                "url": "https://openapi.twse.com.tw/",
            },
            {
                "name": "證券櫃檯買賣中心 OpenAPI",
                "url": "https://www.tpex.org.tw/openapi/",
            },
        ],
    }


def get_market_overview() -> dict[str, Any]:
    global _market_cache

    now = time.monotonic()
    with _cache_lock:
        if _market_cache and now - _market_cache[0] < CACHE_SECONDS:
            return _market_cache[1]

    urls = (
        TWSE_INDEX_URL,
        TWSE_QUOTES_URL,
        TPEX_INDEX_URL,
        TPEX_QUOTES_URL,
    )

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            twse_indices, twse_quotes, tpex_indices, tpex_quotes = list(
                executor.map(_request_rows, urls)
            )
    except (requests.RequestException, RuntimeError, ValueError) as error:
        with _cache_lock:
            if _market_cache:
                return _market_cache[1]

        raise RuntimeError("官方市場資料暫時無法取得，請稍後再試。") from error

    basic_result = build_market_overview(
        twse_indices,
        twse_quotes,
        tpex_indices,
        tpex_quotes,
    )

    sector_history: dict[str, Any] | None = None
    if basic_result["indices"]["twse"]:
        try:
            sector_history = _load_sector_trend_history(
                basic_result["indices"]["twse"]["date"]
            )
        except (requests.RequestException, RuntimeError, ValueError):
            sector_history = None

    result = build_market_overview(
        twse_indices,
        twse_quotes,
        tpex_indices,
        tpex_quotes,
        sector_history=sector_history,
    )

    with _cache_lock:
        _market_cache = (now, result)

    return result
