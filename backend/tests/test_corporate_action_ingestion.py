import pytest

from app.services.corporate_action_ingestion import normalize_resolution_record, normalize_resolution_records
from app.services.corporate_action_metadata import ResolutionType


def base(**overrides):
    record = {
        "stock_code": "TEST",
        "event_id": "evt-1",
        "event_type": "cash_buyout",
        "announce_date": "2026-01-01",
        "effective_date": "2026-02-01",
        "cash_per_share": "120.5",
    }
    record.update(overrides)
    return record


def test_cash_buyout_normalizes_official_terms():
    event = normalize_resolution_record(base(), source="TWSE")
    assert event.resolution_type == ResolutionType.CASH_BUYOUT
    assert event.cash_per_share == 120.5
    assert event.source == "TWSE"


def test_stock_swap_requires_successor_and_ratio():
    record = base(event_type="stock_swap", cash_per_share=None, exchange_ratio="0.5", successor_stock_code="NEW")
    event = normalize_resolution_record(record, source="TWSE")
    assert event.resolution_type == ResolutionType.STOCK_SWAP
    assert event.exchange_ratio == 0.5
    assert event.successor_stock_code == "NEW"


@pytest.mark.parametrize("event_type", ["mystery", "", "unknown"])
def test_unknown_resolution_fails_closed(event_type):
    with pytest.raises(ValueError, match="unknown resolution"):
        normalize_resolution_record(base(event_type=event_type), source="TWSE")


def test_incomplete_cash_buyout_fails_closed():
    with pytest.raises(ValueError, match="cash_per_share"):
        normalize_resolution_record(base(cash_per_share=None), source="TWSE")


def test_invalid_numeric_field_fails_closed():
    with pytest.raises(ValueError, match="numeric field"):
        normalize_resolution_record(base(cash_per_share="not-a-number"), source="TWSE")


def test_duplicate_event_ids_reject_entire_batch():
    records = [base(), base(stock_code="OTHER")]
    with pytest.raises(ValueError, match="duplicate"):
        normalize_resolution_records(records, source="TWSE")
