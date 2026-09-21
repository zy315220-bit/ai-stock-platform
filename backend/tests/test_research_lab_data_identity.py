from copy import deepcopy
from dataclasses import asdict

import pandas as pd
import pytest

from app.services.backtest.data_identity import economic_frame_identity
from app.services.research_lab.evolution import generate_parameter_candidates
from app.services.research_lab.training_memory import (
    LEGACY_TRAIN_DATA_IDENTITY_SCHEMA,
    TRAIN_DATA_IDENTITY_SCHEMA,
    build_training_memory,
    prepare_daily_candidate_plan,
)


def _frame():
    frame = pd.DataFrame({
        "Date": pd.bdate_range("2020-01-01", periods=65),
        "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
        "Volume": 1_000_000, "EMA20": 100.0,
    })
    frame.attrs.update(
        price_basis="split_adjusted", corporate_action_validated=True,
        dividends=[{"ex_date": "2020-03-02", "amount": 1.0, "source": "official"}],
    )
    return frame


def test_economic_identity_ignores_future_dividends_and_provenance_only_changes():
    original = _frame()
    changed = original.copy()
    changed.attrs["dividends"] = [
        {"ex_date": "2020-03-02", "amount": 1.0, "source": "provider", "payment_date": "2020-04-01"},
        {"ex_date": "2026-09-17", "amount": 99.0, "source": "official"},
    ]
    changed.attrs["dividend_source"] = "another URL"
    assert economic_frame_identity("0056", original) == economic_frame_identity("0056", changed)


@pytest.mark.parametrize("column", ["Close", "Volume", "EMA20"])
def test_real_prices_volume_and_warmup_indicator_changes_invalidate_identity(column):
    original = _frame()
    changed = original.copy()
    changed.loc[0, column] += 1
    assert economic_frame_identity("0056", original) != economic_frame_identity("0056", changed)


def test_in_window_dividend_and_raw_split_changes_invalidate_identity():
    original = _frame()
    dividend = original.copy()
    dividend.attrs["dividends"] = [{"ex_date": "2020-03-02", "amount": 2.0}]
    assert economic_frame_identity("0056", original) != economic_frame_identity("0056", dividend)
    split = original.copy()
    split.attrs.update(price_basis="raw_unadjusted", split_adjustments=[{"effective_date": "2020-03-02", "ratio": 4.0}])
    assert economic_frame_identity("0056", original) != economic_frame_identity("0056", split)


def _result(candidate):
    return {
        "research_run_id": "train-run",
        "research_audit": {"validation_used_during_adaptive_search": False, "holdout_used_during_search": False},
        "rounds": [{"generation": 1, "evaluation_phase": "train", "survivors": [], "evaluated": [{
            "candidate": asdict(candidate), "evaluation_phase": "train", "decision": "KEEP",
            "research_score": 40.0, "reasons": [],
            "validation_metrics": {"data_fingerprint": "frame", "statistical_evidence": {"period_sharpe_ratio": 0.1}},
        }]}],
    }


def test_legacy_identity_bridge_preserves_seen_candidates_and_cumulative_trials():
    grid = generate_parameter_candidates()
    kwargs = dict(stock_code="3037", campaign_id="2026-Q3", train_window=("2020-01-01", "2023-11-24"))
    old = build_training_memory(**kwargs, train_data_identity="legacy-probe", as_of_date="2026-09-20", result=_result(grid[0]), prior_memory=None)
    old["train_data_identity_schema"] = LEGACY_TRAIN_DATA_IDENTITY_SCHEMA
    old_copy = deepcopy(old)
    plan = prepare_daily_candidate_plan(**kwargs, train_data_identity="economic-probe", legacy_train_data_identity="legacy-probe", rotated_grid=grid, prior_memory=old)
    assert plan.audit["prior_memory_loaded"] is True
    assert plan.audit["train_data_identity_verified"] is True
    assert plan.prior_train_trial_sharpes == (0.1,)
    migrated = build_training_memory(**kwargs, train_data_identity="economic-probe", legacy_train_data_identity="legacy-probe", as_of_date="2026-09-21", result=_result(grid[1]), prior_memory=old)
    assert old == old_copy
    assert migrated["train_data_identity_schema"] == TRAIN_DATA_IDENTITY_SCHEMA
    assert migrated["memory_reset_reason"] is None
    assert migrated["lifetime_experiment_count"] == 2
    assert set(old["seen_parameter_signatures"]) <= set(migrated["seen_parameter_signatures"])
    assert migrated["train_trial_period_sharpes"] == [0.1, 0.1]
    assert migrated["identity_schema_bridge"]["verified_by"] == "matching_legacy_probe_on_same_frame"
    wrong = prepare_daily_candidate_plan(**kwargs, train_data_identity="economic-probe", legacy_train_data_identity="different-legacy-probe", rotated_grid=grid, prior_memory=old)
    assert wrong.audit["prior_memory_loaded"] is False
    assert wrong.audit["memory_reset_reason"] == "train_data_revision"
    assert wrong.audit["train_data_identity_verified"] is False


def test_empty_experiment_run_is_visible_in_persisted_progress():
    kwargs = dict(stock_code="3037", campaign_id="2026-Q3", train_window=("2020-01-01", "2023-11-24"), train_data_identity="economic")
    result = _result(generate_parameter_candidates()[0])
    result["rounds"] = []
    first = build_training_memory(**kwargs, as_of_date="2026-09-21", result=result, prior_memory=None)
    second = build_training_memory(**kwargs, as_of_date="2026-09-21", result=result, prior_memory=first)
    assert second["search_state"] == "NO_NEW_EXPERIMENTS"
    assert second["consecutive_no_new_experiment_runs"] == 2
    assert second["last_run_new_experiment_count"] == 0
