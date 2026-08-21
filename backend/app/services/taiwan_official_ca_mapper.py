"""Map official Taiwan exchange ex-right/ex-dividend records into canonical CA fields.

This module intentionally maps only fields whose semantics are explicitly
published by the exchange. Unknown or incomplete records fail closed upstream.
TPEx publishes cash dividend, stock-dividend rate, rights-issue rate and
subscription price in its ex-right/ex-dividend datasets.
"""
from __future__ import annotations

from typing import Any


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, "", "--"):
            return record[key]
    return None


def _num(value: Any) -> float:
    if value in (None, "", "--"):
        return 0.0
    text = str(value).replace(",", "").replace("%", "").strip()
    return float(text)


def map_tpex_exright_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert one official TPEx ex-right/ex-dividend row to explicit CA events.

    Rates published as percentages are converted to per-share ratios. Rights
    issues retain subscription price instead of pretending the entitlement is a
    cash dividend; the ledger policy can therefore fail closed until disposition
    is explicitly configured.
    """
    code = str(_first(record, "股票代號", "證券代號", "SecuritiesCompanyCode") or "").strip()
    ex_date = str(_first(record, "除權息日期", "資料日期", "Date") or "").strip()
    if not code or not ex_date:
        raise ValueError("TPEx CA record missing stock code or effective date")

    events: list[dict[str, Any]] = []
    cash = _num(_first(record, "現金股利", "現金股利 NT$", "CashDividend"))
    stock_pct = _num(_first(record, "無償配股率", "無償增資配股率％", "StockDividendRate"))
    rights_pct = _num(_first(record, "現金增資配股率", "現金增資配股率％", "RightsIssueRate"))
    subscription = _first(record, "現金增資認購價", "現金增資認購價(每股)", "SubscriptionPrice")

    base = {"stock_code": code, "effective_date": ex_date, "source": "TPEx_official"}
    if cash > 0:
        events.append({**base, "event_type": "cash_dividend", "cash_per_share": cash})
    if stock_pct > 0:
        events.append({**base, "event_type": "stock_dividend", "ratio": 1.0 + stock_pct / 100.0})
    if rights_pct > 0:
        if subscription in (None, "", "--"):
            raise ValueError("TPEx rights issue missing official subscription price")
        events.append({
            **base,
            "event_type": "rights_issue",
            "rights_ratio": rights_pct / 100.0,
            "subscription_price": _num(subscription),
        })
    if not events:
        raise ValueError("TPEx CA record contains no recognized economic event")
    return events
