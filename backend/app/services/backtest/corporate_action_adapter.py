"""Translate current normalized dataframe metadata into ledger events.

The production feed currently exposes split_adjustments and dividends in frame
attrs. This adapter gives the backtest loop one event schedule now, while future
TWSE metadata ingestion can add reduction/rights/merger events without changing
the execution loop.

Important: split events are NOT emitted when the dataframe price basis is already
split-adjusted. Doing so would double-adjust the economic position.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.corporate_action_ledger import CorporateActionEvent, CorporateActionType
from .corporate_action_execution import events_by_effective_date


def _date(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def ledger_schedule_from_frame(frame: pd.DataFrame) -> dict[str, list[CorporateActionEvent]]:
    events: list[CorporateActionEvent] = []
    price_basis = str(frame.attrs.get("price_basis") or "").lower()

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

    # Existing production frames normalize historical OHLC into latest share
    # units. Applying the same split to portfolio shares would be a second
    # adjustment. Raw-basis feeds may emit split events safely.
    already_split_adjusted = "split-adjusted" in price_basis or "split_adjusted" in price_basis
    if not already_split_adjusted:
        for item in frame.attrs.get("split_adjustments", []) or []:
            if not isinstance(item, dict):
                continue
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
