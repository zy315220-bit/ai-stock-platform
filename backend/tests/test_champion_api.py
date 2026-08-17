from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class ChampionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch("app.api.competition.evaluate_champion_gate")
    @patch("app.api.competition.analyze_historical_selection_overfit")
    @patch("app.api.competition.legacy._download_competition_frames")
    @patch("app.api.competition.run_competition")
    def test_champion_endpoint_combines_same_request_evidence(
        self, run_competition, download_frames, analyze_pbo, evaluate_gate
    ) -> None:
        competition = {"run_id": "run-1", "leader": {"robot_id": "R1", "name": "Robot 1"}}
        frames = {"0050": object()}
        sources = {"0050": "official"}
        pbo = {"pbo": {"pbo_percent": 12.5}, "slice_count": 12, "strategy_count": 16}
        champion = {"robot_id": "R1", "qualified": True, "status": "qualified_champion", "policy": "policy"}
        run_competition.return_value = competition
        download_frames.return_value = (frames, sources)
        analyze_pbo.return_value = pbo
        evaluate_gate.return_value = champion

        response = self.client.get("/api/competition/champion?initial_capital=100000&slice_months=1&max_slices=12")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["champion"]["status"], "qualified_champion")
        self.assertEqual(payload["competition_run_id"], "run-1")
        self.assertEqual(payload["pbo_percent"], 12.5)
        self.assertEqual(payload["data_sources"], sources)
        evaluate_gate.assert_called_once_with(competition=competition, pbo_analysis=pbo)

    @patch("app.api.competition.run_competition")
    def test_champion_endpoint_rejects_odd_slice_count_before_work(self, run_competition) -> None:
        response = self.client.get("/api/competition/champion?max_slices=11")
        self.assertEqual(response.status_code, 400)
        run_competition.assert_not_called()

    @patch("app.api.competition.evaluate_champion_gate")
    @patch("app.api.competition.analyze_historical_selection_overfit")
    @patch("app.api.competition.legacy._download_competition_frames")
    @patch("app.api.competition.run_competition")
    def test_champion_gate_validation_failure_does_not_claim_champion(
        self, run_competition, download_frames, analyze_pbo, evaluate_gate
    ) -> None:
        run_competition.return_value = {"run_id": "run-2", "leader": {"robot_id": "R1"}}
        download_frames.return_value = ({"0050": object()}, {"0050": "official"})
        analyze_pbo.return_value = {"pbo": {"pbo_percent": 20.0}, "slice_count": 12, "strategy_count": 16}
        evaluate_gate.side_effect = ValueError("competition leader is missing from PBO matrix")

        response = self.client.get("/api/competition/champion")
        self.assertEqual(response.status_code, 400)
        self.assertIn("missing from PBO matrix", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
