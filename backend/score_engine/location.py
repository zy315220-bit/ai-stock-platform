from dataclasses import dataclass
from typing import List


@dataclass
class LocationResult:
    score: float
    state: str
    distance_atr: float
    reasons: List[str]


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def score_location(
    close: float,
    ema20: float,
    ema60: float,
    atr: float,
) -> LocationResult:
    """
    日線進場位置評分，滿分20分。

    核心概念：
    1. 多頭中靠近EMA20通常是較合理的波段位置。
    2. 距離EMA20太遠，代表追價風險增加。
    3. 跌破EMA60太多，可能已不是正常回檔。
    """

    if close <= 0:
        raise ValueError("close 必須大於0。")

    if ema20 <= 0 or ema60 <= 0:
        raise ValueError("EMA20及EMA60必須大於0。")

    if atr <= 0:
        raise ValueError("ATR必須大於0。")

    reasons = []

    distance_atr = (close - ema20) / atr

    # ==============================================
    # 1. 距離EMA20位置：14分
    # ==============================================

    if -0.50 <= distance_atr <= 0.50:
        ema20_score = 14.0
        state = "IDEAL_PULLBACK"
        text = "價格位於EMA20附近的理想回檔區"

    elif 0.50 < distance_atr <= 1.00:
        ema20_score = 11.0
        state = "SLIGHTLY_EXTENDED"
        text = "價格略高於EMA20，仍可觀察"

    elif 1.00 < distance_atr <= 1.50:
        ema20_score = 7.0
        state = "EXTENDED"
        text = "價格距離EMA20偏遠，追價風險增加"

    elif distance_atr > 1.50:
        ema20_score = max(
            1.0,
            7.0 - (distance_atr - 1.5) * 3.0,
        )
        state = "OVEREXTENDED"
        text = "價格明顯遠離EMA20，不適合追價"

    elif -1.00 <= distance_atr < -0.50:
        ema20_score = 10.0
        state = "DEEP_PULLBACK"
        text = "價格低於EMA20，屬於較深回檔"

    elif -1.50 <= distance_atr < -1.00:
        ema20_score = 6.0
        state = "WEAK_PULLBACK"
        text = "回檔幅度偏深，需要等待止跌"

    else:
        ema20_score = 2.0
        state = "STRUCTURE_WARNING"
        text = "價格大幅低於EMA20，可能不是正常回檔"

    reasons.append(
        f"{text}，距離EMA20為 {distance_atr:+.2f} ATR "
        f"(+{ema20_score:.1f}/14)"
    )

    # ==============================================
    # 2. EMA60結構保護：6分
    # ==============================================

    ema60_distance_atr = (close - ema60) / atr

    structure_score = clamp(
        (ema60_distance_atr + 1.0) / 2.0 * 6.0,
        0.0,
        6.0,
    )

    if close >= ema60:
        structure_text = "價格仍位於EMA60上方"
    else:
        structure_text = "價格已低於EMA60，結構轉弱"

    reasons.append(
        f"{structure_text}，距離EMA60為 "
        f"{ema60_distance_atr:+.2f} ATR "
        f"(+{structure_score:.1f}/6)"
    )

    total_score = round(
        clamp(ema20_score + structure_score, 0.0, 20.0),
        1,
    )

    return LocationResult(
        score=total_score,
        state=state,
        distance_atr=round(distance_atr, 3),
        reasons=reasons,
    )