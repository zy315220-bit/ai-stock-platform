from __future__ import annotations

import unittest

from app.services.champion_gate import evaluate_champion_gate


def fixtures(*, qualified: bool = True, trades: int = 30, pbo: float = 20.0, positive: int = 8):
    competition = {
        "leader": {"robot_id": "R1", "name": "Robot 1", "qualified": qualified},
        "ranking": {"minimum_forward_trades_for_champion": 20},
        "robots": [{
            "robot_id": "R1", "name": "Robot 1", "wilson_lower_percent": 55.0,
            "forward": {"trade_count": trades},
        }],
    }
    values = [1.0] * positive + [-1.0] * (12 - positive)
    pbo_analysis = {
        "pbo": {"pbo_percent": pbo},
        "matrix": {"robot_ids": ["R1"], "matrix": [[value] for value in values]},
    }
    return competition, pbo_analysis


class ChampionGateTests(unittest.TestCase):
    def test_requires_both_forward_and_cross_time_gates(self) -> None:
        competition, pbo = fixtures()
        result = evaluate_champion_gate(competition=competition, pbo_analysis=pbo)
        self.assertTrue(result["qualified"])
        self.assertEqual(result["status"], "qualified_champion")
        self.assertTrue(result["forward_sample_gate"]["passed"])
        self.assertTrue(result["cross_time_robustness_gate"]["passed"])

    def test_high_pbo_blocks_champion(self) -> None:
        competition, pbo = fixtures(pbo=40.0)
        result = evaluate_champion_gate(competition=competition, pbo_analysis=pbo)
        self.assertFalse(result["qualified"])
        self.assertFalse(result["cross_time_robustness_gate"]["passed"])

    def test_low_positive_slice_rate_blocks_champion(self) -> None:
        competition, pbo = fixtures(positive=6)
        result = evaluate_champion_gate(competition=competition, pbo_analysis=pbo)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["cross_time_robustness_gate"]["positive_slice_rate_percent"], 50.0)

    def test_forward_sample_failure_blocks_champion_even_when_pbo_is_good(self) -> None:
        competition, pbo = fixtures(qualified=False, trades=10, pbo=5.0, positive=12)
        result = evaluate_champion_gate(competition=competition, pbo_analysis=pbo)
        self.assertFalse(result["qualified"])
        self.assertFalse(result["forward_sample_gate"]["passed"])
        self.assertTrue(result["cross_time_robustness_gate"]["passed"])

    def test_leader_must_exist_in_pbo_matrix(self) -> None:
        competition, pbo = fixtures()
        pbo["matrix"]["robot_ids"] = ["R2"]
        with self.assertRaisesRegex(ValueError, "missing from PBO matrix"):
            evaluate_champion_gate(competition=competition, pbo_analysis=pbo)


if __name__ == "__main__":
    unittest.main()
