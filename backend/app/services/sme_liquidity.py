from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

HORIZONS = (30, 60, 90)
ENGINE_VERSION = "monte-carlo-baseline-v1"


@dataclass(frozen=True)
class Receivable:
    amount: float
    due_day: int
    delay_mean_days: float = 5.0
    delay_std_days: float = 5.0
    default_probability: float = 0.01


@dataclass(frozen=True)
class Payable:
    amount: float
    due_day: int


@dataclass(frozen=True)
class LiquidityProfile:
    current_cash: float
    safety_cash_floor: float
    baseline_daily_inflow: float
    daily_inflow_volatility: float
    fixed_daily_outflow: float
    payroll_amount: float
    payroll_every_days: int
    receivables: tuple[Receivable, ...] = ()
    payables: tuple[Payable, ...] = ()
    fx_receivable_share: float = 0.0


StressName = Literal[
    "base",
    "major_customer_delay_30d",
    "revenue_down_15pct",
    "twd_strengthens_5pct",
    "combined",
]


def _apply_stress(profile: LiquidityProfile, stress: StressName) -> LiquidityProfile:
    if stress == "base":
        return profile

    next_profile = profile
    if stress in {"major_customer_delay_30d", "combined"} and profile.receivables:
        idx = max(range(len(profile.receivables)), key=lambda i: profile.receivables[i].amount)
        receivables = list(profile.receivables)
        receivables[idx] = replace(receivables[idx], due_day=receivables[idx].due_day + 30)
        next_profile = replace(next_profile, receivables=tuple(receivables))

    if stress in {"revenue_down_15pct", "combined"}:
        next_profile = replace(
            next_profile,
            baseline_daily_inflow=next_profile.baseline_daily_inflow * 0.85,
        )

    if stress in {"twd_strengthens_5pct", "combined"} and next_profile.fx_receivable_share > 0:
        fx_drag = 0.05 * next_profile.fx_receivable_share
        next_profile = replace(
            next_profile,
            baseline_daily_inflow=next_profile.baseline_daily_inflow * (1.0 - fx_drag),
            receivables=tuple(
                replace(item, amount=item.amount * (1.0 - fx_drag))
                for item in next_profile.receivables
            ),
        )

    return next_profile


def _simulate_paths(
    profile: LiquidityProfile,
    *,
    simulations: int,
    days: int,
    seed: int,
) -> np.ndarray:
    if simulations < 100:
        raise ValueError("simulations must be >= 100")
    if days < 90:
        raise ValueError("days must cover 90-day horizon")
    if profile.payroll_every_days <= 0:
        raise ValueError("payroll_every_days must be > 0")

    rng = np.random.default_rng(seed)
    inflows = rng.normal(
        profile.baseline_daily_inflow,
        max(profile.daily_inflow_volatility, 0.0),
        size=(simulations, days),
    )
    inflows = np.maximum(inflows, 0.0)

    outflows = np.full((simulations, days), profile.fixed_daily_outflow, dtype=float)

    for day in range(profile.payroll_every_days, days + 1, profile.payroll_every_days):
        outflows[:, day - 1] += profile.payroll_amount

    for payable in profile.payables:
        if 1 <= payable.due_day <= days:
            outflows[:, payable.due_day - 1] += payable.amount

    receipts = np.zeros((simulations, days), dtype=float)
    for receivable in profile.receivables:
        defaults = rng.random(simulations) < receivable.default_probability
        delays = np.maximum(
            np.rint(
                rng.normal(
                    receivable.delay_mean_days,
                    max(receivable.delay_std_days, 0.01),
                    size=simulations,
                )
            ),
            0,
        ).astype(int)
        payment_days = receivable.due_day + delays
        valid = (~defaults) & (payment_days >= 1) & (payment_days <= days)
        rows = np.nonzero(valid)[0]
        cols = payment_days[valid] - 1
        receipts[rows, cols] += receivable.amount

    daily_net = inflows + receipts - outflows
    cash = np.empty((simulations, days + 1), dtype=float)
    cash[:, 0] = profile.current_cash
    cash[:, 1:] = profile.current_cash + np.cumsum(daily_net, axis=1)
    return cash


def _metrics(paths: np.ndarray, floor: float, horizon: int) -> dict[str, float | int | None]:
    window = paths[:, 1 : horizon + 1]
    ending = window[:, -1]
    minimum = np.min(window, axis=1)
    breached = minimum < floor
    first_breach_days: list[int] = []
    if np.any(breached):
        breach_matrix = window[breached] < floor
        first_breach_days = (np.argmax(breach_matrix, axis=1) + 1).tolist()

    p10, p50, p90 = np.quantile(ending, [0.1, 0.5, 0.9])
    return {
        "horizon_days": horizon,
        "ending_cash_p10": round(float(p10), 2),
        "ending_cash_p50": round(float(p50), 2),
        "ending_cash_p90": round(float(p90), 2),
        "shortfall_probability": round(float(np.mean(breached)), 4),
        "expected_min_cash": round(float(np.mean(minimum)), 2),
        "cash_flow_at_risk_p50_to_p10": round(float(p50 - p10), 2),
        "median_first_breach_day": (
            int(round(float(np.median(first_breach_days)))) if first_breach_days else None
        ),
    }


def _drivers(profile: LiquidityProfile) -> list[dict[str, float | str]]:
    rows = [
        (
            "應收帳款延遲／違約暴露",
            sum(
                r.amount * min(1.0, max(0.0, r.default_probability + r.delay_mean_days / 90.0))
                for r in profile.receivables
            ),
        ),
        ("已知應付款", sum(p.amount for p in profile.payables if p.due_day <= 90)),
        ("薪資固定負擔", profile.payroll_amount * (90 // profile.payroll_every_days)),
        ("日常營運支出", profile.fixed_daily_outflow * 90),
        (
            "外幣應收曝險",
            profile.fx_receivable_share
            * (profile.baseline_daily_inflow * 90 + sum(r.amount for r in profile.receivables)),
        ),
    ]
    rows.sort(key=lambda item: item[1], reverse=True)
    return [
        {"driver": name, "exposure_amount": round(float(amount), 2)}
        for name, amount in rows
        if amount > 0
    ]


def forecast_liquidity(
    profile: LiquidityProfile,
    *,
    simulations: int = 5000,
    seed: int = 20260827,
) -> dict[str, object]:
    base_paths = _simulate_paths(profile, simulations=simulations, days=90, seed=seed)
    horizons = [_metrics(base_paths, profile.safety_cash_floor, h) for h in HORIZONS]

    stress_tests = []
    for stress in ("major_customer_delay_30d", "revenue_down_15pct", "twd_strengthens_5pct", "combined"):
        stressed = _apply_stress(profile, stress)
        paths = _simulate_paths(stressed, simulations=simulations, days=90, seed=seed)
        m = _metrics(paths, stressed.safety_cash_floor, 90)
        stress_tests.append(
            {
                "stress": stress,
                "shortfall_probability": m["shortfall_probability"],
                "ending_cash_p50": m["ending_cash_p50"],
                "median_first_breach_day": m["median_first_breach_day"],
            }
        )

    return {
        "engine_version": ENGINE_VERSION,
        "probabilistic": True,
        "simulations": simulations,
        "seed": seed,
        "safety_cash_floor": round(profile.safety_cash_floor, 2),
        "horizons": horizons,
        "stress_tests": stress_tests,
        "drivers": _drivers(profile),
        "guardrails": {
            "is_credit_decision": False,
            "is_loan_approval": False,
            "human_review_required_for_bank_action": True,
        },
    }
