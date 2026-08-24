from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from stock import (
    _clean_ohlcv,
    _download_yfinance,
    _normalize_datetime_index,
    _normalize_price_basis,
)


class StockPriceBasisTests(unittest.TestCase):
    def _frame(self) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "Open": [47.0, 47.2],
                "High": [47.5, 48.0],
                "Low": [46.8, 46.9],
                "Close": [47.1625, 47.16],
                "Volume": [4_000_000.0, 4_100_000.0],
            },
            index=pd.to_datetime(["2025-06-10", "2025-06-18"]),
        )
        frame.attrs["source"] = "Yahoo Finance"
        frame.attrs["split_adjusted"] = True
        frame.attrs["price_basis"] = "yahoo_split_adjusted_close"
        return frame

    def test_yahoo_split_adjusted_frame_is_not_adjusted_again(self) -> None:
        frame = self._frame()
        with patch("stock.apply_split_adjustments") as adjust:
            normalized = _normalize_price_basis(frame, "0050", "Yahoo Finance")
        adjust.assert_not_called()
        pd.testing.assert_frame_equal(frame, normalized)
        self.assertTrue(normalized.attrs["split_adjusted"])

    def test_official_raw_frame_does_use_split_normalizer(self) -> None:
        frame = self._frame()
        frame.attrs.clear()
        expected = frame.copy()
        expected.attrs["split_adjusted"] = True
        with patch("stock.apply_split_adjustments", return_value=expected) as adjust:
            normalized = _normalize_price_basis(frame, "0050", "TWSE")
        adjust.assert_called_once()
        self.assertTrue(normalized.attrs["split_adjusted"])

    def test_cleaning_and_datetime_normalization_preserve_basis_metadata(self) -> None:
        frame = self._frame()
        cleaned = _clean_ohlcv(frame)
        normalized = _normalize_datetime_index(cleaned, remove_timezone=True)
        self.assertEqual(normalized.attrs["source"], "Yahoo Finance")
        self.assertTrue(normalized.attrs["split_adjusted"])
        self.assertEqual(normalized.attrs["price_basis"], "yahoo_split_adjusted_close")

    @patch("stock.requests.get")
    @patch("stock.yf.download", return_value=pd.DataFrame())
    def test_chart_api_recovers_when_yfinance_is_rate_limited(
        self,
        _yfinance_download,
        request_get,
    ) -> None:
        response = request_get.return_value
        response.json.return_value = {
            "chart": {
                "error": None,
                "result": [
                    {
                        "timestamp": [1717376400, 1717462800],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [100.0, 101.0],
                                    "high": [102.0, 103.0],
                                    "low": [99.0, 100.0],
                                    "close": [101.0, 102.0],
                                    "volume": [1_000, 1_100],
                                }
                            ]
                        },
                    }
                ],
            }
        }

        frame = _download_yfinance("0050.TW", "1y", "1d")

        response.raise_for_status.assert_called_once_with()
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.attrs["source"], "Yahoo Finance")
        self.assertEqual(frame.attrs["download_transport"], "chart-api-fallback")
        self.assertEqual(float(frame.iloc[-1]["Close"]), 102.0)

    @patch("stock._download_yahoo_chart")
    @patch("stock.yf.download")
    def test_long_daily_history_prefers_single_chart_request(
        self,
        yfinance_download,
        chart_download,
    ) -> None:
        expected = self._frame()
        expected.attrs["download_transport"] = "chart-api-fallback"
        chart_download.return_value = expected

        result = _download_yfinance("0050.TW", "10y", "1d")

        chart_download.assert_called_once_with("0050.TW", "10y", "1d", False)
        yfinance_download.assert_not_called()
        pd.testing.assert_frame_equal(result, expected)


if __name__ == "__main__":
    unittest.main()
