from __future__ import annotations

import unittest

from app.services.selection_bias import (
    probability_at_least_one_false_positive,
    selection_bias_diagnostics,
    sidak_per_strategy_alpha,
)


class SelectionBiasTests(unittest.TestCase):
    def test_sixteen_strategy_family_false_positive_risk_is_material(self) -> None:
        probability = probability_at_least_one_false_positive(16, 0.05)
        self.assertAlmostEqual(probability, 1.0 - 0.95**16)
        self.assertGreater(probability, 0.55)

    def test_sidak_adjustment_controls_family_error(self) -> None:
        per_strategy_alpha = sidak_per_strategy_alpha(16, 0.05)
        reconstructed_family_alpha = 1.0 - (1.0 - per_strategy_alpha) ** 16
        self.assertAlmostEqual(reconstructed_family_alpha, 0.05, places=12)
        self.assertLess(per_strategy_alpha, 0.05)

    def test_diagnostics_are_explicitly_not_pbo(self) -> None:
        diagnostics = selection_bias_diagnostics(16, observed_trade_counts=[0, 4, 30, 12])
        self.assertEqual(diagnostics["strategy_count"], 16)
        self.assertEqual(diagnostics["minimum_observed_trades"], 0)
        self.assertEqual(diagnostics["maximum_observed_trades"], 30)
        self.assertEqual(diagnostics["interpretation"], "diagnostic_only_not_pbo")
        self.assertEqual(diagnostics["assumption"], "independent_strategy_tests")
        self.assertIn("不是 PBO", diagnostics["warning"])

    def test_invalid_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            probability_at_least_one_false_positive(-1)
        with self.assertRaises(ValueError):
            sidak_per_strategy_alpha(0)
        with self.assertRaises(ValueError):
            selection_bias_diagnostics(16, observed_trade_counts=[-1])


if __name__ == "__main__":
    unittest.main()
