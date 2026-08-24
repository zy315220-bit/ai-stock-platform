from __future__ import annotations

import unittest
from datetime import date

from official_data import (
    LONG_HISTORY_MONTH_THRESHOLD,
    MAX_MONTH_WORKERS,
    _download_market,
    _month_worker_count,
    _number,
    _roc_date,
    _rows_to_frame,
)


class OfficialDataParsingTests(unittest.TestCase):
    def test_month_download_concurrency_stays_below_exchange_limit(self) -> None:
        self.assertEqual(MAX_MONTH_WORKERS, 5)
        self.assertEqual(LONG_HISTORY_MONTH_THRESHOLD, 24)
        self.assertEqual(_month_worker_count(13), 5)
        self.assertEqual(_month_worker_count(66), 5)

    def test_transient_missing_month_is_retried(self) -> None:
        calls: dict[str, int] = {}

        def flaky_fetcher(_stock_code, month):
            key = month.isoformat()
            calls[key] = calls.get(key, 0) + 1

            if calls[key] == 1:
                raise ValueError("temporary response error")

            frame = _rows_to_frame(
                [["115/08/20", "1,000", "0", "10", "11", "9", "10.5"]],
                volume_multiplier=1,
            )
            return frame, "test"

        frame, name = _download_market(
            "00878",
            [date(2026, 8, 1)],
            flaky_fetcher,
        )

        self.assertEqual(len(frame), 1)
        self.assertEqual(name, "test")
        self.assertEqual(calls["2026-08-01"], 2)

    def test_roc_date_is_converted_to_gregorian_calendar(self) -> None:
        timestamp = _roc_date("115/08/12")
        self.assertIsNotNone(timestamp)
        self.assertEqual(timestamp.strftime("%Y-%m-%d"), "2026-08-12")

    def test_number_handles_commas_and_exchange_prefix(self) -> None:
        self.assertEqual(_number("38,149,440"), 38_149_440)
        self.assertEqual(_number("X49.17"), 49.17)
        self.assertIsNone(_number("--"))

    def test_tpex_volume_is_converted_from_lots_to_shares(self) -> None:
        frame = _rows_to_frame(
            [["115/08/12", "11,057", "10,024,119", "844", "933", "844", "933"]],
            volume_multiplier=1000,
        )
        self.assertEqual(float(frame.iloc[0]["Volume"]), 11_057_000)


if __name__ == "__main__":
    unittest.main()
