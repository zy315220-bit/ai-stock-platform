from __future__ import annotations

import hashlib
import json
import math
from statistics import NormalDist
from typing import Any


WILSON_REFERENCE = {
    "title": "Probable Inference, the Law of Succession, and Statistical Inference",
    "author": "Edwin B. Wilson",
    "year": 1927,
    "journal": "Journal of the American Statistical Association",
    "doi": "10.1080/01621459.1927.10502953",
}

BACKTEST_OVERFITTING_REFERENCE = {
    "title": "The Probability of Backtest Overfitting",
    "authors": "David H. Bailey, Jonathan M. Borwein, Marcos Lopez de Prado, Qiji Jim Zhu",
    "year": 2015,
    "journal": "Journal of Computational Finance",
    "doi": "10.2139/ssrn.2326253",
}

TWSE_COST_REFERENCE = {
    "title": "Taiwan Stock Exchange - Trading Mechanism / Transaction Cost and Taxes",
    "organization": "Taiwan Stock Exchange",
    "note": (
        "Broker commission schedules vary by broker; securities transaction tax is "
        "levied on the seller according to product type. Competition runs must use "
        "the same explicit cost assumptions for every robot."
    ),
}

FAIRNESS_FIELDS = (
    "initial_capital",
    "period_start",
    "period_end",
    "cost_model_id",
    "risk_model_id",
    "market_universe_id",
)


def freeze_robot_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical, versionable robot rule specification.

    The SHA-256 fingerprint makes any rule change visible. A robot should never
    be compared under the same version after its rule fingerprint changes.
    """

    if not isinstance(spec, dict) or not spec:
        raise ValueError("機器人規則不能是空白。")

    canonical = json.dumps(
        spec,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return {
        "spec": spec,
        "canonical_json": canonical,
        "rule_fingerprint": fingerprint,
        "immutable": True,
    }


def wilson_interval(
    wins: int,
    trials: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial win probability."""

    if trials < 0 or wins < 0 or wins > trials:
        raise ValueError("勝場與交易次數不合理。")
    if trials == 0:
        return 0.0, 1.0
    if not 0 < confidence < 1:
        raise ValueError("confidence 必須介於 0 與 1 之間。")

    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    n = float(trials)
    p = wins / n
    z2 = z * z
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    margin = (
        z
        * math.sqrt((p * (1 - p) / n) + (z2 / (4 * n * n)))
        / denominator
    )

    return max(0.0, center - margin), min(1.0, center + margin)


def _require_number(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool):
        raise ValueError(f"{key} 必須是數值。")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{key} 必須是數值。") from error
    if not math.isfinite(number):
        raise ValueError(f"{key} 必須是有限數值。")
    return number


def _validate_fairness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("至少需要一個機器人結果。")

    baseline = rows[0]
    mismatches: dict[str, list[Any]] = {}

    for field in FAIRNESS_FIELDS:
        expected = baseline.get(field)
        different = [row.get(field) for row in rows if row.get(field) != expected]
        if different:
            mismatches[field] = [expected, *different]

    if mismatches:
        fields = "、".join(mismatches)
        raise ValueError(
            f"機器人競賽條件不一致：{fields}。"
            "所有機器人必須使用相同初始資金、期間、交易成本、風控與市場母體。"
        )

    return {field: baseline.get(field) for field in FAIRNESS_FIELDS}


def rank_robot_results(
    rows: list[dict[str, Any]],
    *,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Rank fixed-rule robots with win rate as the primary objective.

    Raw win rate alone over-rewards robots with very few trades. The primary
    ranking statistic is therefore the lower bound of the Wilson confidence
    interval. Raw win rate remains visible and is the first tie-breaker.
    """

    fairness = _validate_fairness(rows)
    ranked: list[dict[str, Any]] = []

    for row in rows:
        robot_id = str(row.get("robot_id") or "").strip()
        robot_version = str(row.get("robot_version") or "").strip()
        fingerprint = str(row.get("rule_fingerprint") or "").strip()

        if not robot_id or not robot_version or not fingerprint:
            raise ValueError(
                "每個機器人都必須提供 robot_id、robot_version 與 rule_fingerprint。"
            )

        trades = int(_require_number(row, "trade_count"))
        wins = int(_require_number(row, "winning_trade_count"))
        if trades < 0 or wins < 0 or wins > trades:
            raise ValueError(f"{robot_id} 的勝場或交易次數不合理。")

        total_return = _require_number(row, "total_return_percent")
        max_drawdown = _require_number(row, "max_drawdown_percent")
        lower, upper = wilson_interval(wins, trades, confidence)
        raw_win_rate = (wins / trades * 100) if trades else 0.0

        ranked.append(
            {
                **row,
                "raw_win_rate_percent": round(raw_win_rate, 4),
                "win_rate_confidence": confidence,
                "wilson_lower_percent": round(lower * 100, 4),
                "wilson_upper_percent": round(upper * 100, 4),
                "ranking_primary_metric": "wilson_lower_percent",
                "total_return_percent": total_return,
                "max_drawdown_percent": max_drawdown,
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["wilson_lower_percent"],
            -item["raw_win_rate_percent"],
            -item["total_return_percent"],
            item["max_drawdown_percent"],
            item["robot_id"],
        )
    )

    for index, item in enumerate(ranked, start=1):
        item["rank"] = index

    return {
        "objective": "找出在公平條件下，勝率證據最強且規則固定的機器人。",
        "ranking_method": (
            "第一排序使用 Wilson 95% 勝率信賴區間下界；"
            "同分依原始勝率、總報酬、較小最大回撤排序。"
        ),
        "fairness": fairness,
        "robots": ranked,
        "research_notes": [
            (
                "Wilson 下界避免只因少量交易出現極高原始勝率就直接排名第一；"
                "交易數增加後，區間會逐漸收斂。"
            ),
            (
                "策略規則必須版本化並固定；反覆依回測結果調參會增加 backtest overfitting 風險。"
            ),
            (
                "勝率是主要目標，但總報酬與最大回撤仍保留作為安全與經濟意義的檢查指標。"
            ),
        ],
    }


def competition_methodology() -> dict[str, Any]:
    return {
        "primary_goal": "最高且有足夠統計證據的勝率",
        "primary_metric": "Wilson score interval lower bound",
        "confidence": 0.95,
        "fairness_fields": list(FAIRNESS_FIELDS),
        "robot_rule_policy": (
            "每個機器人規則需固定、版本化並保存 SHA-256 fingerprint；"
            "若規則改變，必須建立新版本，不可覆蓋舊版本績效。"
        ),
        "anti_overfitting_policy": (
            "平台應保留未參與調參的 out-of-sample / forward 測試；"
            "後續策略數量足夠時加入 CSCV/PBO 檢驗。"
        ),
        "references": [
            WILSON_REFERENCE,
            BACKTEST_OVERFITTING_REFERENCE,
            TWSE_COST_REFERENCE,
        ],
    }
