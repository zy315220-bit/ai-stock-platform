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
TWSE_COMPANY_PROFILE_URL = (
    "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
)
TPEX_MARKET_URL = (
    "https://www.tpex.org.tw/openapi/v1/tpex_mainborad_highlight"
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

# 證交所公開資訊觀測站的官方產業代碼。電子類指數涵蓋其下所有電子次產業；
# 化學生技醫療類指數則涵蓋化學與生技醫療兩個產業代碼。
SECTOR_INDUSTRY_CODES = {
    "半導體": {"24"},
    "電子": {"24", "25", "26", "27", "28", "29", "30", "31"},
    "電腦週邊": {"25"},
    "電子零組件": {"28"},
    "光電": {"26"},
    "通信網路": {"27"},
    "資訊服務": {"30"},
    "金融保險": {"17"},
    "航運": {"15"},
    "鋼鐵": {"10"},
    "電機機械": {"05"},
    "汽車": {"12"},
    "生技醫療": {"22"},
    "化學生技": {"21", "22"},
    "塑膠": {"03"},
}


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


def _request_optional_rows(url: str) -> list[dict[str, Any]]:
    try:
        return _request_rows(url)
    except (requests.RequestException, RuntimeError, ValueError):
        return []


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


def _request_optional_payload(
    url: str,
    *,
    params: dict[str, str],
) -> dict[str, Any] | None:
    try:
        return _request_payload(url, params=params)
    except (requests.RequestException, RuntimeError, ValueError):
        return None


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


def _turnover_rows_from_calendar_payload(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    fields = payload.get("fields")
    rows = payload.get("data")
    if not isinstance(fields, list) or not isinstance(rows, list):
        return []

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list):
            continue

        item = dict(zip(fields, row, strict=False))
        market_date = _iso_market_date(item.get("日期"))
        turnover = _safe_float(item.get("成交金額"))
        if not market_date or turnover is None:
            continue

        normalized.append(
            {
                "date": market_date,
                "turnover_billion": round(turnover / 1_000_000_000, 2),
            }
        )

    return normalized


def _leading_int(value: Any) -> int | None:
    matched = re.search(r"-?[\d,]+", str(value or ""))
    if not matched:
        return None

    try:
        return int(matched.group(0).replace(",", ""))
    except ValueError:
        return None


def _market_breadth_row_from_payload(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    payload_date = _iso_market_date(payload.get("date"))

    for table in payload.get("tables", []):
        if not isinstance(table, dict) or table.get("title") != "漲跌證券數合計":
            continue

        fields = table.get("fields")
        rows = table.get("data")
        if not isinstance(fields, list) or not isinstance(rows, list):
            continue

        values: dict[str, int] = {}
        for row in rows:
            if not isinstance(row, list):
                continue
            item = dict(zip(fields, row, strict=False))
            category = str(item.get("類型", ""))
            stock_count = _leading_int(item.get("股票"))
            if stock_count is not None:
                values[category] = stock_count

        advancing = values.get("上漲(漲停)")
        declining = values.get("下跌(跌停)")
        unchanged = values.get("持平")
        if advancing is None or declining is None or unchanged is None:
            return None

        directional = advancing + declining
        return {
            "date": payload_date,
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "advance_ratio": (
                round(advancing / directional * 100, 2)
                if directional
                else None
            ),
        }

    return None


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


def _load_calendar_payloads(reference_date: date) -> list[dict[str, Any]]:
    month_starts = _recent_month_starts(reference_date, count=2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(
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


def _load_sector_trend_history(
    as_of_text: str,
    calendar_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    as_of = date.fromisoformat(as_of_text)
    if calendar_payloads is None:
        calendar_payloads = _load_calendar_payloads(as_of)

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
    rolling_dates = trading_dates[-20:]

    with ThreadPoolExecutor(max_workers=22) as executor:
        anchor_futures = [
            executor.submit(
                _request_payload,
                TWSE_DAILY_INDEX_URL,
                params={
                    "date": anchor_date.strftime("%Y%m%d"),
                    "type": "IND",
                    "response": "json",
                },
            )
            for anchor_date in anchor_dates
        ]
        breadth_futures = [
            executor.submit(
                _request_optional_payload,
                TWSE_DAILY_INDEX_URL,
                params={
                    "date": trading_date.strftime("%Y%m%d"),
                    "type": "MS",
                    "response": "json",
                },
            )
            for trading_date in rolling_dates
        ]
        anchor_payloads = [future.result() for future in anchor_futures]
        breadth_payloads = [
            payload
            for future in breadth_futures
            if (payload := future.result()) is not None
        ]

    breadth_rows = [
        row
        for payload in breadth_payloads
        if (row := _market_breadth_row_from_payload(payload)) is not None
    ]
    turnover_rows = sorted(
        (
            row
            for payload in calendar_payloads
            for row in _turnover_rows_from_calendar_payload(payload)
            if date.fromisoformat(row["date"]) <= as_of
        ),
        key=lambda row: row["date"],
    )[-20:]

    return {
        "as_of": as_of.isoformat(),
        "five_session_start": five_session_start.isoformat(),
        "twenty_session_start": twenty_session_start.isoformat(),
        "five_session_rows": _price_index_rows_from_payload(anchor_payloads[0]),
        "twenty_session_rows": _price_index_rows_from_payload(anchor_payloads[1]),
        "market_breadth_rows": sorted(
            breadth_rows,
            key=lambda row: row["date"],
        ),
        "turnover_rows": turnover_rows,
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
    close = _safe_float(item.get("Close") or item.get("CloseIndex"))
    change = _safe_float(item.get("Change") or item.get("IndexChange"))
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


def _tpex_breadth(rows: list[dict[str, Any]]) -> dict[str, Any]:
    highlight = next(
        (
            item
            for item in rows
            if item.get("PriceRiseCompanyNumbers") is not None
        ),
        None,
    )
    if highlight is None:
        return _breadth(
            rows,
            code_key="SecuritiesCompanyCode",
            change_key="Change",
            value_key="TransactionAmount",
        )

    advancing = _leading_int(highlight.get("PriceRiseCompanyNumbers")) or 0
    declining = _leading_int(highlight.get("PriceDeclineCompanyNumbers")) or 0
    unchanged = _leading_int(highlight.get("PriceFlatCompanyNumbers")) or 0
    daily_value_million = _safe_float(highlight.get("DailyTradingValue")) or 0.0
    return {
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "counted": advancing + declining + unchanged,
        "turnover": daily_value_million * 1_000_000,
    }


def _sector_breadth(
    twse_quotes: list[dict[str, Any]],
    company_profiles: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    industry_by_code = {
        str(item.get("公司代號", "")).strip(): str(item.get("產業別", "")).strip()
        for item in company_profiles
        if _equity_code.fullmatch(str(item.get("公司代號", "")).strip())
    }
    quote_by_code = {
        str(item.get("Code", "")).strip(): item
        for item in twse_quotes
        if _equity_code.fullmatch(str(item.get("Code", "")).strip())
    }
    total_turnover = sum(
        trade_value
        for item in quote_by_code.values()
        if (trade_value := _safe_float(item.get("TradeValue"))) is not None
        and trade_value > 0
    )
    result: dict[str, dict[str, Any]] = {}

    for sector_name, industry_codes in SECTOR_INDUSTRY_CODES.items():
        advancing = 0
        declining = 0
        unchanged = 0
        turnover = 0.0

        for code, industry_code in industry_by_code.items():
            if industry_code not in industry_codes:
                continue

            quote = quote_by_code.get(code)
            if quote is None:
                continue

            change = _safe_float(quote.get("Change"))
            trade_value = _safe_float(quote.get("TradeValue"))
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

        directional = advancing + declining
        advance_ratio = (
            round(advancing / directional * 100, 1)
            if directional
            else None
        )
        result[sector_name] = {
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "advance_ratio": advance_ratio,
            "turnover_share_pct": (
                round(turnover / total_turnover * 100, 2)
                if total_turnover > 0
                else None
            ),
        }

    return result


def _sector_breadth_label(
    price_change: float,
    advance_ratio: float | None,
) -> str:
    if advance_ratio is None:
        return "個股資料不足"
    if price_change > 0 and advance_ratio < 45:
        return "少數權值股帶動"
    if price_change < 0 and advance_ratio > 55:
        return "多數個股抗跌"
    if advance_ratio >= 65:
        return "多數個股同步轉強"
    if advance_ratio >= 55:
        return "擴散偏強"
    if advance_ratio >= 45:
        return "漲跌分歧"
    if advance_ratio >= 35:
        return "擴散偏弱"
    return "多數個股同步轉弱"


def _average_last(
    rows: list[dict[str, Any]],
    count: int,
    key: str,
) -> float | None:
    if len(rows) < count:
        return None

    values = [
        float(row[key])
        for row in rows[-count:]
        if row.get(key) is not None
    ]
    if len(values) < count:
        return None

    return sum(values) / len(values)


def _positive_breadth_days(
    rows: list[dict[str, Any]],
    count: int,
) -> int | None:
    if len(rows) < count:
        return None

    return sum(
        int(row["advancing"]) > int(row["declining"])
        for row in rows[-count:]
    )


def _net_advance_ratio(
    rows: list[dict[str, Any]],
    count: int,
) -> float | None:
    if len(rows) < count:
        return None

    selected = rows[-count:]
    advancing = sum(int(row["advancing"]) for row in selected)
    declining = sum(int(row["declining"]) for row in selected)
    directional = advancing + declining
    if not directional:
        return None

    return round((advancing - declining) / directional * 100, 1)


def _market_history_summary(
    history: dict[str, Any],
    benchmark_return_20d: float | None,
) -> dict[str, Any]:
    breadth_rows = sorted(
        history.get("market_breadth_rows") or [],
        key=lambda row: row["date"],
    )
    turnover_rows = sorted(
        history.get("turnover_rows") or [],
        key=lambda row: row["date"],
    )
    average_5d = _average_last(breadth_rows, 5, "advance_ratio")
    average_20d = _average_last(breadth_rows, 20, "advance_ratio")
    latest_ratio = (
        float(breadth_rows[-1]["advance_ratio"])
        if breadth_rows and breadth_rows[-1].get("advance_ratio") is not None
        else None
    )
    turnover_current = (
        float(turnover_rows[-1]["turnover_billion"])
        if turnover_rows
        else None
    )
    turnover_average_5d = _average_last(
        turnover_rows,
        5,
        "turnover_billion",
    )
    turnover_average_20d = _average_last(
        turnover_rows,
        20,
        "turnover_billion",
    )
    turnover_ratio_20d = (
        round(turnover_current / turnover_average_20d, 2)
        if turnover_current is not None and turnover_average_20d not in {None, 0}
        else None
    )

    if average_5d is None:
        breadth_label = "多日廣度資料不足"
    elif average_20d is not None and average_5d >= average_20d + 3 and average_5d >= 50:
        breadth_label = "廣度正在擴張"
    elif average_20d is not None and average_5d <= average_20d - 3 and average_5d < 50:
        breadth_label = "廣度正在收縮"
    elif average_5d >= 55:
        breadth_label = "多數股票偏強"
    elif average_5d <= 45:
        breadth_label = "多數股票偏弱"
    else:
        breadth_label = "廣度中性"

    if turnover_ratio_20d is None or benchmark_return_20d is None:
        volume_label = "量價資料不足"
    elif benchmark_return_20d > 0 and turnover_ratio_20d >= 1.1:
        volume_label = "上漲且量能放大"
    elif benchmark_return_20d > 0 and turnover_ratio_20d < 0.8:
        volume_label = "上漲但量能偏低"
    elif benchmark_return_20d < 0 and turnover_ratio_20d >= 1.1:
        volume_label = "下跌且量能放大"
    elif benchmark_return_20d < 0 and turnover_ratio_20d < 0.8:
        volume_label = "下跌但量能縮小"
    else:
        volume_label = "量能接近 20 日均值"

    return {
        "available": average_5d is not None or turnover_ratio_20d is not None,
        "breadth_complete": len(breadth_rows) >= 20,
        "volume_complete": len(turnover_rows) >= 20,
        "as_of": history.get("as_of"),
        "five_session_start": (
            breadth_rows[-5]["date"] if len(breadth_rows) >= 5 else None
        ),
        "twenty_session_start": (
            breadth_rows[-20]["date"] if len(breadth_rows) >= 20 else None
        ),
        "latest_advance_ratio": round(latest_ratio, 1) if latest_ratio is not None else None,
        "average_advance_ratio_5d": round(average_5d, 1) if average_5d is not None else None,
        "average_advance_ratio_20d": round(average_20d, 1) if average_20d is not None else None,
        "positive_breadth_days_5d": _positive_breadth_days(breadth_rows, 5),
        "positive_breadth_days_20d": _positive_breadth_days(breadth_rows, 20),
        "net_advance_ratio_5d": _net_advance_ratio(breadth_rows, 5),
        "net_advance_ratio_20d": _net_advance_ratio(breadth_rows, 20),
        "breadth_label": breadth_label,
        "turnover_current_billion": round(turnover_current, 1) if turnover_current is not None else None,
        "turnover_average_5d_billion": round(turnover_average_5d, 1) if turnover_average_5d is not None else None,
        "turnover_average_20d_billion": round(turnover_average_20d, 1) if turnover_average_20d is not None else None,
        "turnover_ratio_20d": turnover_ratio_20d,
        "volume_label": volume_label,
        "method": (
            "多日廣度以證交所上市股票每日上漲家數除以上漲加下跌家數；"
            "量能以集中市場全部有價證券成交金額比較最近 20 個交易日平均。"
        ),
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
    sector_breadth: dict[str, dict[str, Any]] | None = None,
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
        participation = (sector_breadth or {}).get(sector_name, {})
        advance_ratio = participation.get("advance_ratio")
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
                "advancing": participation.get("advancing"),
                "declining": participation.get("declining"),
                "unchanged": participation.get("unchanged"),
                "advance_ratio": advance_ratio,
                "turnover_share_pct": participation.get("turnover_share_pct"),
                "breadth_label": _sector_breadth_label(
                    change_percent,
                    advance_ratio,
                ),
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
    company_profiles: list[dict[str, Any]] | None = None,
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
    tpex_breadth = _tpex_breadth(tpex_quotes)

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
    participation = _sector_breadth(
        twse_quotes,
        company_profiles or [],
    )
    sectors = _sector_rows(
        twse_indices,
        five_session_rows=history.get("five_session_rows"),
        twenty_session_rows=history.get("twenty_session_rows"),
        sector_breadth=participation,
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
    benchmark_20d = _index_entry(
        history.get("twenty_session_rows") or [],
        "發行量加權股價指數",
    )
    benchmark_return_20d = _return_percent(
        twse_index.get("close") if twse_index else None,
        benchmark_20d.get("close") if benchmark_20d else None,
    )
    market_trend = _market_history_summary(
        history,
        benchmark_return_20d,
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
        "market_trend": market_trend,
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
            "20 日價格表現、相對大盤超額報酬與產業內上市個股漲跌擴散。"
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

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            twse_indices_future = executor.submit(_request_rows, TWSE_INDEX_URL)
            twse_quotes_future = executor.submit(_request_rows, TWSE_QUOTES_URL)
            tpex_market_future = executor.submit(_request_rows, TPEX_MARKET_URL)
            company_profile_future = executor.submit(
                _request_optional_rows,
                TWSE_COMPANY_PROFILE_URL,
            )
            calendar_future = executor.submit(
                _load_calendar_payloads,
                date.today(),
            )

            twse_indices = twse_indices_future.result()
            twse_index = _index_entry(
                twse_indices,
                "發行量加權股價指數",
            )
            try:
                calendar_payloads = calendar_future.result()
            except (requests.RequestException, RuntimeError, ValueError):
                calendar_payloads = None

            history_future = (
                executor.submit(
                    _load_sector_trend_history,
                    twse_index["date"],
                    calendar_payloads,
                )
                if twse_index and calendar_payloads
                else None
            )
            twse_quotes = twse_quotes_future.result()
            tpex_market = tpex_market_future.result()
            company_profiles = company_profile_future.result()
            try:
                sector_history = history_future.result() if history_future else None
            except (requests.RequestException, RuntimeError, ValueError):
                sector_history = None
    except (requests.RequestException, RuntimeError, ValueError) as error:
        with _cache_lock:
            if _market_cache:
                return _market_cache[1]

        raise RuntimeError("官方市場資料暫時無法取得，請稍後再試。") from error

    result = build_market_overview(
        twse_indices,
        twse_quotes,
        tpex_market,
        tpex_market,
        sector_history=sector_history,
        company_profiles=company_profiles,
    )

    with _cache_lock:
        _market_cache = (now, result)

    return result
