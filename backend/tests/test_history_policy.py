from __future__ import annotations

import unittest

from app.services.history_policy import assess_history_coverage, history_policy


class HistoryPolicyTests(unittest.TestCase):
    def test_policy_separates_chart_ranges_from_research_horizon(self) -> None:
        policy = history_policy()
        self.assertEqual(policy["interactive_chart_ranges"], ["1m", "3m", "6m", "1y", "3y", "5y"])
        self.assertEqual(policy["research_history_months"], 60)
        self.assertEqual(policy["forward_holdout_months"], 1)

    def test_six_month_history_cannot_be_called_long_horizon(self) -> None:
        result = assess_history_coverage(available_days=183)
        self.assertFalse(result["long_horizon_qualified"])
        self.assertEqual(result["status"], "insufficient_for_long_horizon_claim")

    def test_three_year_history_is_acceptable(self) -> None:
        result = assess_history_coverage(available_days=1096)
        self.assertTrue(result["long_horizon_qualified"])
        self.assertEqual(result["status"], "acceptable")

    def test_five_year_history_is_preferred(self) -> None:
        result = assess_history_coverage(available_days=1827)
        self.assertTrue(result["long_horizon_qualified"])
        self.assertEqual(result["status"], "preferred")

    def test_negative_coverage_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-negative"):
            assess_history_coverage(available_days=-1)


if __name__ == "__main__":
    unittest.main()
