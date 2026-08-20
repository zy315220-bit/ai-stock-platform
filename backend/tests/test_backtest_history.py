from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.services.backtest.engine import backtest_stock
from indicators import add_indicators as real_add_indicators


class BacktestHistoryTests(unittest.TestCase):
    def test_backtest_requests_warmup_and_preserves_five_year_period(self) -> None:
        dates = pd.bdate_range("2021-01-01", "2026-08-20")
        prices = np.linspace(20, 34, len(dates))
        frame = pd.DataFrame(
            {
                "Open": prices,
                "High": prices + 0.5,
                "Low": prices - 0.5,
                "Close": prices,
                "Volume": np.full(len(dates), 1_000_000),
            },
            index=dates,
        )
        frame.attrs["source"] = "synthetic-official"
        calls: list[dict] = []

        def fake_download(_code: str, **kwargs) -> pd.DataFrame:
            calls.append(kwargs)
            return frame.copy()

        with (
            patch(
                "app.services.backtest.engine.download_stock",
                side_effect=fake_download,
            ),
            patch(
                "app.services.backtest.engine.calculate_score",
                return_value={"total_score": 0},
            ),
        ):
            result = backtest_stock(
                "00878",
                start_date="2021-08-20",
                initial_capital=80_000,
            )

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["prefer_official"])
        self.assertFalse(calls[0]["update_with_intraday"])
        self.assertEqual(calls[0]["official_months"], 66)
        self.assertTrue(calls[0]["include_corporate_actions"])
        self.assertEqual(result["requested_start_date"], "2021-08-20")
        self.assertEqual(result["actual_start_date"], "2021-08-20")
        self.assertEqual(result["actual_end_date"], "2026-08-20")
        self.assertEqual(result["history_coverage"]["available_years"], 5.0)
        self.assertTrue(result["history_coverage"]["long_horizon_qualified"])

    def test_optional_indicator_nan_does_not_shorten_backtest_period(self) -> None:
        dates = pd.bdate_range("2021-01-01", "2026-08-20")
        phase = np.linspace(0, 24 * np.pi, len(dates))
        prices = 27 + np.sin(phase) + np.linspace(0, 5, len(dates))
        frame = pd.DataFrame(
            {
                "Open": prices,
                "High": prices + 0.5,
                "Low": prices - 0.5,
                "Close": prices,
                "Volume": np.full(len(dates), 1_000_000),
            },
            index=dates,
        )

        def indicators_with_optional_nan(data: pd.DataFrame) -> pd.DataFrame:
            enriched = real_add_indicators(data)
            enriched["OptionalDiagnostic"] = np.nan
            return enriched

        with (
            patch(
                "app.services.backtest.engine.download_stock",
                return_value=frame,
            ),
            patch(
                "app.services.backtest.engine.add_indicators",
                side_effect=indicators_with_optional_nan,
            ),
            patch(
                "app.services.backtest.engine.calculate_score",
                return_value={"total_score": 0},
            ),
        ):
            result = backtest_stock(
                "00878",
                start_date="2021-08-20",
                initial_capital=80_000,
            )

        self.assertEqual(result["actual_start_date"], "2021-08-20")
        self.assertEqual(result["actual_end_date"], "2026-08-20")

    def test_strategy_and_benchmark_include_distributions(self) -> None:
        dates = pd.bdate_range("2024-01-02", periods=220)
        prices = np.full(len(dates), 20.0)
        frame = pd.DataFrame(
            {
                "Open": prices,
                "High": prices + 0.2,
                "Low": prices - 0.2,
                "Close": prices,
                "Volume": np.full(len(dates), 1_000_000),
            },
            index=dates,
        )
        ex_date = dates[180].strftime("%Y-%m-%d")
        frame.attrs["dividends"] = [{"ex_date": ex_date, "amount": 1.0}]

        with (
            patch(
                "app.services.backtest.engine.download_stock",
                return_value=frame,
            ),
            patch(
                "app.services.backtest.engine.calculate_score",
                return_value={"total_score": 100},
            ),
        ):
            result = backtest_stock(
                "0050",
                start_date=dates[0].strftime("%Y-%m-%d"),
                initial_capital=10_000,
                commission_rate=0.0,
                transaction_tax_rate=0.0,
            )

        self.assertEqual(result["total_dividends"], 500.0)
        self.assertEqual(result["trades"][0]["dividends"], 500.0)
        self.assertEqual(result["buy_and_hold"]["total_dividends"], 500.0)
        self.assertEqual(result["total_return_percent"], 5.0)


if __name__ == "__main__":
    unittest.main()
