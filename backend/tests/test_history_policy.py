from __future__ import annotations

import unittest
from datetime import date

from app.services.history_policy import (
    assess_history_coverage,
    default_research_start_date,
    history_policy,
)


class HistoryPolicyTests(unittest.TestCase):
    def test_policy_separates_interactive_and_research_horizons(self) -> None:
        policy = history_policy()
        self.assertEqual(policy["interactive_history_months"], 13)
        self.assertEqual(policy["research_history_months"], 60)
        self.assertEqual(policy["backtest_warmup_months"], 6)
        self.assertEqual(policy["forward_holdout_months"], 12)

    def test_default_start_is_five_calendar_years_earlier(self) -> None:
        self.assertEqual(
            default_research_start_date(date(2026, 8, 20)),
            date(2021, 8, 20),
        )
        self.assertEqual(
            default_research_start_date(date(2024, 2, 29)),
            date(2019, 2, 28),
        )

    def test_less_than_three_years_is_not_long_horizon(self) -> None:
        coverage = assess_history_coverage(available_days=700)
        self.assertFalse(coverage["long_horizon_qualified"])


if __name__ == "__main__":
    unittest.main()
