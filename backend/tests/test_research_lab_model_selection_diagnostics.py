from __future__ import annotations

import json

from scripts.summarize_model_selection_evidence import summarize


def _write_payload(tmp_path, stock_code: str, *, pbo: dict, spa: dict) -> None:
    payload = {
        "stock_code": stock_code,
        "result": {
            "model_selection_evidence": {
                "cscv_pbo": pbo,
                "hansen_spa": spa,
                "trial_count_for_deflated_sharpe": 123,
            }
        },
    }
    (tmp_path / f"{stock_code}.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_model_selection_diagnostics_counts_available_pass_and_reasons(tmp_path) -> None:
    _write_payload(
        tmp_path,
        "2330",
        pbo={
            "available": True,
            "overfitting_risk_pass": True,
            "pbo_probability_percent": 12.5,
            "candidate_count": 5,
            "original_candidate_count": 8,
        },
        spa={
            "available": True,
            "method": "Hansen_SPA_consistent_stationary_bootstrap_v2_lrv",
            "studentization": "stationary_bootstrap_long_run_variance",
            "superior_predictive_ability_pass": True,
            "spa_p_value": 0.03,
            "p_values": {"lower": 0.02, "consistent": 0.03, "upper": 0.04},
            "candidate_count": 5,
            "active_candidate_count": 3,
            "observations": 240,
            "best_candidate_id": "candidate-a",
            "best_mean_daily_excess_percent": 0.08,
            "observed_max_studentized_statistic": 2.4,
            "critical_values_5pct": {"consistent": 1.8},
            "required_mean_daily_excess_percent_at_5pct": 0.06,
            "additional_mean_daily_excess_percent_needed_at_5pct": 0.0,
        },
    )
    _write_payload(
        tmp_path,
        "2882",
        pbo={
            "available": False,
            "reason": "CSCV_requires_three_candidates_and_even_slices",
            "candidate_count": 2,
            "original_candidate_count": 8,
        },
        spa={
            "available": False,
            "reason": "SPA_requires_at_least_two_candidate_models",
            "candidate_count": 1,
        },
    )

    diagnostics = summarize(tmp_path)

    assert diagnostics["schema_version"] == 2
    assert diagnostics["symbol_count"] == 2
    assert diagnostics["pbo"]["available_symbol_count"] == 1
    assert diagnostics["pbo"]["pass_symbol_count"] == 1
    assert diagnostics["pbo"]["unavailable_symbol_count"] == 1
    assert diagnostics["pbo"]["unavailable_reasons"] == {
        "CSCV_requires_three_candidates_and_even_slices": 1
    }
    assert diagnostics["spa"]["available_symbol_count"] == 1
    assert diagnostics["spa"]["pass_symbol_count"] == 1
    assert diagnostics["spa"]["unavailable_symbol_count"] == 1
    assert diagnostics["spa"]["unavailable_reasons"] == {
        "SPA_requires_at_least_two_candidate_models": 1
    }
    assert diagnostics["pbo"]["best_by_lowest_pbo_probability"][0][
        "stock_code"
    ] == "2330"
    assert diagnostics["spa"]["best_by_lowest_p_value"][0]["stock_code"] == (
        "2330"
    )
    row = next(row for row in diagnostics["rows"] if row["stock_code"] == "2330")
    assert row["deflated_sharpe_trial_count"] == 123
    assert row["spa"]["studentization"] == "stationary_bootstrap_long_run_variance"
    assert row["spa"]["best_candidate_id"] == "candidate-a"
    assert row["spa"]["p_values"] == {
        "lower": 0.02,
        "consistent": 0.03,
        "upper": 0.04,
    }
    assert row["spa"]["critical_value_5pct_consistent"] == 1.8
    assert row["spa"]["additional_mean_daily_excess_percent_needed_at_5pct"] == 0.0


def test_model_selection_diagnostics_ranks_lowest_pbo_and_spa_first(tmp_path) -> None:
    for stock_code, pbo_probability, spa_p_value in (
        ("0050", 35.0, 0.20),
        ("2330", 15.0, 0.04),
        ("2603", 25.0, 0.10),
    ):
        _write_payload(
            tmp_path,
            stock_code,
            pbo={
                "available": True,
                "overfitting_risk_pass": pbo_probability <= 20.0,
                "pbo_probability_percent": pbo_probability,
                "candidate_count": 5,
                "original_candidate_count": 8,
            },
            spa={
                "available": True,
                "superior_predictive_ability_pass": spa_p_value < 0.05,
                "spa_p_value": spa_p_value,
                "candidate_count": 5,
                "active_candidate_count": 3,
                "observations": 240,
            },
        )

    diagnostics = summarize(tmp_path)

    assert [
        row["stock_code"]
        for row in diagnostics["pbo"]["best_by_lowest_pbo_probability"]
    ] == ["2330", "2603", "0050"]
    assert [
        row["stock_code"]
        for row in diagnostics["spa"]["best_by_lowest_p_value"]
    ] == ["2330", "2603", "0050"]
