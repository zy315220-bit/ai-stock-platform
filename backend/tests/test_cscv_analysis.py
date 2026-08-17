from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.cscv_analysis import analyze_historical_selection_overfit


class CSCVAnalysisTests(unittest.TestCase):
    @patch("app.services.cscv_analysis.calculate_cscv_pbo")
    @patch("app.services.cscv_analysis.build_historical_performance_matrix")
    def test_real_matrix_flows_directly_into_pbo(self, build_matrix, calculate_pbo) -> None:
        matrix = {
            "schema": "cscv-performance-matrix-v1",
            "metric": "net_total_return_percent",
            "source": "real_strategy_simulation_on_common_history",
            "slice_count": 12,
            "strategy_count": 16,
            "slice_months": 1,
            "market_universe": ["0050", "0056", "00878", "00919"],
            "cost_model_id": "TW-ETF-0.1425-0.1-v1",
            "ready_for_pbo": True,
            "robot_ids": [f"R{i}" for i in range(16)],
            "matrix": [[0.0] * 16 for _ in range(12)],
        }
        pbo = {"method": "CSCV-PBO-v1", "pbo": 0.25, "pbo_percent": 25.0, "split_count": 924}
        build_matrix.return_value = matrix
        calculate_pbo.return_value = pbo

        result = analyze_historical_selection_overfit(
            {"placeholder": object()}, initial_capital=1_000_000.0, slice_months=1, max_slices=12
        )

        build_matrix.assert_called_once_with(
            {"placeholder": object()}, initial_capital=1_000_000.0, slice_months=1, max_slices=12
        )
        calculate_pbo.assert_called_once_with(matrix)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["method"], "CSCV-PBO-v1")
        self.assertEqual(result["slice_count"], 12)
        self.assertEqual(result["strategy_count"], 16)
        self.assertEqual(result["pbo"]["pbo_percent"], 25.0)
        self.assertIs(result["matrix"], matrix)

    @patch("app.services.cscv_analysis.build_historical_performance_matrix")
    def test_matrix_validation_failure_prevents_pbo_claim(self, build_matrix) -> None:
        build_matrix.side_effect = ValueError("insufficient common history for CSCV performance matrix")
        with self.assertRaisesRegex(ValueError, "insufficient common history"):
            analyze_historical_selection_overfit({}, initial_capital=1_000_000.0)


if __name__ == "__main__":
    unittest.main()
