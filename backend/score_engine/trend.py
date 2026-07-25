from dataclasses import dataclass
from typing import List


@dataclass
class TrendResult:
    score: float
    direction: str
    reasons: List[str]


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def score_trend(close, ema20, ema60):
    """
    日線 EMA20／EMA60 趨勢評分。

    滿分30分，採連續評分，
    沒有完全符合時不直接歸零。
    """

    if close <= 0:
        raise ValueError("close 必須大於0。")

    if ema20 <= 0 or ema60 <= 0:
        raise ValueError("EMA20與EMA60必須大於0。")

    reasons = []

    # ==============================================
    # 1. EMA20／EMA60相對距離：15分
    # ==============================================

    ema_distance_pct = (
        (ema20 - ema60)
        / ema60
        * 100
    )

    ema_score = clamp(
        (ema_distance_pct + 3.0)
        / 6.0
        * 15.0,
        0.0,
        15.0,
    )

    reasons.append(
        f"EMA20與EMA60距離 {ema_distance_pct:+.2f}% "
        f"(+{ema_score:.1f}/15)"
    )

    # ==============================================
    # 2. 股價相對EMA20位置：10分
    # ==============================================

    close_ema20_pct = (
        (close - ema20)
        / ema20
        * 100
    )

    price_score = clamp(
        (close_ema20_pct + 3.0)
        / 6.0
        * 10.0,
        0.0,
        10.0,
    )

    # 太高也不應持續加分，避免鼓勵追價。
    if close_ema20_pct > 8.0:
        price_score = min(price_score, 5.0)
        price_text = "股價距離EMA20過遠，存在追價風險"

    elif close_ema20_pct > 3.0:
        price_score = min(price_score, 8.0)
        price_text = "股價位於EMA20上方，但略有延伸"

    elif close_ema20_pct >= -1.0:
        price_text = "股價位於EMA20附近的合理區域"

    else:
        price_text = "股價位於EMA20下方"

    reasons.append(
        f"{price_text}，距離 {close_ema20_pct:+.2f}% "
        f"(+{price_score:.1f}/10)"
    )

    # ==============================================
    # 3. 股價相對EMA60位置：5分
    # ==============================================

    close_ema60_pct = (
        (close - ema60)
        / ema60
        * 100
    )

    structure_score = clamp(
        (close_ema60_pct + 5.0)
        / 10.0
        * 5.0,
        0.0,
        5.0,
    )

    reasons.append(
        f"股價與EMA60距離 {close_ema60_pct:+.2f}% "
        f"(+{structure_score:.1f}/5)"
    )

    total_score = round(
        clamp(
            ema_score
            + price_score
            + structure_score,
            0.0,
            30.0,
        ),
        1,
    )

    if ema20 > ema60 and close >= ema60:
        direction = "LONG"
    else:
        direction = "WAIT"

    return TrendResult(
        score=total_score,
        direction=direction,
        reasons=reasons,
    )