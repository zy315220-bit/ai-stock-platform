from __future__ import annotations

from app.services.sme_liquidity import (
    LiquidityProfile,
    Payable,
    Receivable,
    forecast_liquidity,
)


def sample_profile(**overrides: object) -> LiquidityProfile:
    values = {
        "name": "宏昇精密",
        "industry": "出口製造",
        "description": "test",
        "current_cash": 4_200_000,
        "safety_cash_floor": 1_200_000,
        "baseline_daily_inflow": 92_000,
        "daily_inflow_volatility": 38_000,
        "fixed_daily_outflow": 82_000,
        "payroll_amount": 920_000,
        "payroll_every_days": 30,
        "receivables": (
            Receivable(
                amount=2_100_000,
                due_day=28,
                delay_mean_days=11,
                delay_std_days=8,
                default_probability=0.02,
            ),
            Receivable(
                amount=1_450_000,
                due_day=52,
                delay_mean_days=7,
                delay_std_days=6,
                default_probability=0.01,
            ),
        ),
        "payables": (
            Payable(amount=1_350_000, due_day=42),
            Payable(amount=1_100_000, due_day=73),
        ),
        "fx_receivable_share": 0.55,
    }
    values.update(overrides)
    return LiquidityProfile(**values)


def horizon(result: dict[str, object], days: int) -> dict[str, object]:
    return next(
        row
        for row in result["horizons"]  # type: ignore[index]
        if row["horizon_days"] == days
    )


def stress(result: dict[str, object], name: str) -> dict[str, object]:
    return next(
        row
        for row in result["stress_tests"]  # type: ignore[index]
        if row["stress"] == name
    )


def test_forecast_is_deterministic_for_same_seed() -> None:
    profile = sample_profile()
    first = forecast_liquidity(profile, simulations=1000, seed=42)
    second = forecast_liquidity(profile, simulations=1000, seed=42)
    assert first == second


def test_engine_contract_and_horizons() -> None:
    result = forecast_liquidity(sample_profile(), simulations=1000, seed=7)

    engine = result["engine"]
    assert engine["version"] == "sme-liquidity-monte-carlo-v2"  # type: ignore[index]
    assert engine["assumptions"]["day0_floor_breach_included"] is True  # type: ignore[index]
    assert (
        engine["assumptions"]["nonnegative_inflow_distribution"]  # type: ignore[index]
        == "lognormal_mean_std_calibrated"
    )

    horizons = result["horizons"]
    assert [row["horizon_days"] for row in horizons] == [30, 60, 90]  # type: ignore[index]
    assert all(
        0 <= row["shortfall_probability"] <= 1  # type: ignore[index]
        for row in horizons
    )


def test_quantiles_and_wilson_interval_are_ordered() -> None:
    result = forecast_liquidity(sample_profile(), simulations=1000, seed=8)

    for row in result["horizons"]:  # type: ignore[index]
        assert row["ending_cash_p10"] <= row["ending_cash_p50"] <= row["ending_cash_p90"]
        assert (
            row["shortfall_probability_ci95_lower"]
            <= row["shortfall_probability"]
            <= row["shortfall_probability_ci95_upper"]
        )


def test_zero_breaches_are_not_presented_as_certain_zero() -> None:
    profile = sample_profile(
        current_cash=10_000_000,
        safety_cash_floor=100_000,
        fixed_daily_outflow=1_000,
        payroll_amount=0,
        payables=(),
        receivables=(),
    )
    result = forecast_liquidity(profile, simulations=1000, seed=9)
    h90 = horizon(result, 90)

    assert h90["shortfall_breach_count"] == 0
    assert h90["shortfall_probability"] == 0
    assert h90["shortfall_probability_ci95_upper"] > 0


def test_day_zero_breach_is_counted_immediately() -> None:
    profile = sample_profile(
        current_cash=100_000,
        safety_cash_floor=500_000,
    )
    result = forecast_liquidity(profile, simulations=1000, seed=10)

    h30 = horizon(result, 30)
    assert h30["shortfall_probability"] == 1
    assert h30["shortfall_breach_count"] == 1000
    assert h30["median_first_breach_day"] == 0
    assert result["risk_interpretation"]["status"] == "HIGH_RISK"  # type: ignore[index]


def test_zero_revenue_with_continuing_costs_becomes_high_risk() -> None:
    profile = sample_profile(
        baseline_daily_inflow=0,
        daily_inflow_volatility=0,
        current_cash=1_000_000,
        safety_cash_floor=500_000,
        fixed_daily_outflow=20_000,
        payroll_amount=300_000,
        receivables=(),
    )
    result = forecast_liquidity(profile, simulations=1000, seed=11)

    assert horizon(result, 90)["shortfall_probability"] > 0.5
    assert result["risk_interpretation"]["status"] == "HIGH_RISK"  # type: ignore[index]


def test_huge_payable_raises_near_term_risk() -> None:
    profile = sample_profile(
        current_cash=1_000_000,
        safety_cash_floor=500_000,
        payables=(Payable(amount=10_000_000, due_day=20),),
    )
    result = forecast_liquidity(profile, simulations=1000, seed=12)

    assert horizon(result, 30)["shortfall_probability"] > 0.5


def test_receivable_beyond_90_days_is_not_counted_inside_horizon() -> None:
    base = sample_profile(
        receivables=(),
        payables=(),
        current_cash=1_000_000,
        safety_cash_floor=500_000,
    )
    outside = sample_profile(
        receivables=(
            Receivable(
                amount=50_000_000,
                due_day=180,
                delay_mean_days=0,
                delay_std_days=0,
                default_probability=0,
            ),
        ),
        payables=(),
        current_cash=1_000_000,
        safety_cash_floor=500_000,
    )

    base_result = forecast_liquidity(base, simulations=1000, seed=13)
    outside_result = forecast_liquidity(outside, simulations=1000, seed=13)

    assert (
        horizon(base_result, 90)["ending_cash_p50"]
        == horizon(outside_result, 90)["ending_cash_p50"]
    )


def test_fx_stress_does_not_improve_full_fx_exposure() -> None:
    profile = sample_profile(fx_receivable_share=1.0)
    result = forecast_liquidity(profile, simulations=1000, seed=14)

    assert (
        stress(result, "twd_strengthens_5pct")["ending_cash_p50"]
        <= horizon(result, 90)["ending_cash_p50"]
    )


def test_combined_stress_is_not_safer_than_base_for_sample_profile() -> None:
    result = forecast_liquidity(sample_profile(), simulations=2000, seed=15)

    base_90 = horizon(result, 90)
    combined = stress(result, "combined")

    assert combined["shortfall_probability"] >= base_90["shortfall_probability"]
    assert combined["ending_cash_p50"] <= base_90["ending_cash_p50"]


def test_adjustment_recommendations_do_not_claim_negative_improvement() -> None:
    result = forecast_liquidity(sample_profile(), simulations=1000, seed=16)
    recommendations = result["adjustment_recommendations"]

    assert recommendations
    assert all(
        row["improvement_percentage_points"] >= 0
        for row in recommendations  # type: ignore[union-attr]
    )


def test_guardrails_do_not_claim_credit_decision() -> None:
    result = forecast_liquidity(sample_profile(), simulations=500, seed=17)
    guardrails = result["guardrails"]

    assert guardrails["is_credit_decision"] is False  # type: ignore[index]
    assert guardrails["is_loan_approval"] is False  # type: ignore[index]
    assert guardrails["automatic_product_sale"] is False  # type: ignore[index]
    assert guardrails["human_review_required"] is True  # type: ignore[index]
    assert guardrails["profile_persisted"] is False  # type: ignore[index]


def test_input_fingerprint_is_stable_and_input_sensitive() -> None:
    first = forecast_liquidity(sample_profile(), simulations=1000, seed=99)
    second = forecast_liquidity(sample_profile(), simulations=1000, seed=99)
    changed = forecast_liquidity(
        sample_profile(current_cash=4_300_000),
        simulations=1000,
        seed=99,
    )

    assert first["engine"]["input_fingerprint"] == second["engine"]["input_fingerprint"]  # type: ignore[index]
    assert first["engine"]["input_fingerprint"] != changed["engine"]["input_fingerprint"]  # type: ignore[index]


def test_zero_fx_stress_matches_base_with_common_random_numbers() -> None:
    profile = sample_profile(fx_receivable_share=0.0)
    result = forecast_liquidity(profile, simulations=1000, seed=101)

    base_90 = horizon(result, 90)
    fx = stress(result, "twd_strengthens_5pct")

    assert fx["shortfall_probability"] == base_90["shortfall_probability"]
    assert fx["ending_cash_p50"] == base_90["ending_cash_p50"]


def test_breach_probability_is_non_decreasing_with_horizon() -> None:
    result = forecast_liquidity(sample_profile(), simulations=1500, seed=202)

    p30 = horizon(result, 30)["shortfall_probability"]
    p60 = horizon(result, 60)["shortfall_probability"]
    p90 = horizon(result, 90)["shortfall_probability"]

    assert p30 <= p60 <= p90


def test_each_adjustment_recommendation_has_measurable_improvement() -> None:
    result = forecast_liquidity(sample_profile(), simulations=1500, seed=203)

    for item in result["adjustment_recommendations"]:  # type: ignore[index]
        probability_improved = (
            item["after_shortfall_probability"]
            < item["before_shortfall_probability"]
        )
        cash_improved = item["ending_cash_p50_change"] > 0
        assert probability_improved or cash_improved
