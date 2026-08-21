"""Corporate-action execution bridge for the production backtest loop.

This adapter keeps the engine migration incremental: current cash/share state is
converted to the canonical ledger state, dated events are applied before the
session's open-order execution, then accounting state is returned to the engine.
Unknown/unsupported events propagate ValueError and therefore fail closed.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.services.corporate_action_ledger import (
    CorporateActionEvent,
    PositionState,
    apply_events,
)


def events_by_effective_date(events: Iterable[CorporateActionEvent]) -> dict[str, list[CorporateActionEvent]]:
    schedule: dict[str, list[CorporateActionEvent]] = defaultdict(list)
    for event in events:
        schedule[str(event.effective_date)].append(event)
    return dict(schedule)


def apply_session_corporate_actions(
    *,
    stock_code: str,
    date: str,
    shares: float,
    cash: float,
    total_cost_basis: float,
    schedule: dict[str, list[CorporateActionEvent]],
) -> PositionState:
    state = PositionState(
        stock_code=stock_code,
        shares=float(shares),
        cash=float(cash),
        total_cost_basis=float(total_cost_basis),
    )
    dated_events = schedule.get(str(date), [])
    if not dated_events or state.shares <= 0:
        return state
    return apply_events(state, dated_events)
