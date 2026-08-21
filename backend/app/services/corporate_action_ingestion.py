"""Official corporate-action ingestion and normalization contract.

Production research must not infer complex Taiwan corporate actions from OHLC.
Provider/TWSE records are normalized here into canonical metadata before they can
reach the event ledger. Unknown event kinds or incomplete resolution terms fail
closed.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.services.corporate_action_metadata import CorporateActionResolution, ResolutionType


_EVENT_ALIASES = {
    "cash_buyout": ResolutionType.CASH_BUYOUT,
    "privatization": ResolutionType.CASH_BUYOUT,
    "stock_swap": ResolutionType.STOCK_SWAP,
    "merger_exchange": ResolutionType.STOCK_SWAP,
    "market_transfer": ResolutionType.MARKET_TRANSFER,
    "liquidation": ResolutionType.LIQUIDATION,
    "bankruptcy": ResolutionType.BANKRUPTCY,
}


def _text(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _number(record: dict[str, Any], key: str) -> float | None:
    value = record.get(key)
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid corporate-action numeric field: {key}") from exc


def normalize_resolution_record(record: dict[str, Any], *, source: str) -> CorporateActionResolution:
    """Normalize one official lifecycle record; never guess missing terms."""
    raw_type = (_text(record, "resolution_type") or _text(record, "event_type") or "").lower()
    resolution_type = _EVENT_ALIASES.get(raw_type, ResolutionType.UNKNOWN)
    resolution = CorporateActionResolution(
        stock_code=_text(record, "stock_code") or "",
        event_id=_text(record, "event_id") or "",
        event_type=_text(record, "event_type") or raw_type,
        announce_date=_text(record, "announce_date"),
        effective_date=_text(record, "effective_date") or "",
        source=source,
        source_revision=_text(record, "source_revision"),
        delisting_reason=_text(record, "delisting_reason"),
        resolution_type=resolution_type,
        cash_per_share=_number(record, "cash_per_share"),
        exchange_ratio=_number(record, "exchange_ratio"),
        successor_stock_code=_text(record, "successor_stock_code"),
        successor_market=_text(record, "successor_market"),
        old_market=_text(record, "old_market"),
        settlement_date=_text(record, "settlement_date"),
        trading_end_date=_text(record, "trading_end_date"),
        settlement_currency=_text(record, "settlement_currency") or "TWD",
        locked_until_date=_text(record, "locked_until_date"),
        notes=_text(record, "notes"),
    )
    resolution.validate_for_research()
    return resolution


def normalize_resolution_records(records: Iterable[dict[str, Any]], *, source: str) -> list[CorporateActionResolution]:
    """Normalize a batch atomically: any unsafe record rejects the whole batch."""
    normalized = [normalize_resolution_record(record, source=source) for record in records]
    ids = [event.event_id for event in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate corporate-action event_id in official ingestion batch")
    return normalized
