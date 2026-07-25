from dataclasses import dataclass
from typing import List, Optional

import pandas as pd


@dataclass
class TriggerResult:
    score: float
    triggered: bool
    stage: str
    trigger_price: Optional[float]
    reasons: List[str]


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def score_trigger(
    hourly_df: Optional[pd.DataFrame],
) -> TriggerResult:
    """
    60分鐘進場觸發評分，滿分25分。

    預設邏輯：
    1. 是否形成higher low。
    2. 是否接近或突破前一段高點。
    3. 短期EMA是否轉強。
    4. 成交量是否確認。
    """

    if hourly_df is None or hourly_df.empty:
        return TriggerResult(
            score=10.0,
            triggered=False,
            stage="NO_HOURLY_DATA",
            trigger_price=None,
            reasons=[
                "尚未取得60分鐘資料，觸發層暫採中性分數 "
                "(+10.0/25)"
            ],
        )

    if len(hourly_df) < 10:
        return TriggerResult(
            score=10.0,
            triggered=False,
            stage="INSUFFICIENT_DATA",
            trigger_price=None,
            reasons=[
                "60分鐘資料不足10根，暫採中性分數 "
                "(+10.0/25)"
            ],
        )

    required = ["High", "Low", "Close"]

    missing = [
        column
        for column in required
        if column not in hourly_df.columns
    ]

    if missing:
        return TriggerResult(
            score=10.0,
            triggered=False,
            stage="MISSING_COLUMNS",
            trigger_price=None,
            reasons=[
                "60分鐘資料缺少欄位："
                + ", ".join(missing)
                + "，暫採中性分數 (+10.0/25)"
            ],
        )

    data = hourly_df.dropna(
        subset=["High", "Low", "Close"]
    ).copy()

    if len(data) < 10:
        return TriggerResult(
            score=10.0,
            triggered=False,
            stage="INSUFFICIENT_VALID_DATA",
            trigger_price=None,
            reasons=[
                "有效60分鐘資料不足，暫採中性分數 "
                "(+10.0/25)"
            ],
        )

    latest = data.iloc[-1]

    current_close = float(latest["Close"])
    current_low = float(latest["Low"])

    previous_block = data.iloc[-6:-1]

    previous_high = float(previous_block["High"].max())
    previous_low = float(previous_block["Low"].min())

    earlier_block = data.iloc[-10:-5]
    earlier_low = float(earlier_block["Low"].min())

    reasons = []

    # ==============================================
    # 1. Higher Low：8分
    # ==============================================

    if previous_low > earlier_low:
        higher_low_score = 8.0
        higher_low = True
        reasons.append(
            "60分鐘已形成higher low (+8.0/8)"
        )
    else:
        difference = (
            previous_low - earlier_low
        ) / max(abs(earlier_low), 0.01)

        higher_low_score = clamp(
            4.0 + difference * 100.0,
            0.0,
            6.0,
        )

        higher_low = False
        reasons.append(
            "60分鐘尚未確認higher low "
            f"(+{higher_low_score:.1f}/8)"
        )

    # ==============================================
    # 2. 突破進度：10分
    # ==============================================

    range_size = max(
        previous_high - previous_low,
        0.01,
    )

    breakout_progress = (
        current_close - previous_low
    ) / range_size

    breakout_score = clamp(
        breakout_progress * 10.0,
        0.0,
        10.0,
    )

    breakout = current_close > previous_high

    if breakout:
        breakout_score = 10.0
        breakout_text = "60分鐘收盤已突破前段高點"
    elif breakout_progress >= 0.8:
        breakout_text = "60分鐘價格已接近突破位置"
    elif breakout_progress >= 0.5:
        breakout_text = "60分鐘價格正在回升"
    else:
        breakout_text = "60分鐘價格尚未明顯轉強"

    reasons.append(
        f"{breakout_text}，突破進度 "
        f"{breakout_progress * 100:.1f}% "
        f"(+{breakout_score:.1f}/10)"
    )

    # ==============================================
    # 3. 成交量確認：4分
    # ==============================================

    if (
        "Volume" in data.columns
        and len(data["Volume"].dropna()) >= 6
    ):
        current_volume = float(
            data.iloc[-1]["Volume"]
        )

        average_volume = float(
            data.iloc[-6:-1]["Volume"].mean()
        )

        if average_volume > 0:
            volume_ratio = current_volume / average_volume
        else:
            volume_ratio = 1.0

        volume_score = clamp(
            (volume_ratio - 0.5) / 1.0 * 4.0,
            0.0,
            4.0,
        )

        reasons.append(
            f"60分鐘量比 {volume_ratio:.2f} "
            f"(+{volume_score:.1f}/4)"
        )
    else:
        volume_score = 2.0
        reasons.append(
            "缺少60分鐘成交量，暫採中性分數 "
            "(+2.0/4)"
        )

    # ==============================================
    # 4. 最新K棒收盤位置：3分
    # ==============================================

    current_high = float(latest["High"])
    candle_range = max(current_high - current_low, 0.01)

    close_position = (
        current_close - current_low
    ) / candle_range

    candle_score = clamp(
        close_position * 3.0,
        0.0,
        3.0,
    )

    reasons.append(
        f"最新60分鐘K棒收盤位置 "
        f"{close_position * 100:.1f}% "
        f"(+{candle_score:.1f}/3)"
    )

    total_score = round(
        clamp(
            higher_low_score
            + breakout_score
            + volume_score
            + candle_score,
            0.0,
            25.0,
        ),
        1,
    )

    triggered = (
        higher_low
        and breakout
        and total_score >= 18.0
    )

    if triggered:
        stage = "TRIGGERED"
    elif breakout_progress >= 0.8:
        stage = "WAITING_BREAKOUT"
    elif higher_low:
        stage = "PREPARING_TRIGGER"
    else:
        stage = "WAITING_STRUCTURE"

    return TriggerResult(
        score=total_score,
        triggered=triggered,
        stage=stage,
        trigger_price=round(previous_high, 2),
        reasons=reasons,
    )