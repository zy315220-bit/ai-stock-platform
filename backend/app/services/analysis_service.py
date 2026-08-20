"""股票分析服務：串接真實行情、技術指標與 Score Engine V2。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import math
import random
from typing import Any, Callable, Optional

import pandas as pd

from app.core.config import settings
from app.services.history_policy import INTERACTIVE_HISTORY_MONTHS
from app.services.market_context import build_perspectives
from app.services.research_history import frame_coverage
from app.services.stock_code import base_stock_code


CHART_ROWS = 260
MINIMUM_DAILY_ROWS = 65
MINIMUM_HOURLY_ROWS = 30
POSITION_STATUSES = {"not_holding", "holding"}


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    return number if math.isfinite(number) else default


def _safe_int(value: Any, default: int = 0) -> int:
    number = _safe_float(value)
    return int(number) if number is not None else default


def _normalize_code(stock_code: str) -> str:
    return base_stock_code(stock_code)


def _score_level(score: Any) -> str:
    value = _safe_float(score, 0.0) or 0.0

    if value >= 85:
        return "高分"
    if value >= 70:
        return "偏強"
    if value >= 55:
        return "中性"
    if value >= 40:
        return "偏弱"

    return "弱勢"


def _normalize_position_status(value: str) -> str:
    normalized = str(value or "not_holding").strip().lower()

    if normalized not in POSITION_STATUSES:
        raise ValueError("持股狀態只接受 not_holding 或 holding。")

    return normalized


def _indicator_snapshot(latest: pd.Series) -> dict[str, Optional[float]]:
    return {
        "ema20": _safe_float(latest.get("EMA20")),
        "ema60": _safe_float(latest.get("EMA60")),
        "rsi": _safe_float(latest.get("RSI")),
        "macd": _safe_float(latest.get("MACD")),
        "macd_signal": _safe_float(latest.get("Signal")),
        "macd_histogram": _safe_float(latest.get("MACD_Hist")),
        "k": _safe_float(latest.get("K")),
        "d": _safe_float(latest.get("D")),
        "atr": _safe_float(latest.get("ATR")),
        "atr_percent": _safe_float(latest.get("ATRPercent")),
        "adx": _safe_float(latest.get("ADX")),
        "volume_ratio": _safe_float(latest.get("VolumeRatio")),
    }


def _build_recommendation(
    *,
    result: Any,
    current_price: float,
    position_status: str,
) -> dict[str, Any]:
    score = _safe_float(result.total_score, 0.0) or 0.0
    direction = str(result.direction or "").upper()
    stop_price = _safe_float(result.stop_price)
    trade_eligible = bool(result.trade_eligible)

    if position_status == "holding":
        label = "已持有"

        if stop_price is not None and current_price <= stop_price:
            action = "REVIEW_RISK"
            title = "風險條件已觸發"
            summary = "現價已到達系統風險線，應優先重新檢查原持有理由與可承受損失。"
            tone = "risk"
        elif score >= 70 and direction == "LONG":
            action = "HOLD_WATCH"
            title = "續抱觀察"
            summary = "中期方向與量化分數仍偏正向，持續觀察停損線與趨勢是否改變。"
            tone = "positive"
        elif score >= 55:
            action = "HOLD_CAUTION"
            title = "續抱但提高警戒"
            summary = "訊號未明顯轉壞，但強度不足；避免因短線波動擴大原定風險。"
            tone = "neutral"
        else:
            action = "REVIEW_POSITION"
            title = "重新檢查持股"
            summary = "量化分數偏弱，請對照停損線、持有期限與原本買進理由重新評估。"
            tone = "risk"
    else:
        label = "尚未持有"

        if trade_eligible and score >= 75 and direction == "LONG":
            action = "WATCH_ENTRY"
            title = "進入候選觀察"
            summary = "條件接近系統門檻，但仍應等待觸發價確認並控制單筆風險。"
            tone = "positive"
        elif score >= 60 and direction == "LONG":
            action = "WAIT_CONFIRMATION"
            title = "等待訊號確認"
            summary = "方向偏多但條件尚未完整，不宜只因上漲或單一指標追價。"
            tone = "neutral"
        else:
            action = "NO_ENTRY"
            title = "目前不列入進場"
            summary = "分數或風險條件尚未通過，先等待更完整的趨勢與觸發訊號。"
            tone = "risk"

    return {
        "position_status": position_status,
        "position_label": label,
        "action": action,
        "title": title,
        "summary": summary,
        "tone": tone,
        "disclaimer": "此結果是量化決策支援，不保證獲利，也不是自動下單指令。",
    }


def _format_time(value: Any, include_clock: bool = False) -> str:
    timestamp = pd.Timestamp(value)

    if pd.isna(timestamp):
        return ""

    return timestamp.strftime(
        "%Y-%m-%d %H:%M:%S" if include_clock else "%Y-%m-%d"
    )


def _validate_daily_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("找不到股票日線資料。")

    if len(df) < MINIMUM_DAILY_ROWS:
        raise ValueError(
            f"日線資料只有 {len(df)} 筆，至少需要 {MINIMUM_DAILY_ROWS} 筆。"
        )

    required = ["Open", "High", "Low", "Close", "Volume", "ATR"]
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError("日線資料缺少必要欄位：" + ", ".join(missing))

    ema20 = "EMA20" if "EMA20" in df.columns else "MA20" if "MA20" in df.columns else None
    ema60 = "EMA60" if "EMA60" in df.columns else "MA60" if "MA60" in df.columns else None

    if ema20 is None:
        raise ValueError("日線資料缺少 EMA20 或 MA20。")
    if ema60 is None:
        raise ValueError("日線資料缺少 EMA60 或 MA60。")

    cleaned = df.copy()

    for column in required:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    cleaned = cleaned.dropna(
        subset=["Open", "High", "Low", "Close", "ATR", ema20, ema60]
    ).copy()

    if cleaned.empty:
        raise ValueError("日線資料清理後沒有可用資料。")

    return cleaned.sort_index()


def _download_interactive_daily_history(
    download_stock: Callable[..., pd.DataFrame],
    stock_code: str,
) -> pd.DataFrame:
    """Return enough daily history for indicators, recovering partial responses.

    The exchange month endpoints can occasionally return only a few successful
    months while still producing a non-empty frame.  A non-empty frame is not
    necessarily complete enough for EMA60, so retry the official source once
    and then try the long-history source before allowing validation to fail.
    """

    attempts = (
        {
            "prefer_official": True,
            "update_with_intraday": False,
            "official_months": INTERACTIVE_HISTORY_MONTHS,
        },
        {
            "prefer_official": True,
            "update_with_intraday": False,
            "official_months": INTERACTIVE_HISTORY_MONTHS,
            "force_official_refresh": True,
        },
        {
            "prefer_official": False,
            "update_with_intraday": False,
            "daily_period": "1y",
            "official_months": INTERACTIVE_HISTORY_MONTHS,
        },
    )
    best_frame = pd.DataFrame()
    errors: list[str] = []
    initial_rows = 0
    method_names = (
        "official",
        "official_refresh",
        "long_history_fallback",
    )

    for attempt_index, options in enumerate(attempts):
        try:
            candidate = download_stock(stock_code, **options)
        except Exception as error:
            errors.append(str(error))
            continue

        if attempt_index == 0:
            initial_rows = len(candidate) if candidate is not None else 0

        if candidate is not None and len(candidate) > len(best_frame):
            best_frame = candidate

        if candidate is not None and len(candidate) >= MINIMUM_DAILY_ROWS:
            candidate.attrs["history_recovery"] = {
                "recovered": attempt_index > 0,
                "attempts": attempt_index + 1,
                "initial_rows": initial_rows,
                "final_rows": len(candidate),
                "method": method_names[attempt_index],
            }
            return candidate

    if not best_frame.empty:
        best_frame.attrs["history_recovery"] = {
            "recovered": len(attempts) > 1,
            "attempts": len(attempts),
            "initial_rows": initial_rows,
            "final_rows": len(best_frame),
            "method": "best_available",
        }
        return best_frame

    detail = "；".join(message for message in errors if message)
    raise ValueError(detail or "找不到股票日線資料。")


def _prepare_hourly_dataframe(
    download_hourly_stock: Optional[Callable],
    add_indicators: Callable,
    stock_code: str,
) -> Optional[pd.DataFrame]:
    if download_hourly_stock is None:
        return None

    try:
        hourly_df = download_hourly_stock(stock_code=stock_code, period="60d")

        if hourly_df is None or hourly_df.empty:
            return None

        hourly_df = add_indicators(hourly_df)

        if hourly_df is None or hourly_df.empty or len(hourly_df) < MINIMUM_HOURLY_ROWS:
            return None

        return hourly_df.sort_index()
    except Exception:
        return None


def _pick_current_price(
    realtime: Optional[dict],
    historical_close: float,
) -> tuple[float, str, bool]:
    if isinstance(realtime, dict):
        trade_price = _safe_float(realtime.get("trade_price"))

        if trade_price is not None and trade_price > 0:
            return (
                trade_price,
                str(realtime.get("price_source", "最新成交價")),
                bool(realtime.get("is_realtime_trade", True)),
            )

        price = _safe_float(realtime.get("price"))

        if price is not None and price > 0:
            return (
                price,
                str(realtime.get("price_source", "即時行情參考價")),
                bool(realtime.get("is_realtime_trade", False)),
            )

    return historical_close, "最新完整日線收盤價", False


def _series_to_candles(df: pd.DataFrame) -> list[dict]:
    candles: list[dict] = []

    for timestamp, row in df.tail(CHART_ROWS).iterrows():
        open_price = _safe_float(row.get("Open"))
        high_price = _safe_float(row.get("High"))
        low_price = _safe_float(row.get("Low"))
        close_price = _safe_float(row.get("Close"))

        if None in {open_price, high_price, low_price, close_price}:
            continue

        candles.append(
            {
                "time": _format_time(timestamp),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": _safe_int(row.get("Volume")),
            }
        )

    return candles


def _line_data(df: pd.DataFrame, column: str) -> list[dict]:
    if column not in df.columns:
        return []

    output: list[dict] = []
    series = pd.to_numeric(df[column].tail(CHART_ROWS), errors="coerce").dropna()

    for timestamp, value in series.items():
        number = _safe_float(value)

        if number is None:
            continue

        output.append({"time": _format_time(timestamp), "value": number})

    return output


def _demo_candles(seed: int, count: int = 120) -> list[dict]:
    random.seed(seed)
    start = datetime.now() - timedelta(days=count * 1.5)
    price = 38.0
    candles: list[dict] = []

    for index in range(count):
        date = start + timedelta(days=index * 1.5)
        drift = 0.12 if index > 40 else 0.02
        close = max(1.0, price + drift + random.uniform(-0.8, 0.8))
        high = max(price, close) + random.uniform(0.1, 0.6)
        low = min(price, close) - random.uniform(0.1, 0.5)

        candles.append(
            {
                "time": date.strftime("%Y-%m-%d"),
                "open": round(price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": int(random.uniform(5_000_000, 20_000_000)),
            }
        )
        price = close

    return candles


def _moving_average(candles: list[dict], period: int) -> list[dict]:
    closes = [float(item["close"]) for item in candles]
    output: list[dict] = []

    for index in range(period - 1, len(candles)):
        window = closes[index - period + 1 : index + 1]
        output.append(
            {
                "time": candles[index]["time"],
                "value": round(sum(window) / period, 2),
            }
        )

    return output


def _demo_response(stock_code: str, position_status: str) -> dict:
    code = _normalize_code(stock_code)
    candles = _demo_candles(sum(ord(char) for char in code))
    latest = candles[-1]
    previous = candles[-2]
    change = round(latest["close"] - previous["close"], 2)
    change_percent = round(change / previous["close"] * 100, 2)

    return {
        "stock": {
            "code": code,
            "name": "元大高股息" if code == "0056" else "示範股票",
            "market": "上市",
            "price": latest["close"],
            "change": change,
            "change_percent": change_percent,
            "open": latest["open"],
            "high": latest["high"],
            "low": latest["low"],
            "volume": latest["volume"],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "price_source": "Demo 資料",
            "is_realtime_trade": False,
            "best_bid": None,
            "best_ask": None,
        },
        "analysis": {
            "technical_score": 72.0,
            "total_score": 72.0,
            "score_level": "偏強",
            "direction": "偏多",
            "stage": "WAITING_BREAKOUT",
            "market_regime": "TRENDING",
            "confidence": "中",
            "trade_eligible": False,
            "subscores": {
                "trend": 24.0,
                "location": 14.0,
                "trigger": 12.0,
                "risk": 14.0,
                "market": 8.0,
            },
            "plan": {
                "trigger_price": round(latest["close"] * 1.015, 2),
                "stop_price": round(latest["close"] * 0.955, 2),
                "risk_percent": 4.5,
                "reward_risk_ratio": 2.1,
            },
            "reasons": [
                "價格位於中期均線上方。",
                "EMA20 高於 EMA60，日線方向偏多。",
                "目前仍等待60分鐘收盤突破觸發價。",
                "預估報酬風險比高於2R。",
            ],
            "veto_reasons": ["Demo 模式不具備正式交易資格。"],
            "historical_similarity": None,
            "historical_sample_size": 0,
            "indicators": {
                "ema20": None,
                "ema60": None,
                "rsi": None,
                "macd": None,
                "macd_signal": None,
                "macd_histogram": None,
                "k": None,
                "d": None,
                "atr": None,
                "atr_percent": None,
                "adx": None,
                "volume_ratio": None,
            },
            "recommendation": {
                "position_status": position_status,
                "position_label": "已持有" if position_status == "holding" else "尚未持有",
                "action": "DEMO",
                "title": "Demo 模式不提供正式判斷",
                "summary": "請切換到真實資料後重新分析。",
                "tone": "neutral",
                "disclaimer": "此結果是量化決策支援，不保證獲利，也不是自動下單指令。",
            },
            "perspectives": {
                "technical": {
                    "available": True,
                    "score": 72.0,
                    "label": "Score Engine V2",
                    "summary": "依趨勢、位置、觸發、風險與量價環境計算。",
                },
                "fundamental": {
                    "available": False,
                    "score": None,
                    "label": "Demo 不提供估值",
                    "summary": "切換到真實資料後，會讀取交易所每日估值資料。",
                    "pe_ratio": None,
                    "pb_ratio": None,
                    "dividend_yield": None,
                    "as_of": None,
                    "source": "Demo",
                },
                "news": {
                    "available": False,
                    "score": None,
                    "label": "Demo 不提供新聞",
                    "summary": "切換到真實資料後，會讀取近期新聞標題。",
                    "positive_hits": 0,
                    "negative_hits": 0,
                    "articles": [],
                    "source": "Demo",
                },
                "composite": {
                    "score": 72.0,
                    "available_axes": 1,
                    "method": "可用面向等權平均；缺少的面向不計入。",
                },
            },
        },
        "chart": {
            "candles": candles,
            "ma20": _moving_average(candles, 20),
            "ma60": _moving_average(candles, 60),
        },
        "watchlist": [
            {"code": "2330", "name": "台積電", "price": 1045, "change_percent": -1.45, "score": 82},
            {"code": "2317", "name": "鴻海", "price": 193.5, "change_percent": -1.02, "score": 76},
            {"code": "2454", "name": "聯發科", "price": 1235, "change_percent": -1.44, "score": 85},
            {"code": "2603", "name": "長榮", "price": 177, "change_percent": 2.02, "score": 80},
        ],
        "meta": {
            "daily_rows": len(candles),
            "hourly_rows": 0,
            "hourly_available": False,
            "analysis_engine": "Demo",
        },
        "demo": True,
    }


def _real_response(stock_code: str, position_status: str) -> dict:
    try:
        from indicators import add_indicators
        from realtime import get_realtime_price
        from score_engine.calculate import calculate_score
        from stock import download_stock
    except ImportError as error:
        raise RuntimeError(
            "請確認 backend 內有 stock.py、indicators.py、realtime.py 與 score_engine/。"
        ) from error

    try:
        from stock import download_hourly_stock
    except ImportError:
        download_hourly_stock = None

    code = _normalize_code(stock_code)

    # 官方歷史資料與即時行情互不相依，同時取得可避免兩段網路等待
    # 疊加。額外取得一個月可確保圖表涵蓋完整的一年交易日。
    with ThreadPoolExecutor(max_workers=2) as executor:
        daily_future = executor.submit(
            _download_interactive_daily_history,
            download_stock,
            code,
        )
        realtime_future = executor.submit(get_realtime_price, code)

        raw_daily_df = daily_future.result()

        try:
            realtime = realtime_future.result()
        except Exception:
            realtime = None

    daily_source = str(raw_daily_df.attrs.get("source", ""))
    history_recovery = dict(raw_daily_df.attrs.get("history_recovery", {}))
    history_coverage = frame_coverage(raw_daily_df)
    daily_df = _validate_daily_dataframe(add_indicators(raw_daily_df))

    # 官方月報提供穩定的免費日線，但不提供60分鐘K線。避免在已知
    # Yahoo 被限流時又等待兩次無效的盤中下載；介面會明確標示此狀態。
    if daily_source == "Yahoo Finance":
        hourly_df = _prepare_hourly_dataframe(
            download_hourly_stock=download_hourly_stock,
            add_indicators=add_indicators,
            stock_code=code,
        )
    else:
        hourly_df = None

    latest = daily_df.iloc[-1]
    historical_close = _safe_float(latest.get("Close"))

    if historical_close is None or historical_close <= 0:
        raise ValueError("無法取得有效的最新日線收盤價。")

    current_price, price_source, is_realtime_trade = _pick_current_price(
        realtime=realtime,
        historical_close=historical_close,
    )

    result = calculate_score(
        df=daily_df,
        current_price=current_price,
        hourly_df=hourly_df,
        historical_similarity=None,
        historical_sample_size=None,
        return_details=True,
    )

    previous_close = _safe_float(
        daily_df["Close"].iloc[-2] if len(daily_df) >= 2 else historical_close,
        historical_close,
    )
    change = current_price - (previous_close or current_price)
    change_percent = change / previous_close * 100 if previous_close and previous_close > 0 else 0.0

    realtime_dict = realtime if isinstance(realtime, dict) else {}
    updated_at = " ".join(
        part
        for part in [
            str(realtime_dict.get("date", "")).strip(),
            str(realtime_dict.get("time", "")).strip(),
        ]
        if part
    ) or _format_time(daily_df.index[-1], include_clock=True)

    ma20_name = "EMA20" if "EMA20" in daily_df.columns else "MA20"
    ma60_name = "EMA60" if "EMA60" in daily_df.columns else "MA60"

    open_price = _safe_float(realtime_dict.get("open"), _safe_float(latest.get("Open")))
    high_price = _safe_float(realtime_dict.get("high"), _safe_float(latest.get("High")))
    low_price = _safe_float(realtime_dict.get("low"), _safe_float(latest.get("Low")))
    total_volume = _safe_int(
        realtime_dict.get("total_volume"),
        _safe_int(latest.get("Volume")),
    )

    stock_name = str(realtime_dict.get("name", "")).strip()
    stock_market = str(
        realtime_dict.get(
            "market",
            daily_df.attrs.get("market", "台股"),
        )
    )
    technical_score = _safe_float(result.total_score, 0.0) or 0.0
    perspectives = build_perspectives(
        technical_score=technical_score,
        stock_code=code,
        market=stock_market,
        stock_name=stock_name,
    )

    return {
        "stock": {
            "code": code,
            "name": stock_name,
            "market": stock_market,
            "price": current_price,
            "change": round(change, 4),
            "change_percent": round(change_percent, 4),
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "volume": total_volume,
            "updated_at": updated_at,
            "price_source": price_source,
            "is_realtime_trade": is_realtime_trade,
            "best_bid": _safe_float(realtime_dict.get("best_bid")),
            "best_ask": _safe_float(realtime_dict.get("best_ask")),
        },
        "analysis": {
            "technical_score": technical_score,
            "total_score": technical_score,
            "score_level": _score_level(result.total_score),
            "direction": str(result.direction),
            "stage": str(result.stage),
            "market_regime": str(result.market_regime),
            "confidence": str(result.confidence),
            "trade_eligible": bool(result.trade_eligible),
            "subscores": {
                "trend": _safe_float(result.trend_score, 0.0),
                "location": _safe_float(result.location_score, 0.0),
                "trigger": _safe_float(result.trigger_score, 0.0),
                "risk": _safe_float(result.risk_score, 0.0),
                "market": _safe_float(result.market_score, 0.0),
            },
            "plan": {
                "trigger_price": _safe_float(result.trigger_price),
                "stop_price": _safe_float(result.stop_price),
                "risk_percent": _safe_float(result.risk_percent),
                "reward_risk_ratio": _safe_float(result.reward_risk_ratio),
            },
            "reasons": list(result.reasons or []),
            "veto_reasons": list(getattr(result, "veto_reasons", []) or []),
            "historical_similarity": _safe_float(
                getattr(result, "historical_similarity", None)
            ),
            "historical_sample_size": _safe_int(
                getattr(result, "historical_sample_size", 0)
            ),
            "indicators": _indicator_snapshot(latest),
            "recommendation": _build_recommendation(
                result=result,
                current_price=current_price,
                position_status=position_status,
            ),
            "perspectives": perspectives,
        },
        "chart": {
            "candles": _series_to_candles(daily_df),
            "ma20": _line_data(daily_df, ma20_name),
            "ma60": _line_data(daily_df, ma60_name),
        },
        "watchlist": [],
        "meta": {
            "daily_rows": len(daily_df),
            "hourly_rows": len(hourly_df) if hourly_df is not None else 0,
            "hourly_available": hourly_df is not None and not hourly_df.empty,
            "analysis_engine": "Score Engine V2",
            "daily_source": daily_source or "未知",
            "history_coverage": history_coverage,
            "history_recovery": history_recovery,
            "requested_history_months": INTERACTIVE_HISTORY_MONTHS,
        },
        "demo": False,
    }


def analyze_stock(stock_code: str, position_status: str = "not_holding") -> dict:
    normalized_position = _normalize_position_status(position_status)

    if settings.use_demo_data:
        return _demo_response(stock_code, normalized_position)

    return _real_response(stock_code, normalized_position)
