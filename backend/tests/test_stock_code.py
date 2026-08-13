from __future__ import annotations

import unittest

from app.services.stock_code import (
    base_stock_code,
    normalize_stock_code,
)


class StockCodeValidationTests(unittest.TestCase):
    def test_normalizes_case_and_whitespace(self) -> None:
        self.assertEqual(
            normalize_stock_code(" 6488.two "),
            "6488.TWO",
        )

    def test_removes_supported_market_suffix(self) -> None:
        self.assertEqual(base_stock_code("2330.tw"), "2330")
        self.assertEqual(base_stock_code("6488.TWO"), "6488")

    def test_accepts_alphanumeric_taiwan_security_code(self) -> None:
        self.assertEqual(normalize_stock_code("2881A"), "2881A")

    def test_rejects_invalid_or_unsafe_codes(self) -> None:
        invalid_codes = [
            "",
            "233",
            "ABCDEFG",
            "2330/analysis",
            "2330.TW.",
            "台積電",
        ]

        for code in invalid_codes:
            with self.subTest(code=code):
                with self.assertRaises(ValueError):
                    normalize_stock_code(code)


if __name__ == "__main__":
    unittest.main()
