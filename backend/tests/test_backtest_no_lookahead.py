from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from app.services.backtest.engine import backtest_stock


class BacktestNoLookaheadTests(unittest.TestCase):
    def _frame(self) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=70, freq="D")
        frame = pd.DataFrame(
            {
                "Open": [100.0] * 70,
                "High": [101.0] * 70,
                "Low": [99.0] * 70,
                "Close": [100.0] * 70,
                "Volume": [1000.0] * 70,
            },
            index=dates,
        )
        frame.attrs["split_adjusted"] = True
        frame.attrs["dividends"] = []
        return frame

    @patch("app.services.backtest.engine._download_backtest_history")
    @patch("app.services.backtest.engine.add_indicators")
    @patch("app.services.backtest.engine.calculate_score")
    def test_signal_uses_history_through_t_and_executes_at_t_plus_1_open(
        self, score, add_indicators, download
    ) -> None:
        frame = self._frame()
        # Make t+1 open intentionally extreme while keeping OHLC internally
        # valid. This bar must survive the production data-quality filter.
        # The signal may execute at this open, but calculate_score must not see
        # any t+1 information when producing the t signal.
        frame.iloc[61, frame.columns.get_loc("Open")] = 250.0
        frame.iloc[61, frame.columns.get_loc("High")] = 251.0
        download.return_value = frame

        def indicators(df: pd.DataFrame) -> pd.DataFrame:
            out = df.copy()
            out["EMA20"] = 100.0
            out["EMA60"] = 100.0
            out["ATR"] = 1.0
            return out

        add_indicators.side_effect = indicators
        seen_last_dates: list[pd.Timestamp] = []

        def scorer(history: pd.DataFrame):
            seen_last_dates.append(pd.Timestamp(history.iloc[-1]["Date"]))
            return {"total_score": 100.0 if len(seen_last_dates) == 1 else 50.0}

        score.side_effect = scorer
        result = backtest_stock(
            "TEST",
            start_date="2024-01-01",
            end_date="2024-03-10",
            entry_score=75,
            exit_score=60,
            initial_capital=100000,
        )

        self.assertGreaterEqual(len(seen_last_dates), 1)
        self.assertEqual(seen_last_dates[0], frame.index[60])
        self.assertLess(seen_last_dates[0], frame.index[61])
        self.assertGreaterEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["entry_date"], frame.index[61].strftime("%Y-%m-%d"))
        self.assertEqual(result["trades"][0]["entry_price"], 250.0)


if __name__ == "__main__":
    unittest.main()
