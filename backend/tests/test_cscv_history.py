from __future__ import annotations

import math
import unittest
from unittest.mock import patch

import pandas as pd

from app.services import competition_runner as legacy
from app.services.cscv_history import _month_slices, build_historical_performance_matrix
from app.services.trading_costs import TAIWAN_ETF_COST_MODEL


def _frames(periods: int = 420) -> dict[str, pd.DataFrame]:
    dates = pd.bdate_range(end="2026-08-14", periods=periods)
    output: dict[str, pd.DataFrame] = {}
    for offset, code in enumerate(legacy.COMPETITION_UNIVERSE):
        prices = [50 + offset * 4 + index * 0.03 + math.sin(index / 8) for index in range(periods)]
        output[code] = pd.DataFrame({
            "Open": prices, "High": [p * 1.01 for p in prices], "Low": [p * 0.99 for p in prices],
            "Close": prices, "Volume": [1_000_000] * periods,
        }, index=dates)
    return output


class CSCVHistoryTests(unittest.TestCase):
    def test_month_slices_are_chronological_and_non_overlapping(self) -> None:
        slices = _month_slices(_frames(), max_slices=6)
        self.assertEqual(len(slices), 6)
        for previous, current in zip(slices, slices[1:]):
            self.assertLess(previous[2], current[1])

    @patch("app.services.cscv_history._simulate_symbol_mark_to_market")
    def test_real_runner_fills_slice_by_robot_matrix(self, simulate) -> None:
        simulate.return_value = {
            "stock_code": "0050", "initial_capital": 25_000.0, "final_capital": 25_250.0,
            "total_return_percent": 1.0, "max_drawdown_percent": 0.5, "trade_count": 2,
            "winning_trade_count": 1, "win_rate_percent": 50.0, "total_commission": 10.0,
            "total_transaction_tax": 5.0, "trades": [], "equity_curve": [], "open_positions": [],
        }
        matrix = build_historical_performance_matrix(_frames(), initial_capital=100_000.0, max_slices=6)
        self.assertEqual(matrix["slice_count"], 6)
        self.assertEqual(matrix["strategy_count"], len(legacy.ROBOT_SPECS))
        self.assertEqual(len(matrix["matrix"]), 6)
        self.assertTrue(all(len(row) == len(legacy.ROBOT_SPECS) for row in matrix["matrix"]))
        self.assertTrue(matrix["ready_for_pbo"])
        self.assertEqual(matrix["source"], "real_strategy_simulation_on_common_history")
        expected_calls = 6 * len(legacy.ROBOT_SPECS) * len(legacy.COMPETITION_UNIVERSE)
        self.assertEqual(simulate.call_count, expected_calls)
        for call in simulate.call_args_list:
            self.assertEqual(call.kwargs["segment"], "cscv")
            self.assertEqual(call.kwargs["commission_rate"], TAIWAN_ETF_COST_MODEL.commission_rate)
            self.assertEqual(call.kwargs["transaction_tax_rate"], TAIWAN_ETF_COST_MODEL.transaction_tax_rate)

    def test_insufficient_common_history_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_historical_performance_matrix(_frames(periods=45), max_slices=4)


if __name__ == "__main__":
    unittest.main()
