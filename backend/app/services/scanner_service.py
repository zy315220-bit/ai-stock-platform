from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import requests


TWSE_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
SCANNER_UNIVERSE = (
    "0050",
    "0056",
    "00878",
    "00919",
    "2330",
    "2317",
    "2454",
    "2308",
    "2382",
    "2303",
    "2345",
    "2379",
    "2881",
    "2882",
    "2891",
    "2603",
    "2615",
    "3037",
    "3231",
    "3711",
)


def _safe_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "--", "---", "nan", "None"}:
        return None

    try:
        number = float(text)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def _scanner_score(
    change_percent: float,
    open_price: float | None,
    high_price: float | None,
    low_price: float | None,
    current_price: float,
    total_volume: float | None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []

    momentum = max(0.0, min(35.0, (change_percent + 3.0) / 8.0 * 35.0))

    if high_price is not None and low_price is not None and high_price > low_price:
        intraday_position = (current_price - low_price) / (high_price - low_price)
        strength = max(0.0, min(25.0, intraday_position * 25.0))
    else:
        strength = 12.5

    if total_volume is not None and total_volume > 0:
        liquidity = max(0.0, min(20.0, (math.log10(total_volume) - 3.0) / 5.0 * 20.0))
    else:
        liquidity = 0.0

    stability = 20.0
    if open_price is not None and open_price > 0:
        open_change = (current_price - open_price) / open_price * 100
        stability = max(5.0, min(20.0, 12.0 + open_change * 2.0))

    if change_percent >= 2:
        reasons.append("當日動能明顯偏強")
    elif change_percent >= 0:
        reasons.append("當日價格維持正報酬")
    else:
        reasons.append("當日仍為負報酬，需等待轉強")

    if strength >= 18:
        reasons.append("現價接近當日高檔")

    if liquidity >= 14:
        reasons.append("成交量具備較佳流動性")

    score = momentum + strength + liquidity + stability
    return round(max(0.0, min(100.0, score)), 1), reasons


def get_daily_scanner() -> dict[str, Any]:
    channels = "|".join(f"tse_{code}.tw" for code in SCANNER_UNIVERSE)
    response = requests.get(
        TWSE_MIS_URL,
        params={"ex_ch": channels, "json": "1", "delay": "0"},
        headers={
            "Accept": "application/json,text/javascript,*/*;q=0.01",
            "Referer": "https://mis.twse.com.tw/",
            "User-Agent": "Mozilla/5.0 AI-Stock-Platform/2.0",
        },
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    messages = payload.get("msgArray") if isinstance(payload, dict) else None

    if not isinstance(messages, list):
        raise RuntimeError("每日選股行情格式不正確。")

    candidates: list[dict[str, Any]] = []

    for quote in messages:
        if not isinstance(quote, dict):
            continue

        code = str(quote.get("c") or "").strip()
        name = str(quote.get("n") or "").strip()
        current_price = _safe_float(quote.get("z")) or _safe_float(quote.get("y"))
        previous_close = _safe_float(quote.get("y"))

        if not code or current_price is None or current_price <= 0:
            continue

        change = (
            current_price - previous_close
            if previous_close is not None and previous_close > 0
            else 0.0
        )
        change_percent = (
            change / previous_close * 100
            if previous_close is not None and previous_close > 0
            else 0.0
        )
        score, reasons = _scanner_score(
            change_percent=change_percent,
            open_price=_safe_float(quote.get("o")),
            high_price=_safe_float(quote.get("h")),
            low_price=_safe_float(quote.get("l")),
            current_price=current_price,
            total_volume=_safe_float(quote.get("v")),
        )

        candidates.append(
            {
                "code": code,
                "name": name,
                "market": "上市",
                "price": round(current_price, 4),
                "change": round(change, 4),
                "change_percent": round(change_percent, 4),
                "volume": int(_safe_float(quote.get("v")) or 0),
                "screening_score": score,
                "reasons": reasons,
                "full_analysis_required": True,
            }
        )

    candidates.sort(
        key=lambda item: (item["screening_score"], item["volume"]),
        reverse=True,
    )

    date_value = ""
    time_value = ""
    if messages:
        date_value = str(messages[0].get("d") or "")
        time_value = str(messages[0].get("t") or "")

    return {
        "updated_at": " ".join(part for part in (date_value, time_value) if part)
        or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_scope": "20 檔高流動性上市股票與 ETF",
        "universe_size": len(SCANNER_UNIVERSE),
        "candidate_count": len(candidates[:10]),
        "method": (
            "先依當日漲跌、收盤區間位置、成交量與開盤後強弱縮小候選名單；"
            "盤中快篩分不等於 AI 評分，也不參與最終排名。"
        ),
        "candidates": candidates[:10],
    }
