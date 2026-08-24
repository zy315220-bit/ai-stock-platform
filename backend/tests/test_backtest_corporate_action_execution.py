import math
import pytest

from app.services.backtest.corporate_action_execution import (
    apply_session_corporate_actions,
    events_by_effective_date,
)
from app.services.corporate_action_ledger import CorporateActionEvent, CorporateActionType


def test_split_is_applied_only_on_effective_session():
    schedule = events_by_effective_date([
        CorporateActionEvent(CorporateActionType.SPLIT, "2026-06-18", ratio=4),
    ])
    before = apply_session_corporate_actions(stock_code="0050", date="2026-06-17", shares=100, cash=500, total_cost_basis=10000, schedule=schedule)
    assert before.shares == 100
    on_date = apply_session_corporate_actions(stock_code="0050", date="2026-06-18", shares=100, cash=500, total_cost_basis=10000, schedule=schedule)
    assert on_date.shares == 400
    assert on_date.cash == 500
    assert on_date.total_cost_basis == 10000


def test_cash_dividend_is_applied_before_session_order_execution():
    schedule = events_by_effective_date([
        CorporateActionEvent(CorporateActionType.CASH_DIVIDEND, "2026-07-01", cash_per_share=2.5),
    ])
    state = apply_session_corporate_actions(stock_code="TEST", date="2026-07-01", shares=100, cash=1000, total_cost_basis=8000, schedule=schedule)
    assert state.cash == 1250
    assert state.shares == 100


def test_unknown_rights_accounting_fails_closed_in_execution_bridge():
    schedule = events_by_effective_date([
        CorporateActionEvent(CorporateActionType.RIGHTS_ISSUE, "2026-07-01", ratio=0.2, subscription_price=50),
    ])
    with pytest.raises(ValueError, match="disposition policy"):
        apply_session_corporate_actions(stock_code="TEST", date="2026-07-01", shares=100, cash=1000, total_cost_basis=8000, schedule=schedule)
