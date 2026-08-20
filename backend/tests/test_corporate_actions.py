from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from app.services.backtest.benchmark import _calculate_buy_and_hold
from corporate_actions import (
    adjust_dividends_for_splits,
    apply_split_adjustments,
    download_twse_etf_dividends,
    parse_twse_dividend_html,
)


class CorporateActionTests(unittest.TestCase):
    def test_0050_split_removes_non_economic_price_drop(self) -> None:
        frame = pd.DataFrame(
            {
                "Open": [188.0, 47.2],
                "High": [190.0, 48.0],
                "Low": [187.0, 46.8],
                "Close": [188.65, 47.16],
                "Volume": [1_000_000.0, 4_100_000.0],
            },
            index=pd.to_datetime(["2025-06-10", "2025-06-18"]),
        )

        adjusted = apply_split_adjustments(frame, "0050")

        self.assertAlmostEqual(adjusted.iloc[0]["Close"], 47.1625)
        self.assertEqual(adjusted.iloc[0]["Volume"], 4_000_000)
        self.assertEqual(adjusted.iloc[1]["Close"], 47.16)
        self.assertEqual(adjusted.attrs["split_adjustments"][0]["ratio"], 4.0)

    def test_pre_split_dividend_is_normalized_to_latest_unit(self) -> None:
        dividends = [
            {"ex_date": "2025-01-17", "payment_date": "2025-02-20", "amount": 2.7},
            {"ex_date": "2025-07-21", "payment_date": "2025-08-08", "amount": 0.36},
        ]
        splits = [{"effective_date": "2025-06-18", "ratio": 4.0}]

        adjusted = adjust_dividends_for_splits(dividends, splits)

        self.assertAlmostEqual(adjusted[0]["amount"], 0.675)
        self.assertAlmostEqual(adjusted[1]["amount"], 0.36)

    def test_official_dividend_html_parser(self) -> None:
        html = """
        <table><tbody><tr>
          <td>0050</td><td>元大台灣50</td><td>115年07月21日</td>
          <td>115年07月27日</td><td>115年08月10日</td><td>0.6</td>
          <td><a>詳細資料</a></td><td>115</td>
        </tr></tbody></table>
        """

        events = parse_twse_dividend_html(html, "0050")

        self.assertEqual(events[0]["ex_date"], "2026-07-21")
        self.assertEqual(events[0]["payment_date"], "2026-08-10")
        self.assertEqual(events[0]["amount"], 0.6)

    def test_buy_and_hold_total_return_includes_dividends(self) -> None:
        frame = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-01-02", "2025-07-21", "2025-12-31"]),
                "Open": [10.0, 10.0, 10.0],
                "High": [10.0, 10.0, 10.0],
                "Low": [10.0, 10.0, 10.0],
                "Close": [10.0, 10.0, 10.0],
                "Volume": [1_000, 1_000, 1_000],
            }
        )
        frame.attrs["dividends"] = [
            {"ex_date": "2025-07-21", "amount": 1.0}
        ]

        result = _calculate_buy_and_hold(
            frame,
            initial_capital=10_000,
            commission_rate=0.0,
            transaction_tax_rate=0.0,
        )

        self.assertEqual(result["shares"], 1_000)
        self.assertEqual(result["total_dividends"], 1_000)
        self.assertEqual(result["return_percent"], 10.0)
        self.assertEqual(result["return_basis"], "split_adjusted_total_return")

    def test_audited_fallback_survives_twse_page_timeout(self) -> None:
        with patch(
            "corporate_actions._download_twse_etf_dividends_cached",
            side_effect=ValueError("timeout"),
        ):
            events = download_twse_etf_dividends(
                "0050",
                start=pd.Timestamp("2025-01-01"),
                end=pd.Timestamp("2025-12-31"),
            )

        self.assertEqual(
            [(event["ex_date"], event["amount"]) for event in events],
            [("2025-01-17", 2.7), ("2025-07-21", 0.36)],
        )


if __name__ == "__main__":
    unittest.main()
