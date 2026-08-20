from __future__ import annotations

import unittest

import pandas as pd

from app.services.analysis_service import (
    MINIMUM_DAILY_ROWS,
    _download_interactive_daily_history,
)


def _frame(rows: int, source: str = "臺灣證券交易所") -> pd.DataFrame:
    frame = pd.DataFrame({"Close": range(rows)})
    frame.attrs["source"] = source
    return frame


class InteractiveAnalysisHistoryTests(unittest.TestCase):
    def test_partial_official_history_is_refetched_before_analysis(self) -> None:
        calls: list[dict] = []
        responses = [_frame(36), _frame(250)]

        def download_stock(_stock_code: str, **kwargs) -> pd.DataFrame:
            calls.append(kwargs)
            return responses[len(calls) - 1]

        result = _download_interactive_daily_history(download_stock, "8039")

        self.assertEqual(len(result), 250)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0]["prefer_official"])
        self.assertTrue(calls[1]["force_official_refresh"])

    def test_long_history_source_is_used_when_official_retry_stays_short(self) -> None:
        calls: list[dict] = []
        responses = [
            _frame(20),
            _frame(MINIMUM_DAILY_ROWS - 1),
            _frame(240, source="Yahoo Finance"),
        ]

        def download_stock(_stock_code: str, **kwargs) -> pd.DataFrame:
            calls.append(kwargs)
            return responses[len(calls) - 1]

        result = _download_interactive_daily_history(download_stock, "8039")

        self.assertEqual(len(result), 240)
        self.assertEqual(result.attrs["source"], "Yahoo Finance")
        self.assertFalse(calls[2]["prefer_official"])
        self.assertEqual(calls[2]["daily_period"], "1y")


if __name__ == "__main__":
    unittest.main()
