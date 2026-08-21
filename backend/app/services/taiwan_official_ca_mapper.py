"""Map official Taiwan exchange ex-right/ex-dividend records into canonical CA fields.

Only explicitly published economic fields are mapped. Unknown/incomplete records
fail closed. TWSE/TPEX rates are ratios (e.g. 0.15 means 15%), not percentages;
therefore they must not be divided by 100 during canonical normalization.
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
    return float(str(value).replace(",", "").replace("%", "").strip())


def _map_exright_record(record: dict[str, Any], *, exchange: str) -> list[dict[str, Any]]:
    code = str(_first(record, "股票代號", "證券代號", "SecuritiesCompanyCode") or "").strip()
    ex_date = str(_first(record, "除權息日期", "除權除息日期", "資料日期", "Date") or "").strip()
    if not code or not ex_date:
        raise ValueError(f"{exchange} CA record missing stock code or effective date")

    events: list[dict[str, Any]] = []
    cash = _num(_first(record, "現金股利", "現金股利 NT$", "CashDividend"))
    stock_ratio = _num(_first(record, "無償配股率", "無償增資配股率％", "股票股利", "StockDividendRate"))
    rights_ratio = _num(_first(record, "現金增資配股率", "現金增資配股率％", "現金增資", "RightsIssueRate"))
    subscription = _first(record, "現金增資認購價", "現金增資認購價(每股)", "每股認購價格", "SubscriptionPrice")

    base = {"stock_code": code, "effective_date": ex_date, "source": f"{exchange}_official"}
    if cash > 0:
        events.append({**base, "event_type": "cash_dividend", "cash_per_share": cash})
    if stock_ratio > 0:
        events.append({**base, "event_type": "stock_dividend", "ratio": 1.0 + stock_ratio})
    if rights_ratio > 0:
        if subscription in (None, "", "--"):
            raise ValueError(f"{exchange} rights issue missing official subscription price")
        events.append({**base, "event_type": "rights_issue", "rights_ratio": rights_ratio, "subscription_price": _num(subscription)})
    if not events:
        raise ValueError(f"{exchange} CA record contains no recognized economic event")
    return events


def map_tpex_exright_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    return _map_exright_record(record, exchange="TPEx")


def map_twse_exright_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Map TWSE TWT46U/T48-style official ex-right/ex-dividend fields."""
    return _map_exright_record(record, exchange="TWSE")
