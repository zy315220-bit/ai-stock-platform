import math
import pytest

from app.services.corporate_action_ledger import (
    CorporateActionEvent,
    CorporateActionType,
    PositionState,
    apply_event,
    apply_resolution,
    portfolio_value,
)
from app.services.corporate_action_metadata import CorporateActionResolution, ResolutionType


def assert_close(a, b):
    assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


def test_split_conserves_economic_value_when_price_resets():
    before = PositionState(shares=100, cash=1000, total_cost_basis=10000, stock_code="TEST")
    after = apply_event(before, CorporateActionEvent(CorporateActionType.SPLIT, "2026-01-02", ratio=4))
    assert after.shares == 400
    assert after.total_cost_basis == before.total_cost_basis
    assert_close(portfolio_value(before, 100), portfolio_value(after, 25))


def test_stock_dividend_conserves_value_under_theoretical_ex_price():
    before = PositionState(shares=100, cash=0, total_cost_basis=10000)
    after = apply_event(before, CorporateActionEvent(CorporateActionType.STOCK_DIVIDEND, "2026-01-02", ratio=0.1))
    assert_close(after.shares, 110)
    assert_close(portfolio_value(before, 100), portfolio_value(after, 100 / 1.1))


def test_cash_capital_reduction_accounts_for_cash_and_share_reduction():
    before = PositionState(shares=100, cash=0, total_cost_basis=10000)
    event = CorporateActionEvent(CorporateActionType.CASH_CAPITAL_REDUCTION, "2026-01-02", ratio=0.8, cash_per_share=20)
    after = apply_event(before, event)
    assert after.shares == 80
    assert after.cash == 2000
    assert after.total_cost_basis == 8000
    assert_close(portfolio_value(before, 100), portfolio_value(after, 100))


def test_loss_reduction_changes_shares_not_total_cost_basis():
    before = PositionState(shares=100, cash=0, total_cost_basis=10000)
    after = apply_event(before, CorporateActionEvent(CorporateActionType.LOSS_CAPITAL_REDUCTION, "2026-01-02", ratio=0.5))
    assert after.shares == 50
    assert after.total_cost_basis == 10000
    assert after.average_cost == 200


def test_rights_issue_fails_closed_without_disposition_policy():
    state = PositionState(shares=100, cash=0, total_cost_basis=10000)
    event = CorporateActionEvent(CorporateActionType.RIGHTS_ISSUE, "2026-01-02", ratio=0.2, subscription_price=50)
    with pytest.raises(ValueError, match="disposition policy"):
        apply_event(state, event)


def test_cash_buyout_uses_resolution_terms_not_last_close():
    state = PositionState(shares=100, cash=500, total_cost_basis=8000, stock_code="OLD")
    resolution = CorporateActionResolution(stock_code="OLD", event_id="buyout-1", event_type="delisting", announce_date="2025-12-01", effective_date="2026-01-02", source="official", resolution_type=ResolutionType.CASH_BUYOUT, cash_per_share=120, settlement_date="2026-01-10")
    after = apply_resolution(state, resolution)
    assert after.shares == 0
    assert after.cash == 12500
    assert after.terminated is True


def test_stock_swap_preserves_basis_and_changes_security_identity():
    state = PositionState(shares=100, cash=0, total_cost_basis=10000, stock_code="OLD", market="TWSE")
    resolution = CorporateActionResolution(stock_code="OLD", event_id="swap-1", event_type="merger", announce_date="2025-12-01", effective_date="2026-01-02", source="official", resolution_type=ResolutionType.STOCK_SWAP, exchange_ratio=0.5, successor_stock_code="NEW", successor_market="TWSE")
    after = apply_resolution(state, resolution)
    assert after.shares == 50
    assert after.stock_code == "NEW"
    assert after.total_cost_basis == 10000


def test_market_transfer_does_not_liquidate_position():
    state = PositionState(shares=100, cash=0, total_cost_basis=10000, stock_code="TEST", market="TWSE")
    resolution = CorporateActionResolution(stock_code="TEST", event_id="transfer-1", event_type="market_transfer", announce_date="2025-12-01", effective_date="2026-01-02", source="official", resolution_type=ResolutionType.MARKET_TRANSFER, successor_market="TPEx")
    after = apply_resolution(state, resolution)
    assert after.shares == 100
    assert after.market == "TPEx"
    assert after.terminated is False


def test_unknown_delisting_resolution_fails_closed():
    state = PositionState(shares=100, cash=0, total_cost_basis=10000)
    resolution = CorporateActionResolution(stock_code="TEST", event_id="unknown-1", event_type="delisting", announce_date=None, effective_date="2026-01-02", source="official")
    with pytest.raises(ValueError, match="unknown resolution"):
        apply_resolution(state, resolution)
