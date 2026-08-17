from __future__ import annotations

import unittest

from app.services.competition_service import rank_robot_results, wilson_interval


FAIRNESS = {
    "initial_capital": 1_000_000.0,
    "period_start": "2026-07-01",
    "period_end": "2026-08-01",
    "cost_model_id": "TW-ETF-0.1425-0.1-v1",
    "risk_model_id": "ATR-2R-STOP-4R-TARGET-v1",
    "market_universe_id": "TW-ETF-CORE-4-v1",
}


def _row(robot_id: str, wins: int, trades: int, total_return: float = 0.0, drawdown: float = 0.0):
    return {
        **FAIRNESS,
        "robot_id": robot_id,
        "robot_version": "1",
        "rule_fingerprint": f"fingerprint-{robot_id}",
        "trade_count": trades,
        "winning_trade_count": wins,
        "total_return_percent": total_return,
        "max_drawdown_percent": drawdown,
    }


class CompetitionStatisticsTests(unittest.TestCase):
    def test_wilson_interval_is_conservative_for_tiny_perfect_sample(self) -> None:
        lower, upper = wilson_interval(1, 1)
        self.assertLess(lower, 0.25)
        self.assertEqual(round(upper, 10), 1.0)

    def test_many_supported_wins_beat_one_lucky_perfect_trade(self) -> None:
        result = rank_robot_results([
            _row("LUCKY-ONE", 1, 1, total_return=10.0),
            _row("SUPPORTED", 24, 30, total_return=5.0),
        ])
        ranked = result["robots"]
        self.assertEqual(ranked[0]["robot_id"], "SUPPORTED")
        self.assertGreater(ranked[0]["wilson_lower_percent"], ranked[1]["wilson_lower_percent"])
        self.assertEqual(ranked[1]["raw_win_rate_percent"], 100.0)

    def test_zero_trade_robot_cannot_win_ranking(self) -> None:
        result = rank_robot_results([
            _row("NO-TRADES", 0, 0, total_return=99.0),
            _row("EVIDENCE", 18, 30, total_return=1.0),
        ])
        ranked = result["robots"]
        self.assertEqual(ranked[0]["robot_id"], "EVIDENCE")
        self.assertEqual(ranked[-1]["robot_id"], "NO-TRADES")
        self.assertEqual(ranked[-1]["wilson_lower_percent"], 0.0)

    def test_return_and_drawdown_only_break_statistical_ties(self) -> None:
        result = rank_robot_results([
            _row("LOWER-RETURN", 18, 30, total_return=3.0, drawdown=4.0),
            _row("HIGHER-RETURN", 18, 30, total_return=7.0, drawdown=9.0),
        ])
        ranked = result["robots"]
        self.assertEqual(ranked[0]["robot_id"], "HIGHER-RETURN")
        self.assertEqual(ranked[0]["wilson_lower_percent"], ranked[1]["wilson_lower_percent"])


if __name__ == "__main__":
    unittest.main()
