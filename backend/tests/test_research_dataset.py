from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import research_dataset


class ResearchDatasetTests(unittest.TestCase):
    def tearDown(self) -> None:
        research_dataset.clear_research_dataset_cache()

    @patch("app.services.research_dataset.summarize_universe_coverage")
    @patch("app.services.research_dataset.load_research_frames")
    def test_same_day_reuses_one_long_history_download(self, load_frames, summarize) -> None:
        frames = {"0050": object(), "0056": object(), "00878": object(), "00919": object()}
        sources = {code: "official-test" for code in frames}
        coverage = {code: {"available_days": 1800} for code in frames}
        load_frames.return_value = (frames, sources, coverage)
        summarize.return_value = {"long_horizon_qualified": True, "available_years": 4.93}

        with patch.dict("sys.modules", {"stock": type("StockModule", (), {"download_stock": object()})()}):
            first = research_dataset.load_shared_research_dataset()
            second = research_dataset.load_shared_research_dataset()

        self.assertIs(first, second)
        self.assertEqual(load_frames.call_count, 1)
        self.assertEqual(first["requested_months"], 60)
        self.assertEqual(first["universe_coverage"]["long_horizon_qualified"], True)

    @patch("app.services.research_dataset.summarize_universe_coverage")
    @patch("app.services.research_dataset.load_research_frames")
    def test_cache_clear_forces_fresh_dataset(self, load_frames, summarize) -> None:
        load_frames.return_value = ({}, {}, {})
        summarize.return_value = {"long_horizon_qualified": False}

        with patch.dict("sys.modules", {"stock": type("StockModule", (), {"download_stock": object()})()}):
            research_dataset.load_shared_research_dataset()
            research_dataset.clear_research_dataset_cache()
            research_dataset.load_shared_research_dataset()

        self.assertEqual(load_frames.call_count, 2)


if __name__ == "__main__":
    unittest.main()
