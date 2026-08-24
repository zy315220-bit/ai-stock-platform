from unittest.mock import patch

import pandas as pd

from app.api.competition import (
    _run_daily_competition,
    _run_forced_competition,
    _run_fresh_competition,
    _run_versioned_competition,
)


def frame(dividend: float) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "Open": [10.0, 10.5],
            "High": [10.2, 10.7],
            "Low": [9.8, 10.3],
            "Close": [10.0, 10.5],
            "Volume": [1_000.0, 1_100.0],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )
    result.attrs.update(
        {
            "stock_code": "0050",
            "source": "official-test",
            "price_basis": "latest-unit split-adjusted",
            "corporate_action_validated": True,
            "split_adjustments": [],
            "dividends": [
                {"ex_date": "2026-01-05", "amount": dividend}
            ],
        }
    )
    return result


def run(dividend: float) -> dict:
    with (
        patch(
            "app.api.competition._download_competition_frames",
            return_value=(
                {"0050": frame(dividend)},
                {"0050": "official-test"},
                {"0050": {}},
            ),
        ),
        patch(
            "app.api.competition.run_competition_on_frames",
            return_value={"run_id": "base-run", "status": "completed"},
        ),
    ):
        return _run_fresh_competition(100_000)


def test_fresh_run_id_is_bound_to_dataset_fingerprint() -> None:
    result = run(0.5)
    assert result["legacy_run_id"] == "base-run"
    assert result["run_id"] == f"base-run-{result['dataset_fingerprint'][:8]}"
    assert result["cache_policy"] == "fresh-corporate-action-validated"
    assert result["dataset_manifest"]["0050"]["corporate_action_validated"]


def test_dividend_correction_forces_new_visible_run_identity() -> None:
    before = run(0.5)
    after = run(0.6)
    assert before["dataset_fingerprint"] != after["dataset_fingerprint"]
    assert before["run_id"] != after["run_id"]


def test_same_date_and_catalog_version_reuses_ranking_cache() -> None:
    _run_versioned_competition.cache_clear()
    with patch(
        "app.api.competition._run_fresh_competition",
        return_value={"run_id": "cached-run"},
    ) as fresh:
        first = _run_versioned_competition(100_000, "2026-08-25", "catalog-a")
        second = _run_versioned_competition(100_000, "2026-08-25", "catalog-a")

    assert fresh.call_count == 1
    assert first is second
    assert first["cache_metadata"] == {
        "cache_date": "2026-08-25",
        "corporate_action_static_version": "catalog-a",
        "forced_refresh": False,
    }


def test_date_or_catalog_change_forces_new_full_run() -> None:
    _run_versioned_competition.cache_clear()
    with patch(
        "app.api.competition._run_fresh_competition",
        side_effect=[{"run_id": "one"}, {"run_id": "two"}, {"run_id": "three"}],
    ) as fresh:
        _run_versioned_competition(100_000, "2026-08-25", "catalog-a")
        _run_versioned_competition(100_000, "2026-08-26", "catalog-a")
        _run_versioned_competition(100_000, "2026-08-26", "catalog-b")

    assert fresh.call_count == 3


def test_force_refresh_clears_all_sources_and_replaces_cached_run() -> None:
    _run_versioned_competition.cache_clear()
    with (
        patch("app.api.competition.clear_official_history_cache") as official_clear,
        patch("app.api.competition.clear_corporate_action_cache") as action_clear,
        patch(
            "app.api.competition._run_fresh_competition",
            return_value={"run_id": "forced-run"},
        ) as fresh,
    ):
        result = _run_forced_competition(100_000)
        cached = _run_daily_competition(100_000)

    official_clear.assert_called_once_with()
    action_clear.assert_called_once_with()
    assert fresh.call_count == 1
    assert result["cache_metadata"]["forced_refresh"] is True
    assert cached["cache_metadata"]["forced_refresh"] is False
    assert result["run_id"] == cached["run_id"] == "forced-run"
