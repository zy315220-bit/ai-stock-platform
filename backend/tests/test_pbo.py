from __future__ import annotations

import unittest

from app.services.pbo import calculate_cscv_pbo


def payload(matrix):
    return {
        "ready_for_pbo": True,
        "robot_ids": ["A", "B", "C", "D"],
        "matrix": matrix,
    }


class PBOTests(unittest.TestCase):
    def test_stable_winner_has_zero_pbo(self) -> None:
        result = calculate_cscv_pbo(payload([
            [4.0, 3.0, 2.0, 1.0],
            [4.1, 3.1, 2.1, 1.1],
            [3.9, 2.9, 1.9, 0.9],
            [4.2, 3.2, 2.2, 1.2],
        ]))
        self.assertEqual(result["split_count"], 6)
        self.assertEqual(result["pbo_percent"], 0.0)
        self.assertEqual(result["selection_counts"]["A"], 6)

    def test_regime_flipping_winners_show_high_overfit_risk(self) -> None:
        result = calculate_cscv_pbo(payload([
            [10.0, 0.0, 2.0, 1.0],
            [10.0, 0.0, 2.0, 1.0],
            [0.0, 10.0, 2.0, 1.0],
            [0.0, 10.0, 2.0, 1.0],
        ]))
        self.assertGreater(result["pbo_percent"], 0.0)
        self.assertGreater(result["overfit_split_count"], 0)

    def test_not_ready_matrix_is_rejected(self) -> None:
        item = payload([[1, 0], [0, 1], [1, 0], [0, 1]])
        item["ready_for_pbo"] = False
        with self.assertRaises(ValueError):
            calculate_cscv_pbo(item)

    def test_non_rectangular_matrix_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            calculate_cscv_pbo(payload([[1, 2, 3, 4], [1, 2], [1, 2, 3, 4], [1, 2, 3, 4]]))

    def test_twelve_slices_generate_expected_number_of_symmetric_splits(self) -> None:
        matrix = [[float(20 - col + (row % 3) / 10) for col in range(4)] for row in range(12)]
        result = calculate_cscv_pbo(payload(matrix))
        # C(12, 6) directional evaluations; complementary pairs are both evaluated.
        self.assertEqual(result["split_count"], 924)


if __name__ == "__main__":
    unittest.main()
