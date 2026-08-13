from __future__ import annotations

import math
import sys
import types
import unittest

import pandas as pd

if "yfinance" not in sys.modules:
    sys.modules["yfinance"] = types.ModuleType("yfinance")

from app.services.competition_runner import (
    COMPETITION_UNIVERSE,
    ROBOT_SPECS,
    _prepare_frame,
    run_competition_on_frames,
)
from app.services.competition_service import freeze_robot_spec


def _synthetic_frame(offset: float) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-08-13", periods=190)
    prices = [
        50.0 + offset + index * 0.06 + math.sin(index / 4.0) * 2.4
        for index in range(len(dates))
    ]
    return pd.DataFrame(
        {
            "Open": [price * 0.998 for price in prices],
            "High": [price * 1.018 for price in prices],
            "Low": [price * 0.982 for price in prices],
            "Close": prices,
            "Volume": [1_000_000 + (index % 20) * 90_000 for index in range(len(dates))],
        },
        index=dates,
    )


class CompetitionRunnerTests(unittest.TestCase):
    def test_robot_rule_fingerprints_are_stable_and_unique(self) -> None:
        fingerprints = [
            freeze_robot_spec(spec)["rule_fingerprint"]
            for spec in ROBOT_SPECS
        ]
        self.assertEqual(len(fingerprints), 4)
        self.assertEqual(len(set(fingerprints)), 4)
        self.assertEqual(
            fingerprints,
            [
                freeze_robot_spec(spec)["rule_fingerprint"]
                for spec in ROBOT_SPECS
            ],
        )

    def test_competition_runs_all_robots_under_equal_conditions(self) -> None:
        frames = {
            code: _prepare_frame(_synthetic_frame(index * 3.0))
            for index, code in enumerate(COMPETITION_UNIVERSE)
        }
        result = run_competition_on_frames(
            frames,
            initial_capital=100_000,
            sources={code: "synthetic-test" for code in COMPETITION_UNIVERSE},
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["fairness"]["initial_capital"], 100_000)
        self.assertEqual(result["fairness"]["capital_per_symbol"], 25_000)
        self.assertEqual(
            result["fairness"]["market_universe"],
            list(COMPETITION_UNIVERSE),
        )
        self.assertTrue(
            result["ranking"]["primary_metric"].startswith("forward Wilson 95%")
        )
        self.assertEqual(
            [robot["rank"] for robot in result["robots"]],
            [1, 2, 3, 4],
        )

        for robot in result["robots"]:
            self.assertEqual(robot["backtest"]["initial_capital"], 100_000)
            self.assertEqual(robot["forward"]["initial_capital"], 100_000)
            self.assertLessEqual(robot["forward"]["win_rate_percent"], 100)
            self.assertGreaterEqual(robot["forward"]["win_rate_percent"], 0)
            self.assertLessEqual(robot["wilson_lower_percent"], 100)
            self.assertGreaterEqual(robot["wilson_lower_percent"], 0)
            self.assertTrue(robot["rule_fingerprint"])
            for trade in robot["forward"]["trades"]:
                self.assertLessEqual(trade["entry_date"], trade["exit_date"])
                self.assertGreaterEqual(trade["entry_commission"], 0)
                self.assertGreaterEqual(trade["exit_commission"], 0)
                self.assertGreaterEqual(trade["transaction_tax"], 0)


if __name__ == "__main__":
    unittest.main()
