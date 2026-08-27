from __future__ import annotations

from app.services.sme_liquidity import LiquidityProfile, Payable, Receivable, forecast_liquidity


def sample_profile() -> LiquidityProfile:
    return LiquidityProfile(
        current_cash=4_200_000,
        safety_cash_floor=1_200_000,
        baseline_daily_inflow=92_000,
        daily_inflow_volatility=38_000,
        fixed_daily_outflow=82_000,
        payroll_amount=920_000,
        payroll_every_days=30,
        receivables=(
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
        payables=(
            Payable(amount=1_350_000, due_day=42),
            Payable(amount=1_100_000, due_day=73),
        ),
        fx_receivable_share=0.55,
    )


def test_forecast_is_deterministic_for_same_seed() -> None:
    profile = sample_profile()
    first = forecast_liquidity(profile, simulations=1000, seed=42)
    second = forecast_liquidity(profile, simulations=1000, seed=42)
    assert first == second


def test_horizons_are_30_60_90_and_probabilities_are_valid() -> None:
    result = forecast_liquidity(sample_profile(), simulations=1000, seed=7)
    horizons = result["horizons"]
    assert [row["horizon_days"] for row in horizons] == [30, 60, 90]
    assert all(0 <= row["shortfall_probability"] <= 1 for row in horizons)


def test_combined_stress_is_not_safer_than_base_for_sample_profile() -> None:
    result = forecast_liquidity(sample_profile(), simulations=2000, seed=99)
    base_90 = next(row for row in result["horizons"] if row["horizon_days"] == 90)
    combined = next(row for row in result["stress_tests"] if row["stress"] == "combined")

    assert combined["shortfall_probability"] >= base_90["shortfall_probability"]
    assert combined["ending_cash_p50"] <= base_90["ending_cash_p50"]


def test_largest_receivable_delay_changes_stress_result() -> None:
    result = forecast_liquidity(sample_profile(), simulations=2000, seed=17)
    base_90 = next(row for row in result["horizons"] if row["horizon_days"] == 90)
    delay = next(
        row for row in result["stress_tests"]
        if row["stress"] == "major_customer_delay_30d"
    )

    assert delay["ending_cash_p50"] <= base_90["ending_cash_p50"]


def test_guardrails_do_not_claim_credit_decision() -> None:
    result = forecast_liquidity(sample_profile(), simulations=500, seed=1)
    assert result["guardrails"]["is_credit_decision"] is False
    assert result["guardrails"]["is_loan_approval"] is False
    assert result["guardrails"]["human_review_required_for_bank_action"] is True
