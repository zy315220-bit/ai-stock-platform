from dataclasses import dataclass
from typing import List, Optional

import math


@dataclass
class SimilarityResult:
    similarity: Optional[float]
    sample_size: int
    reliability: float
    adjustment: float
    reasons: List[str]


def score_similarity(
    similarity: Optional[float],
    sample_size: Optional[int],
) -> SimilarityResult:
    """
    歷史相似度調整。

    不直接成為大量分數，
    最多只調整總分正負5分。
    """

    if similarity is None:
        return SimilarityResult(
            similarity=None,
            sample_size=0,
            reliability=0.0,
            adjustment=0.0,
            reasons=[
                "尚未執行歷史K線相似度分析，總分不調整"
            ],
        )

    similarity = max(
        0.0,
        min(float(similarity), 100.0),
    )

    sample_size = max(
        0,
        int(sample_size or 0),
    )

    if sample_size > 0:
        reliability = min(
            1.0,
            math.sqrt(sample_size / 50.0),
        )
    else:
        reliability = 0.0

    adjustment = (
        (similarity - 50.0)
        / 50.0
        * 5.0
        * reliability
    )

    return SimilarityResult(
        similarity=round(similarity, 1),
        sample_size=sample_size,
        reliability=round(reliability, 3),
        adjustment=round(adjustment, 1),
        reasons=[
            f"歷史相似度 {similarity:.1f}%、"
            f"樣本 {sample_size} 筆、"
            f"可靠度 {reliability * 100:.1f}%、"
            f"總分調整 {adjustment:+.1f}"
        ],
    )