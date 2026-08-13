from __future__ import annotations

import unittest

from official_data import _number, _roc_date, _rows_to_frame


class OfficialDataParsingTests(unittest.TestCase):
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
