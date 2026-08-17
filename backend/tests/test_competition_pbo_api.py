from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api.competition import get_competition_pbo


class CompetitionPBOApiTests(unittest.TestCase):
    @patch("app.api.competition.analyze_historical_selection_overfit")
    @patch("app.api.competition.legacy._download_competition_frames")
    def test_pbo_endpoint_returns_analysis_and_data_sources(self, download, analyze) -> None:
        frames = {"0050": object()}
        sources = {"0050": "TWSE official"}
        download.return_value = (frames, sources)
        analyze.return_value = {
            "status": "completed",
            "method": "CSCV-PBO-v1",
            "pbo": {"pbo_percent": 25.0},
        }
        result = asyncio.run(get_competition_pbo(initial_capital=1_000_000.0, slice_months=1, max_slices=12))
        analyze.assert_called_once_with(frames, initial_capital=1_000_000.0, slice_months=1, max_slices=12)
        self.assertEqual(result["method"], "CSCV-PBO-v1")
        self.assertEqual(result["pbo"]["pbo_percent"], 25.0)
        self.assertEqual(result["data_sources"], sources)

    def test_pbo_endpoint_rejects_odd_slice_count(self) -> None:
        with self.assertRaises(HTTPException) as context:
            asyncio.run(get_competition_pbo(initial_capital=1_000_000.0, slice_months=1, max_slices=11))
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("偶數", context.exception.detail)

    @patch("app.api.competition.legacy._download_competition_frames")
    def test_pbo_endpoint_maps_history_validation_to_400(self, download) -> None:
        download.return_value = ({}, {})
        with patch("app.api.competition.analyze_historical_selection_overfit", side_effect=ValueError("insufficient common history")):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(get_competition_pbo(initial_capital=1_000_000.0, slice_months=1, max_slices=12))
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("insufficient common history", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
