from __future__ import annotations

import unittest

from app.services.position_valuation import mark_open_position_at_segment_end


class PositionValuationTests(unittest.TestCase):
    def test_open_position_is_marked_without_fabricated_exit_costs(self) -> None:
        final_equity, position = mark_open_position_at_segment_end(
            cash=1_000.0,
            shares=100,
            close_price=55.0,
            entry_price=50.0,
            entry_date="2026-08-01",
            entry_reason="test_entry",
            entry_total_cost=5_007.125,
            entry_commission=7.125,
            stop_price=48.0,
            target_price=58.0,
        )

        self.assertEqual(final_equity, 6_500.0)
        self.assertIsNotNone(position)
        assert position is not None
        self.assertEqual(position["valuation"], "mark_to_market")
        self.assertEqual(position["shares"], 100)
        self.assertEqual(position["mark_price"], 55.0)
        self.assertEqual(position["market_value"], 5_500.0)
        self.assertEqual(position["unrealized_profit"], 492.88)
        self.assertNotIn("exit_date", position)
        self.assertNotIn("exit_price", position)
        self.assertNotIn("exit_commission", position)
        self.assertNotIn("transaction_tax", position)
        self.assertNotIn("exit_reason", position)

    def test_no_position_returns_cash_and_no_open_position(self) -> None:
        final_equity, position = mark_open_position_at_segment_end(
            cash=12_345.67,
            shares=0,
            close_price=50.0,
            entry_price=None,
            entry_date=None,
            entry_reason="",
            entry_total_cost=0.0,
            entry_commission=0.0,
            stop_price=None,
            target_price=None,
        )
        self.assertEqual(final_equity, 12_345.67)
        self.assertIsNone(position)

    def test_invalid_mark_price_is_rejected_for_open_holding(self) -> None:
        with self.assertRaisesRegex(ValueError, "close_price must be positive"):
            mark_open_position_at_segment_end(
                cash=0.0,
                shares=10,
                close_price=0.0,
                entry_price=10.0,
                entry_date="2026-08-01",
                entry_reason="test",
                entry_total_cost=100.0,
                entry_commission=0.0,
                stop_price=9.0,
                target_price=12.0,
            )


if __name__ == "__main__":
    unittest.main()
