from __future__ import annotations

import html
import math
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from app.services.stock_code import base_stock_code


TWSE_VALUATION_URL = (
    "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
)
TPEX_VALUATION_URL = (
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
)
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"

DEFAULT_TIMEOUT = 7
VALUATION_CACHE_SECONDS = 60 * 60 * 4
NEWS_CACHE_SECONDS = 60 * 20

_cache_lock = threading.Lock()
_valuation_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_news_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_positive_terms = {
    "成長",
    "創高",
    "獲利",
    "轉盈",
    "增資",
    "擴產",
    "接單",
    "上修",
    "優於預期",
    "營收增",
    "配息",
    "突破",
    "合作",
}
_negative_terms = {
    "衰退",
    "虧損",
    "轉虧",
    "下修",
    "不如預期",
    "營收減",
    "裁員",
    "停工",
    "違約",
    "處分",
    "下跌",
    "重挫",
    "警示",
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


def _first_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and str(item[key]).strip():
            return item[key]

    return None


def _request_json(url: str) -> list[dict[str, Any]]:
    response = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "AI-Stock-Platform/2.0 (+public market research)",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, list):
        raise RuntimeError("估值資料格式不正確。")

    return [item for item in payload if isinstance(item, dict)]


def _cached_valuation_rows(market: str) -> list[dict[str, Any]]:
    now = time.monotonic()

    with _cache_lock:
        cached = _valuation_cache.get(market)
        if cached and now - cached[0] < VALUATION_CACHE_SECONDS:
            return cached[1]

    url = TPEX_VALUATION_URL if market == "上櫃" else TWSE_VALUATION_URL
    rows = _request_json(url)

    with _cache_lock:
        _valuation_cache[market] = (now, rows)

    return rows


def _valuation_score(
    pe_ratio: float | None,
    pb_ratio: float | None,
    dividend_yield: float | None,
) -> float:
    """建立透明的估值快照分數，不把它包裝成財報預測。"""

    score = 50.0

    if pe_ratio is not None and pe_ratio > 0:
        if pe_ratio <= 15:
            score += 18
        elif pe_ratio <= 25:
            score += 9
        elif pe_ratio >= 50:
            score -= 15
        elif pe_ratio >= 35:
            score -= 8

    if pb_ratio is not None and pb_ratio > 0:
        if pb_ratio <= 1.5:
            score += 14
        elif pb_ratio <= 3:
            score += 6
        elif pb_ratio >= 8:
            score -= 12
        elif pb_ratio >= 5:
            score -= 6

    if dividend_yield is not None and dividend_yield >= 0:
        if dividend_yield >= 5:
            score += 16
        elif dividend_yield >= 3:
            score += 10
        elif dividend_yield >= 1.5:
            score += 4

    return round(max(0.0, min(100.0, score)), 1)


def _score_label(score: float) -> str:
    if score >= 70:
        return "估值條件偏佳"
    if score >= 55:
        return "估值條件中性偏佳"
    if score >= 45:
        return "估值條件中性"

    return "估值壓力偏高"


def get_fundamental_snapshot(stock_code: str, market: str) -> dict[str, Any]:
    code = base_stock_code(stock_code)

    if code.startswith("00"):
        return {
            "available": False,
            "score": None,
            "label": "ETF 不適用個股估值",
            "summary": "ETF 應改看成分股、追蹤誤差、費用率與折溢價，不能直接套用個股本益比。",
            "pe_ratio": None,
            "pb_ratio": None,
            "dividend_yield": None,
            "as_of": None,
            "source": "臺灣證券交易所／櫃買中心",
        }

    preferred_market = "上櫃" if market == "上櫃" or stock_code.upper().endswith(".TWO") else "上市"
    market_order = [preferred_market, "上市" if preferred_market == "上櫃" else "上櫃"]

    for candidate_market in market_order:
        try:
            rows = _cached_valuation_rows(candidate_market)
        except (requests.RequestException, RuntimeError, ValueError):
            continue

        for item in rows:
            item_code = str(
                _first_value(
                    item,
                    "Code",
                    "SecuritiesCompanyCode",
                    "證券代號",
                    "股票代號",
                )
                or ""
            ).strip()

            if item_code != code:
                continue

            pe_ratio = _safe_float(
                _first_value(item, "PEratio", "PriceEarningRatio", "本益比")
            )
            pb_ratio = _safe_float(
                _first_value(item, "PBratio", "PriceBookRatio", "股價淨值比")
            )
            dividend_yield = _safe_float(
                _first_value(item, "DividendYield", "殖利率(%)", "殖利率")
            )
            available = any(
                value is not None
                for value in (pe_ratio, pb_ratio, dividend_yield)
            )
            score = (
                _valuation_score(pe_ratio, pb_ratio, dividend_yield)
                if available
                else None
            )

            return {
                "available": available,
                "score": score,
                "label": _score_label(score) if score is not None else "估值資料不足",
                "summary": (
                    "以交易所公布的本益比、股價淨值比與殖利率建立估值快照；"
                    "分數只代表相對估值條件，不等於公司品質或未來獲利。"
                ),
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "dividend_yield": dividend_yield,
                "as_of": str(_first_value(item, "Date", "DateOfData", "日期") or ""),
                "source": f"{'櫃買中心' if candidate_market == '上櫃' else '臺灣證券交易所'}每日估值資料",
            }

    return {
        "available": False,
        "score": None,
        "label": "尚無估值資料",
        "summary": "交易所目前未提供這檔股票可用的本益比、股價淨值比或殖利率。",
        "pe_ratio": None,
        "pb_ratio": None,
        "dividend_yield": None,
        "as_of": None,
        "source": "臺灣證券交易所／櫃買中心",
    }


def score_news_titles(titles: list[str]) -> tuple[float, int, int]:
    positive_hits = 0
    negative_hits = 0

    for title in titles:
        positive_hits += sum(term in title for term in _positive_terms)
        negative_hits += sum(term in title for term in _negative_terms)

    raw_score = 50 + (positive_hits - negative_hits) * 7
    score = round(max(20.0, min(80.0, float(raw_score))), 1)
    return score, positive_hits, negative_hits


def _clean_news_title(value: str) -> str:
    cleaned = html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
    return re.sub(r"\s+", " ", cleaned)


def _news_label(score: float) -> str:
    if score >= 62:
        return "近期消息偏正向"
    if score <= 38:
        return "近期消息偏負向"

    return "近期消息中性"


def get_news_snapshot(stock_code: str, stock_name: str = "") -> dict[str, Any]:
    code = base_stock_code(stock_code)
    query = f"{code} {stock_name} 台股".strip()
    cache_key = query.lower()
    now = time.monotonic()

    with _cache_lock:
        cached = _news_cache.get(cache_key)
        if cached and now - cached[0] < NEWS_CACHE_SECONDS:
            return cached[1]

    params = {
        "q": query,
        "hl": "zh-TW",
        "gl": "TW",
        "ceid": "TW:zh-Hant",
    }

    try:
        response = requests.get(
            GOOGLE_NEWS_RSS_URL,
            params=params,
            headers={"User-Agent": "AI-Stock-Platform/2.0"},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError):
        return {
            "available": False,
            "score": None,
            "label": "新聞服務暫時無法使用",
            "summary": "本次未能取得近期新聞，總分不會因缺少消息面而被扣分。",
            "positive_hits": 0,
            "negative_hits": 0,
            "articles": [],
            "source": "Google 新聞 RSS",
        }

    articles: list[dict[str, str]] = []

    for item in root.findall("./channel/item")[:8]:
        title = _clean_news_title(item.findtext("title", default=""))
        link = item.findtext("link", default="").strip()
        published = item.findtext("pubDate", default="").strip()
        source_node = item.find("source")
        source = source_node.text.strip() if source_node is not None and source_node.text else "新聞來源"

        if not title or not link:
            continue

        try:
            published_at = parsedate_to_datetime(published).isoformat()
        except (TypeError, ValueError, OverflowError):
            published_at = published

        articles.append(
            {
                "title": title,
                "url": link,
                "source": source,
                "published_at": published_at,
            }
        )

    if articles:
        score, positive_hits, negative_hits = score_news_titles(
            [article["title"] for article in articles]
        )
        result = {
            "available": True,
            "score": score,
            "label": _news_label(score),
            "summary": (
                f"分析最近 {len(articles)} 則標題，辨識到 {positive_hits} 個正向與 "
                f"{negative_hits} 個負向詞。這是快速消息溫度，不代表新聞真偽或事件影響。"
            ),
            "positive_hits": positive_hits,
            "negative_hits": negative_hits,
            "articles": articles,
            "source": "Google 新聞 RSS（保留原新聞來源連結）",
        }
    else:
        result = {
            "available": False,
            "score": None,
            "label": "近期新聞不足",
            "summary": "近期沒有找到足夠新聞，總分只使用其他可用面向。",
            "positive_hits": 0,
            "negative_hits": 0,
            "articles": [],
            "source": "Google 新聞 RSS",
        }

    with _cache_lock:
        _news_cache[cache_key] = (now, result)

    return result


def build_perspectives(
    technical_score: float,
    stock_code: str,
    market: str,
    stock_name: str = "",
) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        fundamental_future = executor.submit(
            get_fundamental_snapshot,
            stock_code,
            market,
        )
        news_future = executor.submit(
            get_news_snapshot,
            stock_code,
            stock_name,
        )

        try:
            fundamental = fundamental_future.result()
        except Exception:
            fundamental = {
                "available": False,
                "score": None,
                "label": "基本面資料暫時無法使用",
                "summary": "本次未能取得交易所估值資料，總分不會因此被扣分。",
                "pe_ratio": None,
                "pb_ratio": None,
                "dividend_yield": None,
                "as_of": None,
                "source": "臺灣證券交易所／櫃買中心",
            }

        try:
            news = news_future.result()
        except Exception:
            news = {
                "available": False,
                "score": None,
                "label": "新聞服務暫時無法使用",
                "summary": "本次未能取得近期新聞，總分不會因缺少消息面而被扣分。",
                "positive_hits": 0,
                "negative_hits": 0,
                "articles": [],
                "source": "Google 新聞 RSS",
            }
    axes = [float(technical_score)]

    for snapshot in (fundamental, news):
        score = _safe_float(snapshot.get("score"))
        if snapshot.get("available") and score is not None:
            axes.append(score)

    composite_score = round(sum(axes) / len(axes), 1)

    return {
        "technical": {
            "available": True,
            "score": round(float(technical_score), 1),
            "label": "Score Engine V2",
            "summary": "依趨勢、位置、觸發、風險與量價環境計算。",
        },
        "fundamental": fundamental,
        "news": news,
        "composite": {
            "score": composite_score,
            "available_axes": len(axes),
            "method": "可用面向等權平均；缺少的面向不計入，也不以 0 分懲罰。",
        },
    }
