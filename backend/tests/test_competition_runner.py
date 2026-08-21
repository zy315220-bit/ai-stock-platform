from __future__ import annotations

import math
import sys
import types
import unittest
from datetime import date

import pandas as pd

if "yfinance" not in sys.modules:
    sys.modules["yfinance"] = types.ModuleType("yfinance")

from app.services.competition_runner import (
    COMPETITION_UNIVERSE,
    ROBOT_SPECS,
    SIGNAL_FUNCTIONS,
    _competition_official_months,
    _competition_coverage_is_complete,
    _expected_competition_history_month,
    _prepare_frame,
    _simulate_symbol,
    run_competition_on_frames,
)
from app.services.competition_service import freeze_robot_spec, rank_robot_results


def _synthetic_frame(offset: float) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-08-13", periods=1_500)
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
    def test_history_months_respect_etf_listing_date(self) -> None:
        as_of = date(2026, 8, 20)
        self.assertEqual(_competition_official_months("00878", as_of=as_of), 66)
        self.assertEqual(_competition_official_months("00919", as_of=as_of), 47)

    def test_competition_rejects_partial_recent_history(self) -> None:
        as_of = date(2026, 8, 20)
        self.assertEqual(
            _expected_competition_history_month("0056", as_of=as_of),
            "2021-03",
        )
        self.assertEqual(
            _expected_competition_history_month("00919", as_of=as_of),
            "2022-10",
        )
        self.assertFalse(
            _competition_coverage_is_complete(
                "0056",
                {
                    "start": "2025-06-02",
                    "end": "2026-08-20",
                    "complete_month_coverage": True,
                },
                as_of=as_of,
            )
        )
        self.assertTrue(
            _competition_coverage_is_complete(
                "0056",
                {
                    "start": "2021-03-02",
                    "end": "2026-08-20",
                    "complete_month_coverage": True,
                },
                as_of=as_of,
            )
        )

    def test_unlisted_segment_keeps_symbol_allocation_in_cash(self) -> None:
        prepared = _prepare_frame(_synthetic_frame(0.0))
        result = _simulate_symbol(
            frame=prepared,
            stock_code="00919",
            robot_id="EMA20-TREND-v1",
            segment="backtest",
            start=pd.Timestamp("2019-01-01"),
            end=pd.Timestamp("2019-12-31"),
            initial_capital=25_000,
            commission_rate=0.001425,
            transaction_tax_rate=0.001,
        )

        self.assertFalse(result["data_available"])
        self.assertEqual(result["final_capital"], 25_000)
        self.assertEqual(result["trades"], [])

    def test_robot_rule_fingerprints_are_stable_and_unique(self) -> None:
        self.assertEqual(len(ROBOT_SPECS), 16)
        fingerprints = [
            freeze_robot_spec(spec)["rule_fingerprint"]
            for spec in ROBOT_SPECS
        ]
        self.assertEqual(len(fingerprints), len(ROBOT_SPECS))
        self.assertEqual(len(set(fingerprints)), len(ROBOT_SPECS))
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
        self.assertEqual(len(result["robots"]), len(ROBOT_SPECS))
        self.assertEqual(set(SIGNAL_FUNCTIONS), {spec["robot_id"] for spec in ROBOT_SPECS})
        self.assertEqual(result["fairness"]["initial_capital"], 100_000)
        self.assertEqual(result["fairness"]["capital_per_symbol"], 25_000)
        self.assertEqual(result["requested_history_months"], 60)
        self.assertEqual(result["periods"]["backtest"]["start"], "2021-08-13")
        self.assertEqual(result["periods"]["backtest"]["end"], "2025-08-12")
        self.assertEqual(result["periods"]["forward"]["start"], "2025-08-13")
        self.assertEqual(result["periods"]["forward"]["end"], "2026-08-13")
        self.assertEqual(
            result["fairness"]["market_universe"],
            list(COMPETITION_UNIVERSE),
        )
        self.assertTrue(
            result["ranking"]["primary_metric"].startswith("forward Wilson 95%")
        )
        self.assertEqual(
            [robot["rank"] for robot in result["robots"]],
            list(range(1, len(ROBOT_SPECS) + 1)),
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

    def test_ranking_prioritizes_wilson_win_evidence_over_return(self) -> None:
        shared = {
            "robot_version": "1",
            "rule_fingerprint": "fixed-rule",
            "initial_capital": 100_000,
            "period_start": "2025-08-20",
            "period_end": "2026-08-20",
            "cost_model_id": "same-cost",
            "risk_model_id": "same-risk",
            "market_universe_id": "same-universe",
            "max_drawdown_percent": 5,
        }
        result = rank_robot_results(
            [
                {
                    **shared,
                    "robot_id": "higher-win-evidence",
                    "trade_count": 27,
                    "winning_trade_count": 19,
                    "total_return_percent": 19.24,
                },
                {
                    **shared,
                    "robot_id": "higher-return",
                    "trade_count": 42,
                    "winning_trade_count": 25,
                    "total_return_percent": 22.01,
                },
            ]
        )

        self.assertEqual(
            [row["robot_id"] for row in result["robots"]],
            ["higher-win-evidence", "higher-return"],
        )
        self.assertGreater(
            result["robots"][0]["wilson_lower_percent"],
            result["robots"][1]["wilson_lower_percent"],
        )

    def test_126_session_return_uses_only_current_and_past_closes(self) -> None:
        prepared = _prepare_frame(_synthetic_frame(0.0))
        expected = (
            prepared["Close"].iloc[126]
            / prepared["Close"].iloc[0]
            - 1
        )
        self.assertAlmostEqual(prepared["Return126"].iloc[126], expected)


if __name__ == "__main__":
    unittest.main()
