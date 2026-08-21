import pandas as pd
import pytest

from app.services.backtest.corporate_action_adapter import ledger_schedule_from_frame
from app.services.corporate_action_ledger import CorporateActionType


def _frame(price_basis: str | None):
    frame = pd.DataFrame({"Close": [100.0]})
    if price_basis is not None:
        frame.attrs["price_basis"] = price_basis
    frame.attrs["split_adjustments"] = [{
        "effective_date": "2025-06-18",
        "adjustment_date": "2025-06-18",
        "ratio": 4.0,
        "source": "TWSE",
    }]
    frame.attrs["dividends"] = [{
        "ex_date": "2025-07-21",
        "amount": 0.36,
        "source": "TWSE",
    }]
    return frame


def test_split_adjusted_frame_does_not_emit_split_event():
    schedule = ledger_schedule_from_frame(_frame("latest-unit split-adjusted"))
    kinds = [event.event_type for events in schedule.values() for event in events]
    assert CorporateActionType.SPLIT not in kinds
    assert CorporateActionType.CASH_DIVIDEND in kinds


def test_raw_frame_emits_split_event():
    schedule = ledger_schedule_from_frame(_frame("raw-unadjusted"))
    split_events = [event for events in schedule.values() for event in events if event.event_type == CorporateActionType.SPLIT]
    assert len(split_events) == 1
    assert split_events[0].ratio == 4.0


def test_dividend_emitted_once_on_ex_date():
    schedule = ledger_schedule_from_frame(_frame("latest-unit split-adjusted"))
    events = schedule["2025-07-21"]
    dividends = [event for event in events if event.event_type == CorporateActionType.CASH_DIVIDEND]
    assert len(dividends) == 1
    assert dividends[0].cash_per_share == 0.36


@pytest.mark.parametrize("price_basis", [None, "", "mystery-provider-basis"])
def test_split_metadata_with_unknown_basis_fails_closed(price_basis):
    with pytest.raises(ValueError, match="price basis is unknown"):
        ledger_schedule_from_frame(_frame(price_basis))


def test_unknown_basis_without_split_metadata_can_process_dividend():
    frame = _frame(None)
    frame.attrs["split_adjustments"] = []
    schedule = ledger_schedule_from_frame(frame)
    assert len(schedule["2025-07-21"]) == 1
    assert schedule["2025-07-21"][0].event_type == CorporateActionType.CASH_DIVIDEND
