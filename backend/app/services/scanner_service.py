from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any

import requests


TWSE_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
SCANNER_UNIVERSE = (
    "0050", "0056", "00878", "00919", "2330", "2317", "2454", "2308",
    "2382", "2303", "2345", "2379", "2881", "2882", "2891", "2603",
    "2615", "3037", "3231", "3711",
)
_REQUEST_TIMEOUTS = (4, 7, 10)
_CACHE_TTL_SECONDS = 120
_cache: dict[str, Any] = {"at": 0.0, "payload": None}


def _safe_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "--", "---", "nan", "None"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _scanner_score(change_percent: float, open_price: float | None, high_price: float | None,
                   low_price: float | None, current_price: float,
                   total_volume: float | None) -> tuple[float, list[str]]:
    reasons: list[str] = []
    momentum = max(0.0, min(35.0, (change_percent + 3.0) / 8.0 * 35.0))
    if high_price is not None and low_price is not None and high_price > low_price:
        strength = max(0.0, min(25.0, (current_price - low_price) / (high_price - low_price) * 25.0))
    else:
        strength = 12.5
    liquidity = max(0.0, min(20.0, (math.log10(total_volume) - 3.0) / 5.0 * 20.0)) if total_volume and total_volume > 0 else 0.0
    stability = 20.0
    if open_price is not None and open_price > 0:
        stability = max(5.0, min(20.0, 12.0 + (current_price - open_price) / open_price * 100 * 2.0))
    reasons.append("當日動能明顯偏強" if change_percent >= 2 else "當日價格維持正報酬" if change_percent >= 0 else "當日仍為負報酬，需等待轉強")
    if strength >= 18:
        reasons.append("現價接近當日高檔")
    if liquidity >= 14:
        reasons.append("成交量具備較佳流動性")
    return round(max(0.0, min(100.0, momentum + strength + liquidity + stability)), 1), reasons


def _fetch_messages() -> list[dict[str, Any]]:
    now = time.monotonic()
    cached = _cache.get("payload")
    if isinstance(cached, list) and now - float(_cache.get("at") or 0) < _CACHE_TTL_SECONDS:
        return cached

    channels = "|".join(f"tse_{code}.tw" for code in SCANNER_UNIVERSE)
    last_error: Exception | None = None
    for attempt, timeout in enumerate(_REQUEST_TIMEOUTS):
        try:
            response = requests.get(
                TWSE_MIS_URL,
                params={"ex_ch": channels, "json": "1", "delay": "0"},
                headers={"Accept": "application/json,text/javascript,*/*;q=0.01", "Referer": "https://mis.twse.com.tw/", "User-Agent": "Mozilla/5.0 AI-Stock-Platform/2.1"},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            messages = payload.get("msgArray") if isinstance(payload, dict) else None
            if not isinstance(messages, list):
                raise RuntimeError("每日選股行情格式不正確。")
            _cache.update(at=time.monotonic(), payload=messages)
            return messages
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < len(_REQUEST_TIMEOUTS) - 1:
                time.sleep(0.25 * (2 ** attempt))

    # A stale in-process cache is safer than turning the entire scanner endpoint into a 5xx.
    if isinstance(cached, list):
        return cached
    raise RuntimeError("每日選股行情來源暫時無法連線，請稍後再試。") from last_error


def get_daily_scanner() -> dict[str, Any]:
    messages = _fetch_messages()
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
        change = current_price - previous_close if previous_close and previous_close > 0 else 0.0
        change_percent = change / previous_close * 100 if previous_close and previous_close > 0 else 0.0
        score, reasons = _scanner_score(change_percent, _safe_float(quote.get("o")), _safe_float(quote.get("h")), _safe_float(quote.get("l")), current_price, _safe_float(quote.get("v")))
        candidates.append({"code": code, "name": name, "market": "上市", "price": round(current_price, 4), "change": round(change, 4), "change_percent": round(change_percent, 4), "volume": int(_safe_float(quote.get("v")) or 0), "screening_score": score, "reasons": reasons, "full_analysis_required": True})

    candidates.sort(key=lambda item: (item["screening_score"], item["volume"]), reverse=True)
    date_value = str(messages[0].get("d") or "") if messages else ""
    time_value = str(messages[0].get("t") or "") if messages else ""
    return {
        "updated_at": " ".join(part for part in (date_value, time_value) if part) or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_scope": "20 檔高流動性上市股票與 ETF",
        "universe_size": len(SCANNER_UNIVERSE),
        "candidate_count": len(candidates[:10]),
        "method": "先依當日漲跌、收盤區間位置、成交量與開盤後強弱縮小候選名單；盤中快篩分不等於 AI 評分，也不參與最終排名。",
        "candidates": candidates[:10],
    }
