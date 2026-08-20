from __future__ import annotations

import unittest

import pandas as pd

from app.services.research_history import (
    frame_coverage,
    load_research_frames,
    summarize_universe_coverage,
)


class ResearchHistoryTests(unittest.TestCase):
    def test_loader_requests_sixty_official_months(self) -> None:
        calls: list[tuple[str, dict]] = []

        def downloader(code: str, **kwargs) -> pd.DataFrame:
            calls.append((code, kwargs))
            frame = pd.DataFrame(
                {"Close": [1.0, 2.0]},
                index=pd.to_datetime(["2021-08-17", "2026-08-17"]),
            )
            frame.attrs["source"] = "official-test"
            return frame

        frames, sources, coverage = load_research_frames(
            ("0050", "0056"),
            downloader=downloader,
            prepare=lambda frame: frame,
        )

        self.assertEqual(set(frames), {"0050", "0056"})
        self.assertEqual(sources["0050"], "official-test")
        self.assertEqual(len(calls), 2)
        for _, kwargs in calls:
            self.assertTrue(kwargs["prefer_official"])
            self.assertFalse(kwargs["update_with_intraday"])
            self.assertEqual(kwargs["official_months"], 60)
        self.assertTrue(coverage["0050"]["long_horizon_qualified"])

    def test_coverage_reports_actual_dates_not_requested_dates(self) -> None:
        frame = pd.DataFrame(
            {"Close": [1.0, 2.0]},
            index=pd.to_datetime(["2024-01-10", "2026-08-17"]),
        )
        result = frame_coverage(frame)
        self.assertEqual(result["start"], "2024-01-10")
        self.assertEqual(result["end"], "2026-08-17")
        self.assertFalse(result["long_horizon_qualified"])

    def test_universe_claim_is_limited_by_shortest_symbol_history(self) -> None:
        coverage = {
            "0050": frame_coverage(pd.DataFrame({"Close": [1, 2]}, index=pd.to_datetime(["2021-08-17", "2026-08-17"]))),
            "00919": frame_coverage(pd.DataFrame({"Close": [1, 2]}, index=pd.to_datetime(["2022-09-20", "2026-08-17"]))),
        }
        summary = summarize_universe_coverage(("0050", "00919"), coverage)
        self.assertEqual(summary["limiting_symbol"], "00919")
        self.assertEqual(summary["actual_start"], "2022-09-20")
        self.assertTrue(summary["long_horizon_qualified"])
        self.assertEqual(summary["status"], "acceptable")

    def test_empty_frame_is_never_long_horizon_qualified(self) -> None:
        result = frame_coverage(pd.DataFrame())
        self.assertEqual(result["row_count"], 0)
        self.assertFalse(result["long_horizon_qualified"])


if __name__ == "__main__":
    unittest.main()
