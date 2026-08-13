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

FAIRNESS_FIELDS = (
    "initial_capital", "period_start", "period_end", "cost_model_id",
    "risk_model_id", "market_universe_id",
)


def freeze_robot_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict) or not spec:
        raise ValueError("機器人規則不能是空白。")
    canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "spec": spec,
        "canonical_json": canonical,
        "rule_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "immutable": True,
    }


def wilson_interval(wins: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
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
    margin = z * math.sqrt((p * (1 - p) / n) + (z2 / (4 * n * n))) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _number(row: dict[str, Any], key: str) -> float:
    try:
        value = float(row.get(key))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{key} 必須是數值。") from error
    if not math.isfinite(value):
        raise ValueError(f"{key} 必須是有限數值。")
    return value


def rank_robot_results(rows: list[dict[str, Any]], confidence: float = 0.95) -> dict[str, Any]:
    if not rows:
        raise ValueError("至少需要一個機器人結果。")
    baseline = rows[0]
    for field in FAIRNESS_FIELDS:
        if any(row.get(field) != baseline.get(field) for row in rows):
            raise ValueError(f"機器人競賽條件不一致：{field}。")

    ranked = []
    for row in rows:
        if not all(str(row.get(k) or "").strip() for k in ("robot_id", "robot_version", "rule_fingerprint")):
            raise ValueError("每個機器人都必須提供 robot_id、robot_version 與 rule_fingerprint。")
        trades = int(_number(row, "trade_count"))
        wins = int(_number(row, "winning_trade_count"))
        lower, upper = wilson_interval(wins, trades, confidence)
        ranked.append({
            **row,
            "raw_win_rate_percent": round((wins / trades * 100) if trades else 0.0, 4),
            "wilson_lower_percent": round(lower * 100, 4),
            "wilson_upper_percent": round(upper * 100, 4),
            "total_return_percent": _number(row, "total_return_percent"),
            "max_drawdown_percent": _number(row, "max_drawdown_percent"),
        })

    ranked.sort(key=lambda x: (-x["wilson_lower_percent"], -x["raw_win_rate_percent"], -x["total_return_percent"], x["max_drawdown_percent"], str(x["robot_id"])))
    for index, item in enumerate(ranked, 1):
        item["rank"] = index

    return {
        "objective": "找出公平條件下勝率證據最強且規則固定的機器人。",
        "primary_metric": "Wilson 95% confidence interval lower bound",
        "robots": ranked,
    }


def competition_methodology() -> dict[str, Any]:
    return {
        "primary_goal": "最高且有足夠統計證據的勝率",
        "primary_metric": "Wilson score interval lower bound",
        "confidence": 0.95,
        "fairness_fields": list(FAIRNESS_FIELDS),
        "robot_rule_policy": "規則固定並以 SHA-256 指紋版本化；規則改變即建立新版本。",
        "anti_overfitting_policy": "保留 out-of-sample / forward 測試，後續策略數量足夠時加入 CSCV/PBO。",
        "references": [WILSON_REFERENCE, BACKTEST_OVERFITTING_REFERENCE],
    }
