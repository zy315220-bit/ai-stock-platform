from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from app.services import scanner_service


class ScannerReliabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        scanner_service._cache.update(at=0.0, payload=None)

    def tearDown(self) -> None:
        scanner_service._cache.update(at=0.0, payload=None)

    @patch("app.services.scanner_service.time.sleep")
    @patch("app.services.scanner_service.requests.get")
    def test_fetch_messages_retries_then_succeeds(self, mock_get: Mock, mock_sleep: Mock) -> None:
        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {"msgArray": [{"c": "2330", "z": "1000", "y": "990"}]}
        mock_get.side_effect = [requests.Timeout("first"), requests.Timeout("second"), success]

        messages = scanner_service._fetch_messages()

        self.assertEqual(messages[0]["c"], "2330")
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual([call.kwargs["timeout"] for call in mock_get.call_args_list], [4, 7, 10])
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertIs(scanner_service._cache["payload"], messages)

    @patch("app.services.scanner_service.time.monotonic", return_value=1000.0)
    @patch("app.services.scanner_service.time.sleep")
    @patch("app.services.scanner_service.requests.get")
    def test_fetch_messages_uses_stale_cache_after_all_retries_fail(
        self,
        mock_get: Mock,
        mock_sleep: Mock,
        mock_monotonic: Mock,
    ) -> None:
        stale = [{"c": "0050", "z": "200", "y": "198"}]
        scanner_service._cache.update(at=1.0, payload=stale)
        mock_get.side_effect = requests.Timeout("down")

        messages = scanner_service._fetch_messages()

        self.assertIs(messages, stale)
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertGreater(mock_monotonic.return_value - scanner_service._cache["at"], scanner_service._CACHE_TTL_SECONDS)

    @patch("app.services.scanner_service.time.sleep")
    @patch("app.services.scanner_service.requests.get")
    def test_fetch_messages_raises_clean_error_without_cache(self, mock_get: Mock, mock_sleep: Mock) -> None:
        mock_get.side_effect = requests.Timeout("down")

        with self.assertRaisesRegex(RuntimeError, "每日選股行情來源暫時無法連線"):
            scanner_service._fetch_messages()

        self.assertEqual(mock_get.call_count, 3)

    @patch("app.services.scanner_service.requests.get")
    def test_fresh_cache_skips_network(self, mock_get: Mock) -> None:
        cached = [{"c": "0056", "z": "40", "y": "39.5"}]
        with patch("app.services.scanner_service.time.monotonic", return_value=1000.0):
            scanner_service._cache.update(at=950.0, payload=cached)
            messages = scanner_service._fetch_messages()

        self.assertIs(messages, cached)
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
