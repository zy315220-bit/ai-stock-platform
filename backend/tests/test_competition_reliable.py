from __future__ import annotations

import unittest

from app.services.competition_reliable import _remove_synthetic_segment_end_exit


class CompetitionReliableTests(unittest.TestCase):
    def test_segment_end_exit_becomes_open_position_without_exit_costs(self) -> None:
        result = {
            "trades": [
                {
                    "robot_id": "ema20",
                    "stock_code": "0050",
                    "segment": "test",
                    "entry_date": "2026-08-01",
                    "entry_price": 50.0,
                    "exit_date": "2026-08-15",
                    "exit_price": 55.0,
                    "shares": 100,
                    "profit": 480.0,
                    "entry_reason": "ema20_entry",
                    "exit_reason": "segment_end",
                    "entry_commission": 7.0,
                    "exit_commission": 8.0,
                    "transaction_tax": 12.0,
                    "stop_price": 48.0,
                    "target_price": 58.0,
                },
                {
                    "robot_id": "ema20",
                    "stock_code": "0050",
                    "segment": "test",
                    "entry_date": "2026-07-01",
                    "entry_price": 45.0,
                    "exit_date": "2026-07-10",
                    "exit_price": 47.0,
                    "shares": 100,
                    "profit": 180.0,
                    "exit_reason": "target",
                },
            ],
            "final_capital": 10_480.0,
            "total_commission": 25.0,
            "total_transaction_tax": 20.0,
            "equity_curve": [{"date": "2026-08-15", "equity": 10_480.0}],
        }

        converted = _remove_synthetic_segment_end_exit(result)

        self.assertEqual(len(converted["trades"]), 1)
        self.assertEqual(converted["trades"][0]["exit_reason"], "target")
        self.assertTrue(all(t.get("exit_reason") != "segment_end" for t in converted["trades"]))
        self.assertEqual(len(converted["open_positions"]), 1)
        position = converted["open_positions"][0]
        self.assertEqual(position["valuation"], "mark_to_market")
        self.assertEqual(position["mark_price"], 55.0)
        self.assertEqual(position["market_value"], 5_500.0)
        self.assertEqual(position["unrealized_profit"], 500.0)
        self.assertEqual(converted["final_capital"], 10_500.0)
        self.assertEqual(converted["total_commission"], 17.0)
        self.assertEqual(converted["total_transaction_tax"], 8.0)
        self.assertEqual(converted["equity_curve"][-1]["equity"], 10_500.0)

    def test_completed_trade_is_unchanged_when_no_segment_end_exit_exists(self) -> None:
        trade = {"exit_reason": "stop", "profit": -100.0}
        result = {
            "trades": [trade],
            "final_capital": 9_900.0,
            "total_commission": 10.0,
            "total_transaction_tax": 5.0,
            "equity_curve": [],
        }

        converted = _remove_synthetic_segment_end_exit(result)

        self.assertEqual(converted["trades"], [trade])
        self.assertEqual(converted["open_positions"], [])
        self.assertEqual(converted["final_capital"], 9_900.0)


if __name__ == "__main__":
    unittest.main()
