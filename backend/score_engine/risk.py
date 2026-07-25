from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RiskResult:
    score: float
    stop_price: float
    risk_percent: float
    reward_risk_ratio: Optional[float]
    reasons: List[str]


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def score_risk(
    close: float,
    atr: float,
    recent_low: Optional[float] = None,
    resistance: Optional[float] = None,
) -> RiskResult:
    """
    停損與報酬風險評分，滿分15分。

    停損：
    結構停損與ATR停損取較遠者。
    """

    if close <= 0:
        raise ValueError("close 必須大於0。")

    if atr <= 0:
        raise ValueError("ATR必須大於0。")

    reasons = []

    atr_stop = close - 1.2 * atr

    if recent_low is not None and recent_low > 0:
        structure_stop = recent_low - 0.2 * atr
        stop_price = min(atr_stop, structure_stop)

        reasons.append(
            f"ATR停損 {atr_stop:.2f}，"
            f"結構停損 {structure_stop:.2f}，"
            f"採較遠停損 {stop_price:.2f}"
        )
    else:
        stop_price = atr_stop
        reasons.append(
            f"缺少明確swing low，暫以1.2 ATR設定停損 "
            f"{stop_price:.2f}"
        )

    stop_price = max(0.01, stop_price)

    risk_distance = close - stop_price
    risk_percent = risk_distance / close * 100

    # ==============================================
    # 1. 停損距離品質：8分
    # ==============================================

    if 1.0 <= risk_percent <= 5.0:
        stop_score = 8.0
        stop_text = "停損距離合理"

    elif 0.5 <= risk_percent < 1.0:
        stop_score = 4.0
        stop_text = "停損可能過近，容易受到雜訊影響"

    elif 5.0 < risk_percent <= 8.0:
        stop_score = 5.0
        stop_text = "停損距離偏大，需要降低部位"

    elif risk_percent > 8.0:
        stop_score = 1.0
        stop_text = "停損距離過大"

    else:
        stop_score = 1.0
        stop_text = "停損設定異常"

    reasons.append(
        f"{stop_text}，初始風險 {risk_percent:.2f}% "
        f"(+{stop_score:.1f}/8)"
    )

    # ==============================================
    # 2. 報酬風險比：7分
    # ==============================================

    reward_risk_ratio = None

    if (
        resistance is not None
        and resistance > close
        and risk_distance > 0
    ):
        reward = resistance - close
        reward_risk_ratio = reward / risk_distance

        rr_score = clamp(
            (reward_risk_ratio - 0.8) / 1.7 * 7.0,
            0.0,
            7.0,
        )

        reasons.append(
            f"預估報酬風險比 {reward_risk_ratio:.2f}R "
            f"(+{rr_score:.1f}/7)"
        )

    else:
        rr_score = 3.5
        reasons.append(
            "尚未取得有效壓力目標，"
            "報酬風險比暫採中性分數 "
            "(+3.5/7)"
        )

    total_score = round(
        clamp(stop_score + rr_score, 0.0, 15.0),
        1,
    )

    return RiskResult(
        score=total_score,
        stop_price=round(stop_price, 2),
        risk_percent=round(risk_percent, 2),
        reward_risk_ratio=(
            round(reward_risk_ratio, 2)
            if reward_risk_ratio is not None
            else None
        ),
        reasons=reasons,
    )