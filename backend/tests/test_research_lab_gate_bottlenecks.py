from __future__ import annotations

import json

from scripts.summarize_gate_bottlenecks import summarize


def _write_payload(tmp_path, stock_code: str, *, reasons: list[str], pbo: dict, spa: dict, eligible: bool = False) -> None:
    payload = {
        "stock_code": stock_code,
        "result": {
            "promotion_eligibility": {
                "eligible_for_one_shot_holdout": eligible,
                "reasons": reasons,
            },
            "model_selection_evidence": {
                "cscv_pbo": pbo,
                "hansen_spa": spa,
            },
        },
    }
    (tmp_path / f"{stock_code}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_gate_bottlenecks_split_failed_from_unavailable(tmp_path) -> None:
    _write_payload(
        tmp_path,
        "2330",
        reasons=[
            "bull_bear_robustness_failed",
            "cscv_pbo_failed_or_unavailable",
            "hansen_spa_failed_or_unavailable",
        ],
        pbo={"available": True, "overfitting_risk_pass": False},
        spa={"available": False, "superior_predictive_ability_pass": False},
    )
    _write_payload(
        tmp_path,
        "2882",
        reasons=["cscv_pbo_failed_or_unavailable"],
        pbo={"available": False, "overfitting_risk_pass": False},
        spa={"available": True, "superior_predictive_ability_pass": True},
    )

    diagnostics = summarize(tmp_path)

    counts = {
        item["reason"]: item["symbol_count"]
        for item in diagnostics["top_bottlenecks"]
    }
    assert counts["bull_bear_robustness_failed"] == 1
    assert counts["cscv_pbo_failed"] == 1
    assert counts["cscv_pbo_unavailable"] == 1
    assert counts["hansen_spa_unavailable"] == 1
    assert diagnostics["model_selection_state_counts"]["cscv_pbo"] == {
        "failed": 1,
        "unavailable": 1,
    }
    assert diagnostics["model_selection_state_counts"]["hansen_spa"] == {
        "pass": 1,
        "unavailable": 1,
    }


def test_gate_bottlenecks_keep_validation_diagnostics_observation_only(tmp_path) -> None:
    _write_payload(
        tmp_path,
        "0050",
        reasons=[],
        pbo={"available": True, "overfitting_risk_pass": True},
        spa={"available": True, "superior_predictive_ability_pass": True},
        eligible=True,
    )

    diagnostics = summarize(tmp_path)

    assert diagnostics["eligible_symbol_count"] == 1
    assert diagnostics["blocked_symbol_count"] == 0
    assert diagnostics["research_priority_observer"] == []
    assert diagnostics["feedback_policy"].startswith("OBSERVATION_ONLY")
