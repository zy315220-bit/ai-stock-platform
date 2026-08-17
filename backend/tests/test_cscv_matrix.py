from __future__ import annotations

import unittest

from app.services.cscv_matrix import PerformanceSlice, build_performance_matrix


class CSCVPerformanceMatrixTests(unittest.TestCase):
    def test_builds_rectangular_matrix_in_frozen_robot_order(self) -> None:
        slices = [
            PerformanceSlice("s1", "2026-01-01", "2026-01-31", {"B": 2.0, "A": 1.0}),
            PerformanceSlice("s2", "2026-02-01", "2026-02-28", {"A": -1.0, "B": 3.0}),
            PerformanceSlice("s3", "2026-03-01", "2026-03-31", {"A": 4.0, "B": 0.5}),
            PerformanceSlice("s4", "2026-04-01", "2026-04-30", {"A": 2.5, "B": -0.5}),
        ]
        result = build_performance_matrix(slices, ["A", "B"])
        self.assertEqual(result["schema"], "cscv-performance-matrix-v1")
        self.assertEqual(result["robot_ids"], ["A", "B"])
        self.assertEqual(result["matrix"], [[1.0, 2.0], [-1.0, 3.0], [4.0, 0.5], [2.5, -0.5]])
        self.assertEqual(result["slice_count"], 4)
        self.assertTrue(result["ready_for_pbo"])

    def test_rejects_missing_strategy_in_any_slice(self) -> None:
        slices = [
            PerformanceSlice("s1", "2026-01-01", "2026-01-31", {"A": 1.0, "B": 2.0}),
            PerformanceSlice("s2", "2026-02-01", "2026-02-28", {"A": 3.0}),
        ]
        with self.assertRaisesRegex(ValueError, "strategy mismatch"):
            build_performance_matrix(slices, ["A", "B"])

    def test_rejects_overlapping_or_out_of_order_slices(self) -> None:
        slices = [
            PerformanceSlice("s1", "2026-02-01", "2026-02-28", {"A": 1.0, "B": 2.0}),
            PerformanceSlice("s2", "2026-02-15", "2026-03-15", {"A": 3.0, "B": 4.0}),
        ]
        with self.assertRaisesRegex(ValueError, "chronological"):
            build_performance_matrix(slices, ["A", "B"])

    def test_two_slices_are_not_presented_as_pbo_ready(self) -> None:
        slices = [
            PerformanceSlice("s1", "2026-01-01", "2026-01-31", {"A": 1.0, "B": 2.0}),
            PerformanceSlice("s2", "2026-02-01", "2026-02-28", {"A": 3.0, "B": 4.0}),
        ]
        result = build_performance_matrix(slices, ["A", "B"])
        self.assertFalse(result["ready_for_pbo"])

    def test_rejects_non_finite_performance(self) -> None:
        slices = [
            PerformanceSlice("s1", "2026-01-01", "2026-01-31", {"A": 1.0, "B": float("nan")}),
            PerformanceSlice("s2", "2026-02-01", "2026-02-28", {"A": 3.0, "B": 4.0}),
        ]
        with self.assertRaisesRegex(ValueError, "non-finite"):
            build_performance_matrix(slices, ["A", "B"])


if __name__ == "__main__":
    unittest.main()
