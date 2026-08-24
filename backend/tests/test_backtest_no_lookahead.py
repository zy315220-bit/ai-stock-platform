from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from app.services.backtest.engine import (
    InsufficientBacktestHistoryError,
    backtest_stock,
)


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
        frame.attrs.update(
            {
                "stock_code": "TEST",
                "source": "synthetic-test",
                "split_adjusted": True,
                "price_basis": "latest-unit split-adjusted",
                "corporate_action_validated": True,
                "split_adjustments": [],
                "dividends": [],
            }
        )
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
        # Keep the jump below the structural-break gate; this fixture tests
        # look-ahead execution rather than pretending to contain a reverse split.
        frame.iloc[61, frame.columns.get_loc("Open")] = 175.0
        frame.iloc[61, frame.columns.get_loc("High")] = 176.0
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
        self.assertEqual(result["trades"][0]["entry_price"], 175.0)

    @patch("app.services.backtest.engine._download_backtest_history")
    @patch("app.services.backtest.engine.add_indicators")
    @patch("app.services.backtest.engine.calculate_score")
    def test_entry_structures_gate_score_signals_without_future_bars(
        self, score, add_indicators, download
    ) -> None:
        download.return_value = self._frame()
        score.return_value = {"total_score": 100.0}
        indicator_values: dict[str, float] = {}

        def indicators(df: pd.DataFrame) -> pd.DataFrame:
            out = df.copy()
            out["EMA20"] = 100.0
            out["EMA60"] = 99.0
            out["ATR"] = 1.0
            out["RSI"] = indicator_values.get("RSI", 60.0)
            out["Upper"] = indicator_values.get("Upper", 99.0)
            out["VolumeRatio"] = indicator_values.get("VolumeRatio", 1.3)
            return out

        add_indicators.side_effect = indicators
        cases = (
            ("score_and_rsi_momentum", {"RSI": 60.0}, True),
            ("score_and_rsi_momentum", {"RSI": 50.0}, False),
            ("score_and_bollinger_breakout", {"Upper": 99.0}, True),
            ("score_and_bollinger_breakout", {"Upper": 101.0}, False),
            ("score_and_volume_confirmation", {"VolumeRatio": 1.3}, True),
            ("score_and_volume_confirmation", {"VolumeRatio": 1.1}, False),
        )
        for entry_mode, values, should_trade in cases:
            with self.subTest(entry_mode=entry_mode, values=values):
                indicator_values.clear()
                indicator_values.update(values)
                result = backtest_stock(
                    "MODE",
                    start_date="2024-01-01",
                    end_date="2024-03-10",
                    entry_score=75,
                    exit_score=1,
                    initial_capital=100000,
                    entry_mode=entry_mode,
                )
                self.assertEqual(bool(result["trades"]), should_trade)

    def test_unknown_entry_structure_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported entry_mode"):
            backtest_stock(
                "TEST",
                entry_score=75,
                exit_score=55,
                entry_mode="future_magic",
            )

    @patch("app.services.backtest.engine._prepare_stock_data")
    @patch("app.services.backtest.engine._download_backtest_history")
    def test_pre_inception_slice_is_classified_as_insufficient_history(
        self, download, prepare
    ) -> None:
        download.return_value = self._frame()
        prepare.side_effect = ValueError(
            "指定日期範圍內沒有歷史資料：2019-07-01 至 2020-11-11"
        )
        with self.assertRaises(InsufficientBacktestHistoryError):
            backtest_stock(
                "LATE",
                start_date="2019-07-01",
                end_date="2020-11-11",
            )


if __name__ == "__main__":
    unittest.main()
