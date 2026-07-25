from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

import math
import pandas as pd

from .trend import score_trend
from .location import score_location
from .market import score_market
from .risk import score_risk
from .trigger import score_trigger
from .similarity import score_similarity


@dataclass
class ScoreResult:
    total_score: float

    trend_score: float
    location_score: float
    trigger_score: float
    risk_score: float
    market_score: float

    direction: str
    stage: str
    market_regime: str
    confidence: str
    trade_eligible: bool

    stop_price: Optional[float]
    trigger_price: Optional[float]
    risk_percent: Optional[float]
    reward_risk_ratio: Optional[float]

    reasons: List[str] = field(default_factory=list)
    veto_reasons: List[str] = field(default_factory=list)

    historical_similarity: Optional[float] = None
    historical_sample_size: int = 0


def safe_float(
    value,
    default=None,
):
    """
    安全轉換為有限浮點數。
    """

    try:
        number = float(value)

        if math.isfinite(number):
            return number

    except (TypeError, ValueError):
        pass

    return default


def get_value(
    row: pd.Series,
    names,
    default=None,
):
    """
    從多個候選欄位中取得第一個有效數值。
    """

    for name in names:
        if name not in row.index:
            continue

        value = safe_float(row[name])

        if value is not None:
            return value

    return default


def determine_confidence(
    total_score: float,
    hourly_available: bool,
    sample_size: int,
) -> str:
    """
    根據總分、60分鐘資料及歷史樣本數判斷信心程度。
    """

    points = 0

    if total_score >= 80:
        points += 2

    elif total_score >= 65:
        points += 1

    if hourly_available:
        points += 2

    if sample_size >= 50:
        points += 2

    elif sample_size >= 20:
        points += 1

    if points >= 5:
        return "高"

    if points >= 3:
        return "中"

    return "低"


def calculate_score(
    df: pd.DataFrame,
    current_price=None,
    hourly_df: Optional[pd.DataFrame] = None,
    historical_similarity: Optional[float] = None,
    historical_sample_size: Optional[int] = None,
    return_details: bool = False,
) -> Union[
    ScoreResult,
    Tuple[float, List[str]],
]:
    """
    計算股票綜合技術評分。

    Parameters
    ----------
    df:
        已加入技術指標的日線資料。

    current_price:
        即時價格。若未提供，使用最新日線 Close。

    hourly_df:
        已加入技術指標的60分鐘資料。

    historical_similarity:
        歷史型態相似度。

    historical_sample_size:
        歷史相似樣本數。

    return_details:
        True 回傳 ScoreResult。
        False 回傳舊版相容格式：
        (total_score, reasons)。
    """

    if df is None or df.empty:
        raise ValueError(
            "沒有可供評分的日線資料。"
        )

    latest = df.iloc[-1]

    historical_close = get_value(
        latest,
        [
            "Close",
            "close",
        ],
    )

    close = safe_float(
        current_price,
        historical_close,
    )

    ema20 = get_value(
        latest,
        [
            "EMA20",
            "MA20",
        ],
    )

    ema60 = get_value(
        latest,
        [
            "EMA60",
            "MA60",
        ],
    )

    atr = get_value(
        latest,
        [
            "ATR",
            "atr",
        ],
    )

    if close is None or close <= 0:
        raise ValueError(
            "缺少有效的 Close 價格。"
        )

    if ema20 is None:
        raise ValueError(
            "缺少 EMA20 或 MA20 欄位。"
        )

    if ema60 is None:
        raise ValueError(
            "缺少 EMA60 或 MA60 欄位。"
        )

    if atr is None or atr <= 0:
        raise ValueError(
            "缺少有效 ATR 欄位。"
        )

    volume = get_value(
        latest,
        [
            "Volume",
            "volume",
        ],
    )

    vma20 = get_value(
        latest,
        [
            "VMA20",
            "VolumeMA20",
        ],
    )

    adx = get_value(
        latest,
        [
            "ADX",
            "ADX14",
        ],
    )

    natr = get_value(
        latest,
        ["NATR"],
        default=atr / close * 100.0,
    )

    # ==========================================
    # 最近支撐
    # ==========================================

    if "Low" in df.columns:
        recent_low = safe_float(
            pd.to_numeric(
                df["Low"].tail(10),
                errors="coerce",
            ).min()
        )
    else:
        recent_low = None

    # ==========================================
    # 最近壓力
    # ==========================================

    if "High" in df.columns:
        resistance = safe_float(
            pd.to_numeric(
                df["High"].tail(20),
                errors="coerce",
            ).max()
        )

        if (
            resistance is not None
            and resistance <= close
        ):
            resistance = None

    else:
        resistance = None

    # ==========================================
    # 各模組評分
    # ==========================================

    trend = score_trend(
        close=close,
        ema20=ema20,
        ema60=ema60,
    )

    location = score_location(
        close=close,
        ema20=ema20,
        ema60=ema60,
        atr=atr,
    )

    market = score_market(
        close=close,
        ema20=ema20,
        volume=volume,
        vma20=vma20,
        adx=adx,
        natr=natr,
    )

    risk = score_risk(
        close=close,
        atr=atr,
        recent_low=recent_low,
        resistance=resistance,
    )

    trigger = score_trigger(
        hourly_df=hourly_df,
    )

    similarity = score_similarity(
        similarity=historical_similarity,
        sample_size=historical_sample_size,
    )

    # ==========================================
    # 總分
    # ==========================================

    total_score = (
        trend.score
        + location.score
        + trigger.score
        + risk.score
        + market.score
        + similarity.adjustment
    )

    total_score = round(
        max(
            0.0,
            min(total_score, 100.0),
        ),
        1,
    )

    # ==========================================
    # 評分原因
    # ==========================================

    reasons = []

    reasons.extend(trend.reasons)
    reasons.extend(location.reasons)
    reasons.extend(trigger.reasons)
    reasons.extend(risk.reasons)
    reasons.extend(market.reasons)
    reasons.extend(similarity.reasons)

    # ==========================================
    # 否決條件
    # ==========================================

    veto_reasons = []

    if ema20 <= ema60:
        veto_reasons.append(
            "EMA20 尚未位於 EMA60 上方。"
        )

    if close < ema60:
        veto_reasons.append(
            "價格低於 EMA60，中期結構偏弱。"
        )

    hourly_available = (
        hourly_df is not None
        and not hourly_df.empty
    )

    if not hourly_available:
        veto_reasons.append(
            "尚未取得60分鐘觸發資料。"
        )

    risk_percent = safe_float(
        risk.risk_percent
    )

    if (
        risk_percent is None
        or risk_percent > 8
    ):
        veto_reasons.append(
            "停損距離無效或超過8%，風險過高。"
        )

    reward_risk_ratio = safe_float(
        risk.reward_risk_ratio
    )

    if (
        reward_risk_ratio is not None
        and reward_risk_ratio < 1.3
    ):
        veto_reasons.append(
            "預估報酬風險比低於1.3。"
        )

    if market.regime == "RANGING":
        veto_reasons.append(
            "ADX 顯示市場可能處於盤整。"
        )

    # ==========================================
    # 交易資格
    # ==========================================

    trade_eligible = (
        ema20 > ema60
        and close >= ema60
        and trigger.triggered
        and total_score >= 70
        and risk_percent is not None
        and risk_percent <= 8
        and not veto_reasons
    )

    # ==========================================
    # 交易階段
    # ==========================================

    if ema20 <= ema60:
        stage = "FILTERED"

    elif location.state == "OVEREXTENDED":
        stage = "WAITING_PULLBACK"

    elif trigger.stage == "TRIGGERED":
        stage = "TRIGGERED"

    elif trigger.stage == "PREPARING_TRIGGER":
        stage = "PREPARING_TRIGGER"

    elif trigger.stage in {
        "NO_HOURLY_DATA",
        "INSUFFICIENT_DATA",
        "MISSING_COLUMNS",
        "WAITING_STRUCTURE",
    }:
        stage = trigger.stage

    else:
        stage = "WAITING_BREAKOUT"

    confidence = determine_confidence(
        total_score=total_score,
        hourly_available=hourly_available,
        sample_size=similarity.sample_size,
    )

    # ==========================================
    # 組合結果
    # ==========================================

    result = ScoreResult(
        total_score=total_score,

        trend_score=trend.score,
        location_score=location.score,
        trigger_score=trigger.score,
        risk_score=risk.score,
        market_score=market.score,

        direction=trend.direction,
        stage=stage,
        market_regime=market.regime,
        confidence=confidence,
        trade_eligible=trade_eligible,

        stop_price=risk.stop_price,
        trigger_price=trigger.trigger_price,
        risk_percent=risk_percent,
        reward_risk_ratio=reward_risk_ratio,

        reasons=reasons,
        veto_reasons=veto_reasons,

        historical_similarity=similarity.similarity,
        historical_sample_size=similarity.sample_size,
    )

    if return_details:
        return result

    return (
        result.total_score,
        result.reasons,
    )