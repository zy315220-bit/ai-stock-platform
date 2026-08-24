"""Map official Taiwan exchange ex-right/ex-dividend records into canonical CA fields.

Exchange sources do not expose rate units identically. TWSE TWT48U presents
allotment rates as ratios used directly by its reference-price formula, whereas
TPEx EDIS S20 documents those fields with unit "%". Canonical event `ratio`
for STOCK_DIVIDEND is the *incremental share ratio* (0.15 means +15% shares),
matching CorporateActionLedger which applies shares * (1 + ratio).
"""
from __future__ import annotations

from typing import Any


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, "", "--"):
            return record[key]
    return None


def _first_item(record: dict[str, Any], *keys: str) -> tuple[str | None, Any]:
    for key in keys:
        if key in record and record[key] not in (None, "", "--"):
            return key, record[key]
    return None, None


def _num(value: Any) -> float:
    if value in (None, "", "--"):
        return 0.0
    return float(str(value).replace(",", "").replace("%", "").strip())


def _canonical_date(value: Any) -> str:
    text = str(value or "").strip().replace("年", "").replace("月", "").replace("日", "")
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) == 7:
        year = int(digits[:3]) + 1911
        month = int(digits[3:5])
        day = int(digits[5:7])
        return f"{year:04d}-{month:02d}-{day:02d}"
    if len(digits) == 8 and int(digits[:4]) >= 1911:
        return f"{int(digits[:4]):04d}-{int(digits[4:6]):02d}-{int(digits[6:8]):02d}"
    try:
        from datetime import date

        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise ValueError(f"invalid official corporate-action date: {value!r}") from error


def _canonical_rate(value: Any, *, source_unit: str) -> float:
    raw = _num(value)
    if raw < 0:
        raise ValueError("corporate-action rate cannot be negative")
    if source_unit == "ratio":
        return raw
    if source_unit == "percent":
        return raw / 100.0
    raise ValueError(f"unsupported rate unit: {source_unit}")


def _rate_from_official_field(
    item: tuple[str | None, Any],
    *,
    exchange: str,
) -> float:
    key, value = item
    if key is None:
        return 0.0
    # TPEx's Chinese table fields are documented/displayed as percentages,
    # while its OpenAPI English fields already contain direct ratios. TWSE
    # TWT48U English and Chinese fields are direct ratios. Unit handling must
    # therefore follow the exact source field, not only the exchange name.
    tpex_percent_fields = {
        "無償配股率",
        "無償增資配股率％",
        "現金增資配股率",
        "現金增資配股率％",
    }
    source_unit = (
        "percent"
        if exchange == "TPEx" and key in tpex_percent_fields
        else "ratio"
    )
    return _canonical_rate(value, source_unit=source_unit)


def _map_exright_record(record: dict[str, Any], *, exchange: str) -> list[dict[str, Any]]:
    code = str(_first(record, "股票代號", "證券代號", "Code", "SecuritiesCompanyCode") or "").strip()
    raw_date = _first(
        record,
        "除權息日期",
        "除權除息日期",
        "資料日期",
        "Date",
        "ExRrightsExDividendDate",
    )
    ex_date = _canonical_date(raw_date) if raw_date not in (None, "") else ""
    if not code or not ex_date:
        raise ValueError(f"{exchange} CA record missing stock code or effective date")

    events: list[dict[str, Any]] = []
    cash = _num(_first(record, "現金股利", "現金股利 NT$", "CashDividend"))
    stock_ratio = _rate_from_official_field(
        _first_item(
            record,
            "無償配股率",
            "無償增資配股率％",
            "股票股利",
            "StockDividendRate",
            "StockDividendRatio",
        ),
        exchange=exchange,
    )
    rights_ratio = _rate_from_official_field(
        _first_item(
            record,
            "現金增資配股率",
            "現金增資配股率％",
            "現金增資",
            "RightsIssueRate",
            "SubscriptionRatio",
            "SubscriptionRatioToNewSharesIssued",
        ),
        exchange=exchange,
    )
    subscription = _first(
        record,
        "現金增資認購價",
        "現金增資認購價(每股)",
        "每股認購價格",
        "SubscriptionPrice",
        "SubscriptionPricePerShare",
    )

    base = {"stock_code": code, "effective_date": ex_date, "source": f"{exchange}_official"}
    if cash > 0:
        events.append({**base, "event_type": "cash_dividend", "cash_per_share": cash})
    if stock_ratio > 0:
        events.append({**base, "event_type": "stock_dividend", "ratio": stock_ratio})
    if rights_ratio > 0:
        if subscription in (None, "", "--"):
            raise ValueError(f"{exchange} rights issue missing official subscription price")
        try:
            subscription_price = _num(subscription)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{exchange} rights issue has invalid official subscription price"
            ) from error
        events.append({
            **base,
            "event_type": "rights_issue",
            "rights_ratio": rights_ratio,
            "subscription_price": subscription_price,
        })
    if not events:
        raise ValueError(f"{exchange} CA record contains no recognized economic event")
    return events


def map_tpex_exright_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Map TPEx table/OpenAPI fields using each field's documented unit."""
    return _map_exright_record(record, exchange="TPEx")


def map_twse_exright_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Map TWSE TWT48U-style rates expressed as direct ratios."""
    return _map_exright_record(record, exchange="TWSE")
