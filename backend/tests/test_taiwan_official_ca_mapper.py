import pytest

from app.services.taiwan_official_ca_mapper import map_tpex_exright_record, map_twse_exright_record


def test_twse_stock_dividend_ratio_is_not_divided_by_100():
    events = map_twse_exright_record({
        "股票代號": "2330",
        "除權息日期": "2026-07-01",
        "無償配股率": "0.15",
    })
    assert events == [{
        "stock_code": "2330",
        "effective_date": "2026-07-01",
        "source": "TWSE_official",
        "event_type": "stock_dividend",
        "ratio": 1.15,
    }]


def test_tpex_rights_ratio_is_not_divided_by_100():
    events = map_tpex_exright_record({
        "股票代號": "TEST",
        "除權息日期": "2026-07-01",
        "現金增資配股率": "0.2",
        "現金增資認購價": "50",
    })
    assert events[0]["event_type"] == "rights_issue"
    assert events[0]["rights_ratio"] == pytest.approx(0.2)
    assert events[0]["subscription_price"] == 50.0


def test_cash_dividend_preserves_per_share_amount():
    events = map_twse_exright_record({
        "股票代號": "0050",
        "除權息日期": "2026-07-21",
        "現金股利": "0.36",
    })
    assert events[0]["cash_per_share"] == pytest.approx(0.36)


def test_rights_issue_without_subscription_price_fails_closed():
    with pytest.raises(ValueError, match="subscription price"):
        map_twse_exright_record({
            "股票代號": "TEST",
            "除權息日期": "2026-07-01",
            "現金增資配股率": "0.1",
        })


def test_unrecognized_official_record_fails_closed():
    with pytest.raises(ValueError, match="no recognized economic event"):
        map_tpex_exright_record({
            "股票代號": "TEST",
            "除權息日期": "2026-07-01",
        })
