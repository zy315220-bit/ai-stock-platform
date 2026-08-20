from app.services.market_overview_service import (
    _calendar_dates_from_payload,
    _market_breadth_row_from_payload,
    _price_index_rows_from_payload,
    _turnover_rows_from_calendar_payload,
    build_market_overview,
)


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


def test_tpex_highlight_supplies_index_breadth_and_turnover() -> None:
    highlight = [
        {
            "Date": "1150820",
            "CloseIndex": "389.96",
            "IndexChange": "5.17",
            "PriceRiseCompanyNumbers": "485",
            "PriceDeclineCompanyNumbers": "293",
            "PriceFlatCompanyNumbers": "89",
            "DailyTradingValue": "184302",
        }
    ]
    result = build_market_overview([], [], highlight, highlight)

    assert result["indices"]["tpex"]["close"] == 389.96
    assert result["indices"]["tpex"]["change_percent"] == 1.34
    assert result["market"]["advancing"] == 485
    assert result["market"]["declining"] == 293
    assert result["market"]["turnover_billion"] == 184.3


def test_market_overview_builds_multi_session_sector_ranking() -> None:
    current_indices = [
        {
            "日期": "1150820",
            "指數": "發行量加權股價指數",
            "收盤指數": "1000",
            "漲跌百分比": "1.00",
        },
        {
            "日期": "1150820",
            "指數": "半導體類指數",
            "收盤指數": "220",
            "漲跌百分比": "2.00",
        },
        {
            "日期": "1150820",
            "指數": "航運類指數",
            "收盤指數": "95",
            "漲跌百分比": "-1.00",
        },
    ]
    five_day_indices = [
        {"日期": "1150813", "指數": "發行量加權股價指數", "收盤指數": "980"},
        {"日期": "1150813", "指數": "半導體類指數", "收盤指數": "200"},
        {"日期": "1150813", "指數": "航運類指數", "收盤指數": "100"},
    ]
    twenty_day_indices = [
        {"日期": "1150723", "指數": "發行量加權股價指數", "收盤指數": "950"},
        {"日期": "1150723", "指數": "半導體類指數", "收盤指數": "180"},
        {"日期": "1150723", "指數": "航運類指數", "收盤指數": "90"},
    ]

    result = build_market_overview(
        current_indices,
        [],
        [],
        [],
        sector_history={
            "as_of": "2026-08-20",
            "five_session_start": "2026-08-13",
            "twenty_session_start": "2026-07-23",
            "five_session_rows": five_day_indices,
            "twenty_session_rows": twenty_day_indices,
        },
    )

    semiconductor = next(
        sector for sector in result["sectors"] if sector["name"] == "半導體"
    )
    shipping = next(
        sector for sector in result["sectors"] if sector["name"] == "航運"
    )

    assert result["sector_trend"]["available"] is True
    assert semiconductor["return_5d"] == 10.0
    assert semiconductor["return_20d"] == 22.22
    assert semiconductor["excess_20d"] == 16.96
    assert semiconductor["trend_rank"] == 1
    assert semiconductor["trend_label"] == "持續轉強"
    assert shipping["trend_rank"] == 2


def test_official_history_payload_parsers() -> None:
    calendar_dates = _calendar_dates_from_payload(
        {"data": [["115/08/19", "1"], ["115/08/20", "2"]]}
    )
    rows = _price_index_rows_from_payload(
        {
            "date": "20260820",
            "tables": [
                {
                    "title": "115年08月20日 價格指數(臺灣證券交易所)",
                    "fields": ["指數", "收盤指數", "漲跌百分比(%)"],
                    "data": [["半導體類指數", "1,600", "1.2"]],
                }
            ],
        }
    )

    assert [item.isoformat() for item in calendar_dates] == [
        "2026-08-19",
        "2026-08-20",
    ]
    assert rows[0]["指數"] == "半導體類指數"
    assert rows[0]["日期"] == "2026-08-20"


def test_market_breadth_and_turnover_payload_parsers() -> None:
    breadth = _market_breadth_row_from_payload(
        {
            "date": "20260820",
            "tables": [
                {
                    "title": "漲跌證券數合計",
                    "fields": ["類型", "整體市場", "股票"],
                    "data": [
                        ["上漲(漲停)", "3,000(20)", "480(8)"],
                        ["下跌(跌停)", "2,000(10)", "320(1)"],
                        ["持平", "600", "100"],
                    ],
                }
            ],
        }
    )
    turnover = _turnover_rows_from_calendar_payload(
        {
            "fields": ["日期", "成交金額"],
            "data": [["115/08/20", "1,250,000,000,000"]],
        }
    )

    assert breadth == {
        "date": "2026-08-20",
        "advancing": 480,
        "declining": 320,
        "unchanged": 100,
        "advance_ratio": 60.0,
    }
    assert turnover == [
        {"date": "2026-08-20", "turnover_billion": 1250.0}
    ]


def test_market_overview_adds_multi_day_breadth_volume_and_sector_participation() -> None:
    breadth_rows = [
        {
            "date": f"2026-08-{day:02d}",
            "advancing": 600 if day >= 16 else 450,
            "declining": 400 if day >= 16 else 550,
            "unchanged": 100,
            "advance_ratio": 60.0 if day >= 16 else 45.0,
        }
        for day in range(1, 21)
    ]
    turnover_rows = [
        {
            "date": f"2026-08-{day:02d}",
            "turnover_billion": 1200.0 if day == 20 else 1000.0,
        }
        for day in range(1, 21)
    ]
    result = build_market_overview(
        twse_indices=[
            {
                "日期": "1150820",
                "指數": "發行量加權股價指數",
                "收盤指數": "1100",
                "漲跌百分比": "1.0",
            },
            {
                "日期": "1150820",
                "指數": "半導體類指數",
                "收盤指數": "220",
                "漲跌百分比": "2.0",
            },
        ],
        twse_quotes=[
            {"Code": "2330", "Change": "5", "TradeValue": "300"},
            {"Code": "2303", "Change": "-1", "TradeValue": "100"},
            {"Code": "2454", "Change": "2", "TradeValue": "100"},
        ],
        tpex_indices=[],
        tpex_quotes=[],
        sector_history={
            "as_of": "2026-08-20",
            "five_session_start": "2026-08-13",
            "twenty_session_start": "2026-07-23",
            "five_session_rows": [
                {"日期": "1150813", "指數": "發行量加權股價指數", "收盤指數": "1050"},
                {"日期": "1150813", "指數": "半導體類指數", "收盤指數": "200"},
            ],
            "twenty_session_rows": [
                {"日期": "1150723", "指數": "發行量加權股價指數", "收盤指數": "1000"},
                {"日期": "1150723", "指數": "半導體類指數", "收盤指數": "180"},
            ],
            "market_breadth_rows": breadth_rows,
            "turnover_rows": turnover_rows,
        },
        company_profiles=[
            {"公司代號": "2330", "產業別": "24"},
            {"公司代號": "2303", "產業別": "24"},
            {"公司代號": "2454", "產業別": "24"},
        ],
    )

    semiconductor = result["sectors"][0]
    market_trend = result["market_trend"]

    assert semiconductor["advance_ratio"] == 66.7
    assert semiconductor["advancing"] == 2
    assert semiconductor["declining"] == 1
    assert semiconductor["breadth_label"] == "多數個股同步轉強"
    assert market_trend["breadth_complete"] is True
    assert market_trend["average_advance_ratio_5d"] == 60.0
    assert market_trend["positive_breadth_days_5d"] == 5
    assert market_trend["breadth_label"] == "廣度正在擴張"
    assert market_trend["turnover_ratio_20d"] == 1.19
    assert market_trend["volume_label"] == "上漲且量能放大"
