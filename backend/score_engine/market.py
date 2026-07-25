from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MarketResult:
    score: float
    regime: str
    volume_ratio: float
    reasons: List[str]


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def score_market(
    close: float,
    ema20: float,
    volume: Optional[float] = None,
    vma20: Optional[float] = None,
    adx: Optional[float] = None,
    natr: Optional[float] = None,
) -> MarketResult:
    """
    量價及市場環境評分，滿分10分。

    成交量：4分
    ADX：4分
    NATR：2分
    """

    reasons = []

    # ==============================================
    # 1. 成交量：4分
    # ==============================================

    if (
        volume is not None
        and vma20 is not None
        and vma20 > 0
    ):
        volume_ratio = volume / vma20

        if close >= ema20:
            volume_score = clamp(
                1.0 + (volume_ratio - 0.5) / 1.0 * 3.0,
                1.0,
                4.0,
            )

            if volume_ratio >= 1.2:
                volume_text = "價格偏強且成交量放大"
            elif volume_ratio >= 0.8:
                volume_text = "價格偏強且成交量正常"
            else:
                volume_text = "價格偏強但成交量偏低"

        else:
            if volume_ratio >= 1.2:
                volume_score = 0.5
                volume_text = "價格偏弱且成交量放大"
            elif volume_ratio < 0.8:
                volume_score = 2.5
                volume_text = "回檔過程成交量縮小"
            else:
                volume_score = 1.5
                volume_text = "價格偏弱且成交量普通"

    else:
        volume_ratio = 1.0
        volume_score = 2.0
        volume_text = "缺少完整成交量資料，採中性評分"

    reasons.append(
        f"{volume_text}，量比 {volume_ratio:.2f} "
        f"(+{volume_score:.1f}/4)"
    )

    # ==============================================
    # 2. ADX趨勢環境：4分
    # ==============================================

    if adx is None:
        adx_score = 2.0
        regime = "UNKNOWN"
        adx_text = "缺少ADX資料，採中性評分"

    elif adx < 15:
        adx_score = 0.5
        regime = "RANGING"
        adx_text = "ADX偏低，市場可能處於盤整"

    elif adx < 20:
        adx_score = 2.0
        regime = "WEAK_TREND"
        adx_text = "ADX顯示趨勢仍偏弱"

    elif adx < 30:
        adx_score = 4.0
        regime = "TRENDING"
        adx_text = "ADX顯示趨勢環境良好"

    elif adx < 45:
        adx_score = 3.5
        regime = "STRONG_TREND"
        adx_text = "ADX顯示強趨勢"

    else:
        adx_score = 2.5
        regime = "EXTREME_TREND"
        adx_text = "ADX過高，可能已進入趨勢末段"

    if adx is None:
        reasons.append(f"{adx_text} (+{adx_score:.1f}/4)")
    else:
        reasons.append(
            f"{adx_text}，ADX={adx:.1f} "
            f"(+{adx_score:.1f}/4)"
        )

    # ==============================================
    # 3. NATR波動率：2分
    # ==============================================

    if natr is None:
        natr_score = 1.0
        natr_text = "缺少NATR資料，採中性評分"

    elif 1.0 <= natr <= 3.5:
        natr_score = 2.0
        natr_text = "目前波動率適合波段交易"

    elif 0.5 <= natr < 1.0:
        natr_score = 1.2
        natr_text = "目前波動率偏低"

    elif 3.5 < natr <= 5.0:
        natr_score = 1.0
        natr_text = "目前波動率偏高"

    else:
        natr_score = 0.3
        natr_text = "目前波動率極端"

    if natr is None:
        reasons.append(f"{natr_text} (+{natr_score:.1f}/2)")
    else:
        reasons.append(
            f"{natr_text}，NATR={natr:.2f}% "
            f"(+{natr_score:.1f}/2)"
        )

    total_score = round(
        clamp(
            volume_score + adx_score + natr_score,
            0.0,
            10.0,
        ),
        1,
    )

    return MarketResult(
        score=total_score,
        regime=regime,
        volume_ratio=round(volume_ratio, 3),
        reasons=reasons,
    )