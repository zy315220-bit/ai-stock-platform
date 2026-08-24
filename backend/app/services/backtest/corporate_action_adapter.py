"""Translate current normalized dataframe metadata into ledger events.

The production feed currently exposes split_adjustments and dividends in frame
attrs. This adapter gives the backtest loop one event schedule now, while future
TWSE metadata ingestion can add reduction/rights/merger events without changing
the execution loop.

Important: split events are NOT emitted when the dataframe price basis is already
split-adjusted. Doing so would double-adjust the economic position. Conversely,
we must never assume an unknown basis is raw: if split metadata exists and the
basis cannot be classified, research fails closed instead of guessing.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.corporate_action_ledger import CorporateActionEvent, CorporateActionType
from .corporate_action_execution import events_by_effective_date


_SPLIT_ADJUSTED_BASIS_TOKENS = ("split-adjusted", "split_adjusted")
_RAW_BASIS_TOKENS = ("raw-unadjusted", "raw_unadjusted", "raw-unadjusted-official", "raw_unadjusted_official")


def _date(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _classify_price_basis(value: Any) -> str:
    basis = str(value or "").strip().lower()
    if any(token in basis for token in _SPLIT_ADJUSTED_BASIS_TOKENS):
        return "split_adjusted"
    if any(token in basis for token in _RAW_BASIS_TOKENS):
        return "raw"
    return "unknown"


def ledger_schedule_from_frame(frame: pd.DataFrame) -> dict[str, list[CorporateActionEvent]]:
    events: list[CorporateActionEvent] = []
    price_basis = frame.attrs.get("price_basis")
    basis_class = _classify_price_basis(price_basis)
    split_items = [item for item in (frame.attrs.get("split_adjustments", []) or []) if isinstance(item, dict)]

    # A split-bearing frame with an unknown basis is unsafe. Treating it as raw
    # could double-adjust Yahoo-style normalized prices; treating it as adjusted
    # could omit a real share conversion. Research must stop until provenance is
    # explicit.
    if split_items and basis_class == "unknown":
        raise ValueError(
            "corporate-action price basis is unknown; refusing to apply split metadata "
            f"(price_basis={price_basis!r})"
        )

    # Dividends are cash flows even when OHLC is split-adjusted. They are emitted
    # exactly once here so the engine no longer needs a second dividend path.
    for item in frame.attrs.get("dividends", []) or []:
        if not isinstance(item, dict):
            continue
        amount = item.get("amount", item.get("dividend", item.get("cash_dividend")))
        date = item.get("ex_date", item.get("date"))
        if date is None or amount is None:
            continue
        amount = float(amount)
        if amount <= 0:
            continue
        events.append(CorporateActionEvent(
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_date=_date(date),
            cash_per_share=amount,
            source=str(item.get("source") or frame.attrs.get("dividend_source") or "frame_metadata"),
            announce_date=str(item.get("announce_date")) if item.get("announce_date") else None,
        ))

    # Only an explicitly raw feed may emit split events. Split-adjusted feeds
    # already express historical OHLC in the normalized share unit.
    if basis_class == "raw":
        for item in split_items:
            ratio = item.get("ratio")
            date = item.get("adjustment_date", item.get("effective_date", item.get("date")))
            if date is None or ratio is None:
                continue
            ratio = float(ratio)
            if ratio <= 0:
                continue
            events.append(CorporateActionEvent(
                event_type=(CorporateActionType.SPLIT if ratio >= 1 else CorporateActionType.REVERSE_SPLIT),
                effective_date=_date(date),
                ratio=ratio,
                source=str(item.get("source") or "frame_metadata"),
                announce_date=str(item.get("announce_date")) if item.get("announce_date") else None,
            ))

    return events_by_effective_date(events)
