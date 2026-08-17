from __future__ import annotations

import math
import unittest
from unittest.mock import patch

import pandas as pd

from app.services.competition_reliable import _remove_synthetic_segment_end_exit, run_competition_on_frames
from app.services.trading_costs import TAIWAN_ETF_COST_MODEL
from app.services import competition_runner as legacy


def _synthetic_frames() -> dict[str, pd.DataFrame]:
    dates = pd.bdate_range(end="2026-08-13", periods=190)
    frames = {}
    for symbol_index, code in enumerate(legacy.COMPETITION_UNIVERSE):
        offset = symbol_index * 3.0
        prices = [50.0 + offset + index * 0.06 + math.sin(index / 4.0) * 2.4 for index in range(len(dates))]
        frame = pd.DataFrame({"Open": [p * 0.998 for p in prices], "High": [p * 1.018 for p in prices], "Low": [p * 0.982 for p in prices], "Close": prices, "Volume": [1_000_000 + (i % 20) * 90_000 for i in range(len(dates))]}, index=dates)
        frames[code] = legacy._prepare_frame(frame)
    return frames


class CompetitionReliableTests(unittest.TestCase):
    def test_segment_end_exit_becomes_open_position_without_exit_costs(self) -> None:
        result = {"trades": [{"robot_id": "ema20", "stock_code": "0050", "segment": "test", "entry_date": "2026-08-01", "entry_price": 50.0, "exit_price": 55.0, "shares": 100, "profit": 480.0, "exit_reason": "segment_end", "entry_commission": 7.0, "exit_commission": 8.0, "transaction_tax": 12.0}], "final_capital": 10_480.0, "total_commission": 25.0, "total_transaction_tax": 20.0, "equity_curve": [{"equity": 10_480.0}]}
        converted = _remove_synthetic_segment_end_exit(result)
        self.assertEqual(converted["trades"], [])
        self.assertEqual(converted["open_positions"][0]["valuation"], "mark_to_market")
        self.assertEqual(converted["open_positions"][0]["unrealized_profit"], 500.0)
        self.assertEqual(converted["final_capital"], 10_500.0)

    def test_completed_trade_is_unchanged_when_no_segment_end_exit_exists(self) -> None:
        trade = {"exit_reason": "stop", "profit": -100.0}
        result = {"trades": [trade], "final_capital": 9_900.0, "total_commission": 10.0, "total_transaction_tax": 5.0, "equity_curve": []}
        converted = _remove_synthetic_segment_end_exit(result)
        self.assertEqual(converted["trades"], [trade])
        self.assertEqual(converted["open_positions"], [])

    @patch("app.services.competition_reliable._simulate_symbol_mark_to_market")
    def test_runner_exposes_cost_and_selection_bias_diagnostics(self, simulate) -> None:
        simulate.return_value = {"stock_code": "0050", "initial_capital": 250_000.0, "final_capital": 250_000.0, "total_return_percent": 0.0, "max_drawdown_percent": 0.0, "trade_count": 0, "winning_trade_count": 0, "win_rate_percent": 0.0, "total_commission": 0.0, "total_transaction_tax": 0.0, "trades": [], "equity_curve": [], "open_positions": []}
        result = run_competition_on_frames(_synthetic_frames(), initial_capital=1_000_000.0)
        self.assertEqual(simulate.call_count, len(legacy.ROBOT_SPECS) * 2 * len(legacy.COMPETITION_UNIVERSE))
        for call in simulate.call_args_list:
            self.assertEqual(call.kwargs["commission_rate"], TAIWAN_ETF_COST_MODEL.commission_rate)
            self.assertEqual(call.kwargs["transaction_tax_rate"], TAIWAN_ETF_COST_MODEL.transaction_tax_rate)
        bias = result["ranking"]["selection_bias"]
        self.assertEqual(bias["strategy_count"], len(legacy.ROBOT_SPECS))
        self.assertEqual(bias["interpretation"], "diagnostic_only_not_pbo")
        self.assertEqual(bias["minimum_observed_trades"], 0)
        self.assertGreater(bias["independence_fwer_percent"], 50.0)
        self.assertEqual(result["fairness"]["cost_model_id"], TAIWAN_ETF_COST_MODEL.model_id)


if __name__ == "__main__":
    unittest.main()
