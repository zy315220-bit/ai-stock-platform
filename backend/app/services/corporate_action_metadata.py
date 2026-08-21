"""Canonical metadata schema for complex Taiwan corporate actions.

This is the storage contract used by ingestion/database layers.  It deliberately
keeps market lifecycle terms separate from OHLC so delisting, merger, transfer,
and liquidation cannot be guessed from the last traded price.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


SCHEMA_VERSION = "ca-metadata-v1"


class ResolutionType(str, Enum):
    CASH_BUYOUT = "cash_buyout"
    STOCK_SWAP = "stock_swap"
    MARKET_TRANSFER = "market_transfer"
    LIQUIDATION = "liquidation"
    BANKRUPTCY = "bankruptcy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CorporateActionResolution:
    stock_code: str
    event_id: str
    event_type: str
    announce_date: str | None
    effective_date: str
    source: str
    source_revision: str | None = None
    delisting_reason: str | None = None
    resolution_type: ResolutionType = ResolutionType.UNKNOWN
    cash_per_share: float | None = None
    exchange_ratio: float | None = None
    successor_stock_code: str | None = None
    successor_market: str | None = None
    old_market: str | None = None
    settlement_date: str | None = None
    trading_end_date: str | None = None
    settlement_currency: str = "TWD"
    locked_until_date: str | None = None
    notes: str | None = None

    def validate_for_research(self) -> None:
        if not self.stock_code or not self.event_id or not self.effective_date or not self.source:
            raise ValueError("corporate-action metadata missing identity/date/source")
        if self.resolution_type == ResolutionType.CASH_BUYOUT and not (
            self.cash_per_share is not None and self.cash_per_share >= 0
        ):
            raise ValueError("cash buyout requires cash_per_share")
        if self.resolution_type == ResolutionType.STOCK_SWAP and not (
            self.exchange_ratio is not None
            and self.exchange_ratio > 0
            and self.successor_stock_code
        ):
            raise ValueError("stock swap requires exchange_ratio and successor_stock_code")
        if self.resolution_type == ResolutionType.MARKET_TRANSFER and not self.successor_market:
            raise ValueError("market transfer requires successor_market")
        if self.resolution_type in (ResolutionType.LIQUIDATION, ResolutionType.BANKRUPTCY):
            if not self.settlement_date and self.cash_per_share is None:
                raise ValueError("liquidation/bankruptcy requires settlement terms or explicit recovery")
        if self.resolution_type == ResolutionType.UNKNOWN:
            raise ValueError("unknown resolution must fail closed before research/ranking")

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["resolution_type"] = self.resolution_type.value
        record["schema_version"] = SCHEMA_VERSION
        return record


REQUIRED_STORAGE_FIELDS = (
    "schema_version",
    "stock_code",
    "event_id",
    "event_type",
    "announce_date",
    "effective_date",
    "source",
    "source_revision",
    "delisting_reason",
    "resolution_type",
    "cash_per_share",
    "exchange_ratio",
    "successor_stock_code",
    "successor_market",
    "old_market",
    "settlement_date",
    "trading_end_date",
    "settlement_currency",
    "locked_until_date",
    "notes",
)
