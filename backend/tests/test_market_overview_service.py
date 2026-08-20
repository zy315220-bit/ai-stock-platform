from app.services.market_overview_service import build_market_overview


def test_market_overview_combines_official_market_rows() -> None:
    result = build_market_overview(
        twse_indices=[
            {
                "日期": "1150819",
                "指數": "發行量加權股價指數",
                "收盤指數": "24,500.50",
                "漲跌": "+",
                "漲跌點數": "120.20",
                "漲跌百分比": "0.49",
            },
            {
                "日期": "1150819",
                "指數": "半導體類指數",
                "收盤指數": "800.00",
                "漲跌": "+",
                "漲跌點數": "10.00",
                "漲跌百分比": "1.25",
            },
            {
                "日期": "1150819",
                "指數": "航運類指數",
                "收盤指數": "200.00",
                "漲跌": "-",
                "漲跌點數": "4.00",
                "漲跌百分比": "-2.00",
            },
        ],
        twse_quotes=[
            {"Code": "2330", "Change": "5", "TradeValue": "2000000000"},
            {"Code": "2317", "Change": "-2", "TradeValue": "1000000000"},
            {"Code": "0050", "Change": "1", "TradeValue": "9000000000"},
        ],
        tpex_indices=[
            {
                "Date": "20260819",
                "Close": "300",
                "Change": "3",
            }
        ],
        tpex_quotes=[
            {
                "SecuritiesCompanyCode": "6488",
                "Change": "+1.5",
                "TransactionAmount": "500000000",
            },
            {
                "SecuritiesCompanyCode": "00679B",
                "Change": "+0.1",
                "TransactionAmount": "8000000000",
            },
        ],
    )

    assert result["indices"]["twse"]["close"] == 24500.5
    assert result["indices"]["tpex"]["change_percent"] == 1.01
    assert result["market"]["advancing"] == 2
    assert result["market"]["declining"] == 1
    assert result["market"]["turnover_billion"] == 3.5
    assert result["sectors"][0]["name"] == "半導體"
    assert result["sectors"][1]["name"] == "航運"
    assert result["updated_at"] == "2026-08-19"


def test_market_overview_marks_mismatched_exchange_dates() -> None:
    result = build_market_overview(
        twse_indices=[
            {
                "日期": "1150819",
                "指數": "發行量加權股價指數",
                "收盤指數": "24500",
                "漲跌": "-",
                "漲跌點數": "100",
                "漲跌百分比": "-0.41",
            }
        ],
        twse_quotes=[],
        tpex_indices=[
            {"Date": "20260820", "Close": "300", "Change": "2"}
        ],
        tpex_quotes=[],
    )

    assert result["dates_aligned"] is False
    assert result["source_dates"] == ["2026-08-19", "2026-08-20"]
    assert result["indices"]["twse"]["change"] == -100
