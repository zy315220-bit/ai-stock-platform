from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any


INTERACTIVE_CHART_RANGES = ("1m", "3m", "6m", "1y", "3y", "5y")
INTERACTIVE_HISTORY_MONTHS = 13
# Fetch a materially deeper daily-history buffer than the minimum evidence
# horizon. Yahoo already requests 10y/max; keeping the official exchange
# fallback at the same order of magnitude prevents a temporary Yahoo gap from
# silently shrinking a six-year autonomous campaign to only ~5 years.
RESEARCH_HISTORY_MONTHS = 120
BACKTEST_WARMUP_MONTHS = 6
MINIMUM_RESEARCH_YEARS = 3
PREFERRED_RESEARCH_YEARS = 5
FORWARD_HOLDOUT_MONTHS = 12

# Point-in-time lifecycle metadata for the ETF research universe.  A request
# that starts before an instrument existed must not treat pre-listing months as
# missing market data or repeatedly invoke the official-history fallback.
KNOWN_LISTING_DATES = {
    "0050": date(2003, 6, 25),
    "0056": date(2007, 12, 26),
    "00878": date(2020, 7, 20),
    "00919": date(2022, 10, 20),
}


def effective_history_start_date(
    stock_code: str,
    requested_start: date,
) -> date:
    """Clamp a history request to a known point-in-time listing date."""
    normalized = stock_code.strip().upper().split(".", 1)[0]
    listing_date = KNOWN_LISTING_DATES.get(normalized)
    if listing_date is None:
        return requested_start
    return max(requested_start, listing_date)


def default_research_start_date(as_of: date | None = None) -> date:
    """Return the same calendar date five years earlier when possible."""
    current = as_of or date.today()
    target_year = current.year - PREFERRED_RESEARCH_YEARS
    target_day = min(current.day, monthrange(target_year, current.month)[1])
    return date(target_year, current.month, target_day)


def history_policy() -> dict[str, Any]:
    """Single source of truth for user-facing and strategy-research horizons."""
    return {
        "schema": "history-policy-v2",
        "interactive_chart_ranges": list(INTERACTIVE_CHART_RANGES),
        "interactive_history_months": INTERACTIVE_HISTORY_MONTHS,
        "research_history_months": RESEARCH_HISTORY_MONTHS,
        "backtest_warmup_months": BACKTEST_WARMUP_MONTHS,
        "minimum_research_years": MINIMUM_RESEARCH_YEARS,
        "preferred_research_years": PREFERRED_RESEARCH_YEARS,
        "forward_holdout_months": FORWARD_HOLDOUT_MONTHS,
        "principles": [
            "圖表時間範圍與策略研究樣本分離，避免使用者圖表設定改變研究證據。",
            "研究下載層盡量取得十年日線並保留額外 warm-up；正式長期證據門檻仍以實際可用資料判定。",
            "策略研究優先至少取得五年可靠日線；資料不足三年時不得標示為長期驗證。",
            "上市前不存在的資料不可補造；已知上市日以前不視為資料缺口。",
            "最後 forward holdout 不參與策略調參或冠軍選拔訓練。",
            "所有績效必須標示實際可用起訖日期，而不是宣稱不存在的資料。",
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
