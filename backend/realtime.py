from __future__ import annotations

"""
台灣股票即時行情模組。

資料來源：
    臺灣證券交易所 MIS 即時資訊。

支援市場：
    tse：上市
    otc：上櫃

注意：
    盤前、盤後或股票尚未成交時，
    API 的最新成交價 z 可能為 "-"。
    此時程式會暫時使用昨收價，但會透過
    is_realtime_trade 與 price_source 清楚標示。
"""

import math
from typing import Any

import requests


TWSE_MIS_URL = (
    "https://mis.twse.com.tw/"
    "stock/api/getStockInfo.jsp"
)

DEFAULT_TIMEOUT = 6


def _to_float(value: Any) -> float | None:
    """
    將 API 資料安全轉換成 float。

    無效、非有限數值會回傳 None。
    """

    if value is None:
        return None

    text = (
        str(value)
        .strip()
        .replace(",", "")
    )

    if text.lower() in {
        "",
        "-",
        "--",
        "---",
        "null",
        "none",
        "nan",
    }:
        return None

    try:
        number = float(text)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _to_int(value: Any) -> int | None:
    """
    將 API 資料安全轉換成整數。
    """

    number = _to_float(value)

    if number is None:
        return None

    try:
        return int(number)
    except (TypeError, ValueError, OverflowError):
        return None


def _first_quote_price(
    value: Any,
) -> float | None:
    """
    取得五檔報價中的第一個有效價格。

    TWSE MIS 的買賣價通常使用底線分隔，例如：
        100.00_99.90_99.80_99.70_99.60_
    """

    if value is None:
        return None

    for part in str(value).split("_"):
        price = _to_float(part)

        if price is not None and price > 0:
            return price

    return None


def normalize_stock_code(
    stock_code: Any,
) -> str:
    """
    統一股票代號格式。

    範例：
        2330       -> 2330
        2330.TW    -> 2330
        6488.TWO   -> 6488
        2330.tw    -> 2330
    """

    if stock_code is None:
        raise ValueError(
            "股票代號不能是 None。"
        )

    code = (
        str(stock_code)
        .strip()
        .upper()
    )

    if code.endswith(".TWO"):
        code = code[:-4]

    elif code.endswith(".TW"):
        code = code[:-3]

    code = code.strip()

    if not code:
        raise ValueError(
            "股票代號不能空白。"
        )

    return code


def _build_channels(
    stock_code: Any,
) -> list[dict[str, str]]:
    """
    依股票代號建立 TWSE MIS 查詢市場。

    - 指定 .TW：只查上市
    - 指定 .TWO：只查上櫃
    - 未指定市場：先查上市，再查上櫃
    """

    original = (
        str(stock_code)
        .strip()
        .upper()
    )

    code = normalize_stock_code(
        stock_code
    )

    if original.endswith(".TW"):
        return [
            {
                "channel": f"tse_{code}.tw",
                "market": "上市",
            }
        ]

    if original.endswith(".TWO"):
        return [
            {
                "channel": f"otc_{code}.tw",
                "market": "上櫃",
            }
        ]

    return [
        {
            "channel": f"tse_{code}.tw",
            "market": "上市",
        },
        {
            "channel": f"otc_{code}.tw",
            "market": "上櫃",
        },
    ]


def _create_session() -> requests.Session:
    """
    建立共用 HTTP 連線。
    """

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/150.0.0.0 "
                "Safari/537.36"
            ),
            "Referer": (
                "https://mis.twse.com.tw/"
            ),
            "Accept": (
                "application/json,"
                "text/javascript,"
                "*/*;q=0.01"
            ),
        }
    )

    return session


def _request_quote(
    session: requests.Session,
    channel: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any] | None:
    """
    向 TWSE MIS 取得單一市場的行情。

    成功時回傳 quote 字典；
    找不到股票或回傳格式不符時回傳 None。
    """

    params = {
        "ex_ch": channel,
        "json": "1",
        "delay": "0",
    }

    try:
        response = session.get(
            TWSE_MIS_URL,
            params=params,
            timeout=timeout,
        )

        response.raise_for_status()

    except (
        requests.Timeout,
        requests.RequestException,
    ):
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if not isinstance(data, dict):
        return None

    messages = data.get(
        "msgArray"
    )

    if (
        not isinstance(messages, list)
        or not messages
    ):
        return None

    quote = messages[0]

    if not isinstance(quote, dict):
        return None

    return quote


def _parse_quote(
    quote: dict[str, Any],
    stock_code: str,
    market: str,
) -> dict[str, Any] | None:
    """
    將 TWSE MIS 原始資料轉成系統統一格式。
    """

    code = str(
        quote.get("c", stock_code)
    ).strip()

    # 避免 MIS 回傳內容與請求代號不一致。
    if code and code != stock_code:
        return None

    name = str(
        quote.get("n", "")
    ).strip()

    trade_price = _to_float(
        quote.get("z")
    )

    previous_close = _to_float(
        quote.get("y")
    )

    open_price = _to_float(
        quote.get("o")
    )

    high_price = _to_float(
        quote.get("h")
    )

    low_price = _to_float(
        quote.get("l")
    )

    best_bid = _first_quote_price(
        quote.get("b")
    )

    best_ask = _first_quote_price(
        quote.get("a")
    )

    # tv：單筆成交量
    # v：累積成交量
    trade_volume = _to_int(
        quote.get("tv")
    )

    total_volume = _to_int(
        quote.get("v")
    )

    if (
        trade_price is not None
        and trade_price > 0
    ):
        analysis_price = trade_price
        is_realtime_trade = True
        price_source = "最新成交價"

    elif (
        previous_close is not None
        and previous_close > 0
    ):
        analysis_price = previous_close
        is_realtime_trade = False
        price_source = "昨收價"

    else:
        return None

    change: float | None = None
    change_percent: float | None = None

    if (
        previous_close is not None
        and previous_close > 0
    ):
        change = (
            analysis_price
            - previous_close
        )

        change_percent = (
            change
            / previous_close
            * 100
        )

    quote_date = str(
        quote.get("d", "")
    ).strip()

    quote_time = str(
        quote.get("t", "")
    ).strip()

    return {
        "code": code or stock_code,
        "name": name,
        "market": market,
        "price": analysis_price,
        "trade_price": trade_price,
        "previous_close": previous_close,
        "change": change,
        "change_percent": change_percent,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "trade_volume": trade_volume,
        "total_volume": total_volume,
        "date": quote_date,
        "time": quote_time,
        "is_realtime_trade": (
            is_realtime_trade
        ),
        "price_source": price_source,
        "source": "TWSE MIS",
    }


def get_realtime_price(
    stock_code: Any,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """
    取得台灣上市或上櫃股票即時行情。

    Parameters
    ----------
    stock_code:
        股票代號，例如 2330、2330.TW、6488.TWO。

    timeout:
        每次 HTTP 請求的逾秒時間。

    Returns
    -------
    dict
        統一格式的行情資料。

    Raises
    ------
    ValueError
        股票代號空白、timeout 無效，
        或上市、上櫃市場皆查無資料。
    """

    normalized_code = (
        normalize_stock_code(
            stock_code
        )
    )

    if timeout <= 0:
        raise ValueError(
            "timeout 必須大於 0。"
        )

    channels = _build_channels(
        stock_code
    )

    session = _create_session()

    try:
        for item in channels:
            quote = _request_quote(
                session=session,
                channel=item["channel"],
                timeout=timeout,
            )

            if quote is None:
                continue

            result = _parse_quote(
                quote=quote,
                stock_code=(
                    normalized_code
                ),
                market=item["market"],
            )

            if result is not None:
                return result

    finally:
        session.close()

    raise ValueError(
        f"無法取得 {normalized_code} 的最新行情，"
        "可能原因包括：股票代號錯誤、"
        "市場暫停服務或網路連線異常。"
    )
