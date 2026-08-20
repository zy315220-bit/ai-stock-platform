from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any


INTERACTIVE_CHART_RANGES = ("1m", "3m", "6m", "1y", "3y", "5y")
INTERACTIVE_HISTORY_MONTHS = 13
RESEARCH_HISTORY_MONTHS = 60
BACKTEST_WARMUP_MONTHS = 6
MINIMUM_RESEARCH_YEARS = 3
PREFERRED_RESEARCH_YEARS = 5
FORWARD_HOLDOUT_MONTHS = 12


def default_research_start_date(as_of: date | None = None) -> date:
    """Return the same calendar date five years earlier when possible."""
    current = as_of or date.today()
    target_year = current.year - PREFERRED_RESEARCH_YEARS
    target_day = min(current.day, monthrange(target_year, current.month)[1])
    return date(target_year, current.month, target_day)


def history_policy() -> dict[str, Any]:
    """Single source of truth for user-facing and strategy-research horizons."""
    return {
        "schema": "history-policy-v1",
        "interactive_chart_ranges": list(INTERACTIVE_CHART_RANGES),
        "interactive_history_months": INTERACTIVE_HISTORY_MONTHS,
        "research_history_months": RESEARCH_HISTORY_MONTHS,
        "backtest_warmup_months": BACKTEST_WARMUP_MONTHS,
        "minimum_research_years": MINIMUM_RESEARCH_YEARS,
        "preferred_research_years": PREFERRED_RESEARCH_YEARS,
        "forward_holdout_months": FORWARD_HOLDOUT_MONTHS,
        "principles": [
            "圖表時間範圍與策略研究樣本分離，避免使用者圖表設定改變研究證據。",
            "策略研究優先取得五年可靠日線；資料不足三年時不得標示為長期驗證。",
            "最後 forward holdout 不參與策略調參或冠軍選拔訓練。",
            "所有績效必須標示實際可用起訖日期，而不是宣稱不存在的五年資料。",
        ],
    }


def assess_history_coverage(*, available_days: int) -> dict[str, Any]:
    if available_days < 0:
        raise ValueError("available_days must be non-negative")

    years = available_days / 365.2425

    if years >= PREFERRED_RESEARCH_YEARS:
        status = "preferred"
    elif years >= MINIMUM_RESEARCH_YEARS:
        status = "acceptable"
    else:
        status = "insufficient_for_long_horizon_claim"

    return {
        "available_days": available_days,
        "available_years": round(years, 2),
        "status": status,
        "long_horizon_qualified": years >= MINIMUM_RESEARCH_YEARS,
    }
