"""Event-driven corporate-action accounting primitives.

Raw market prices and portfolio accounting are separate concerns. Corporate
actions mutate shares/cash/cost basis only on their effective event date.
Complex lifecycle events are resolved from explicit official metadata; unknown
terms fail closed instead of guessing from the last traded price.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
from typing import Iterable

from app.services.corporate_action_metadata import CorporateActionResolution, ResolutionType


class CorporateActionType(str, Enum):
    CASH_DIVIDEND = "cash_dividend"
    STOCK_DIVIDEND = "stock_dividend"
    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    CASH_CAPITAL_REDUCTION = "cash_capital_reduction"
    LOSS_CAPITAL_REDUCTION = "loss_capital_reduction"
    RIGHTS_ISSUE = "rights_issue"
    MERGER_EXCHANGE = "merger_exchange"
    CASH_MERGER = "cash_merger"
    DELISTING = "delisting"


@dataclass(frozen=True)
class CorporateActionEvent:
    event_type: CorporateActionType
    effective_date: str
    ratio: float | None = None
    cash_per_share: float | None = None
    subscription_price: float | None = None
    source: str | None = None
    announce_date: str | None = None


@dataclass(frozen=True)
class PositionState:
    shares: float
    cash: float
    total_cost_basis: float
    stock_code: str | None = None
    market: str | None = None
    locked_until_date: str | None = None
    terminated: bool = False

    @property
    def average_cost(self) -> float:
        return self.total_cost_basis / self.shares if self.shares > 0 else 0.0


def _finite_nonnegative(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def _positive(value: float | None, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} is required")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def apply_event(state: PositionState, event: CorporateActionEvent) -> PositionState:
    shares = _finite_nonnegative(state.shares, "shares")
    cash = _finite_nonnegative(state.cash, "cash")
    basis = _finite_nonnegative(state.total_cost_basis, "total_cost_basis")
    kind = event.event_type
    if shares == 0:
        return state
    if kind == CorporateActionType.CASH_DIVIDEND:
        amount = _finite_nonnegative(event.cash_per_share or 0.0, "cash_per_share")
        return replace(state, cash=cash + shares * amount)
    if kind in (CorporateActionType.SPLIT, CorporateActionType.REVERSE_SPLIT):
        return replace(state, shares=shares * _positive(event.ratio, "ratio"))
    if kind == CorporateActionType.STOCK_DIVIDEND:
        ratio = _finite_nonnegative(event.ratio or 0.0, "ratio")
        return replace(state, shares=shares * (1.0 + ratio))
    if kind == CorporateActionType.CASH_CAPITAL_REDUCTION:
        ratio = _positive(event.ratio, "ratio")
        returned = _finite_nonnegative(event.cash_per_share or 0.0, "cash_per_share") * shares
        return replace(state, shares=shares * ratio, cash=cash + returned,
                       total_cost_basis=max(0.0, basis - returned))
    if kind == CorporateActionType.LOSS_CAPITAL_REDUCTION:
        return replace(state, shares=shares * _positive(event.ratio, "ratio"))
    if kind == CorporateActionType.RIGHTS_ISSUE:
        _positive(event.ratio, "ratio")
        _positive(event.subscription_price, "subscription_price")
        raise ValueError("rights_issue requires an explicit entitlement disposition policy")
    if kind == CorporateActionType.MERGER_EXCHANGE:
        return replace(state, shares=shares * _positive(event.ratio, "ratio"))
    if kind == CorporateActionType.CASH_MERGER:
        proceeds = shares * _positive(event.cash_per_share, "cash_per_share")
        return replace(state, shares=0.0, cash=cash + proceeds, total_cost_basis=0.0, terminated=True)
    if kind == CorporateActionType.DELISTING:
        raise ValueError("delisting requires explicit settlement/termination terms")
    raise ValueError(f"unsupported corporate action: {kind}")


def apply_resolution(state: PositionState, resolution: CorporateActionResolution) -> PositionState:
    """Execute an explicitly sourced delisting/merger/market-transfer resolution."""
    resolution.validate_for_research()
    shares = _finite_nonnegative(state.shares, "shares")
    cash = _finite_nonnegative(state.cash, "cash")

    if resolution.resolution_type == ResolutionType.CASH_BUYOUT:
        proceeds = shares * _finite_nonnegative(resolution.cash_per_share or 0.0, "cash_per_share")
        return replace(state, shares=0.0, cash=cash + proceeds, total_cost_basis=0.0,
                       locked_until_date=resolution.settlement_date, terminated=True)

    if resolution.resolution_type == ResolutionType.STOCK_SWAP:
        ratio = _positive(resolution.exchange_ratio, "exchange_ratio")
        return replace(state, shares=shares * ratio,
                       stock_code=resolution.successor_stock_code,
                       market=resolution.successor_market or state.market,
                       locked_until_date=resolution.locked_until_date)

    if resolution.resolution_type == ResolutionType.MARKET_TRANSFER:
        return replace(state, market=resolution.successor_market,
                       locked_until_date=resolution.locked_until_date)

    if resolution.resolution_type in (ResolutionType.LIQUIDATION, ResolutionType.BANKRUPTCY):
        if resolution.cash_per_share is None:
            # A pending settlement is an illiquid locked asset, not zero and not cash.
            return replace(state, locked_until_date=resolution.settlement_date or resolution.locked_until_date)
        recovery = shares * _finite_nonnegative(resolution.cash_per_share, "cash_per_share")
        return replace(state, shares=0.0, cash=cash + recovery, total_cost_basis=0.0,
                       locked_until_date=resolution.settlement_date, terminated=True)

    raise ValueError("unsupported/unknown resolution must fail closed")


def apply_events(state: PositionState, events: Iterable[CorporateActionEvent]) -> PositionState:
    current = state
    for event in events:
        current = apply_event(current, event)
    return current


def portfolio_value(state: PositionState, raw_price: float) -> float:
    price = _finite_nonnegative(raw_price, "raw_price")
    return state.cash + state.shares * price
