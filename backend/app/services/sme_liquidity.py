from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import log, log1p, sqrt
from typing import Literal

import numpy as np

HORIZONS = (30, 60, 90)
ENGINE_VERSION = "sme-liquidity-monte-carlo-v2"
Z_95 = 1.959963984540054


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
    name: str = ""
    industry: str = ""
    description: str = ""


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


def _lognormal_params(mean: float, std: float) -> tuple[float, float]:
    if mean <= 0:
        return 0.0, 0.0
    if std <= 0:
        return log(mean), 0.0
    variance_ratio = (std * std) / (mean * mean)
    sigma2 = log1p(variance_ratio)
    sigma = sqrt(sigma2)
    mu = log(mean) - sigma2 / 2
    return mu, sigma


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

    if profile.baseline_daily_inflow <= 0:
        inflows = np.zeros((simulations, days), dtype=float)
    elif profile.daily_inflow_volatility <= 0:
        inflows = np.full(
            (simulations, days),
            profile.baseline_daily_inflow,
            dtype=float,
        )
    else:
        mu, sigma = _lognormal_params(
            profile.baseline_daily_inflow,
            profile.daily_inflow_volatility,
        )
        inflows = rng.lognormal(mu, sigma, size=(simulations, days))

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


def _wilson_interval(successes: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    z2 = Z_95 * Z_95
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half = (
        Z_95
        * sqrt((p * (1 - p)) / n + z2 / (4 * n * n))
        / denominator
    )
    return max(0.0, center - half), min(1.0, center + half)


def _metrics(
    paths: np.ndarray,
    floor: float,
    horizon: int,
    initial_cash: float,
) -> dict[str, float | int | None]:
    window = paths[:, 1 : horizon + 1]
    ending = window[:, -1]
    minimum = np.minimum(np.min(window, axis=1), initial_cash)

    if initial_cash < floor:
        breached = np.ones(paths.shape[0], dtype=bool)
        first_breach_days = np.zeros(paths.shape[0], dtype=int)
    else:
        breach_matrix = window < floor
        breached = np.any(breach_matrix, axis=1)
        first_breach_days = np.argmax(breach_matrix[breached], axis=1) + 1 if np.any(breached) else np.array([], dtype=int)

    successes = int(np.sum(breached))
    n = int(paths.shape[0])
    lower, upper = _wilson_interval(successes, n)

    p10, p50, p90 = np.quantile(ending, [0.1, 0.5, 0.9])
    min_p10, min_p50 = np.quantile(minimum, [0.1, 0.5])
    buffer = float(min_p10 - floor)

    return {
        "horizon_days": horizon,
        "ending_cash_p10": round(float(p10), 2),
        "ending_cash_p50": round(float(p50), 2),
        "ending_cash_p90": round(float(p90), 2),
        "shortfall_probability": round(successes / n, 6),
        "shortfall_breach_count": successes,
        "simulated_path_count": n,
        "shortfall_probability_ci95_lower": round(lower, 6),
        "shortfall_probability_ci95_upper": round(upper, 6),
        "expected_min_cash": round(float(np.mean(minimum)), 2),
        "min_cash_p10": round(float(min_p10), 2),
        "min_cash_p50": round(float(min_p50), 2),
        "p10_buffer_above_floor": round(buffer, 2),
        "p10_buffer_ratio": round(buffer / floor, 6) if floor > 0 else None,
        "cash_flow_at_risk_p50_to_p10": round(float(p50 - p10), 2),
        "median_first_breach_day": (
            int(round(float(np.median(first_breach_days))))
            if first_breach_days.size
            else None
        ),
    }


def _drivers(profile: LiquidityProfile) -> list[dict[str, float | str]]:
    rows = [
        (
            "應收帳款延遲／違約暴露",
            sum(
                r.amount
                * min(
                    1.0,
                    max(0.0, r.default_probability + r.delay_mean_days / 90.0),
                )
                for r in profile.receivables
            ),
        ),
        ("已知應付款", sum(p.amount for p in profile.payables if p.due_day <= 90)),
        ("薪資固定負擔", profile.payroll_amount * (90 // profile.payroll_every_days)),
        ("日常營運支出", profile.fixed_daily_outflow * 90),
        (
            "外幣應收曝險",
            profile.fx_receivable_share
            * (
                profile.baseline_daily_inflow * 90
                + sum(r.amount for r in profile.receivables)
            ),
        ),
    ]
    rows.sort(key=lambda item: item[1], reverse=True)
    return [
        {"driver": name, "exposure_amount": round(float(amount), 2)}
        for name, amount in rows
        if amount > 0
    ]


def _action_hint(top_driver: str) -> dict[str, str]:
    if "應收帳款" in top_driver:
        return {
            "route": "應收帳款管理／承購諮詢",
            "reason": "先確認最大客戶付款週期與可承作應收帳款，再由 RM 評估合適方案。",
        }
    if "外幣" in top_driver:
        return {
            "route": "外匯避險諮詢",
            "reason": "先盤點收付款幣別與時點，再由 RM／專責人員評估避險工具。",
        }
    if "薪資" in top_driver or "營運" in top_driver:
        return {
            "route": "營運週轉金檢視",
            "reason": "固定支出對安全水位影響較高，建議 RM 優先了解短期週轉需求。",
        }
    return {
        "route": "現金流盤點",
        "reason": "由 RM 先確認大額付款時點與資金來源，再決定是否進一步媒合金融服務。",
    }


def _risk_interpretation(
    profile: LiquidityProfile,
    horizons: list[dict[str, object]],
    stress_tests: list[dict[str, object]],
) -> dict[str, object]:
    h90 = next((row for row in horizons if row["horizon_days"] == 90), horizons[-1])
    max_stress = max(
        stress_tests,
        key=lambda row: float(row["shortfall_probability"]),
    )

    buffer_ratio_raw = h90["p10_buffer_ratio"]
    buffer_ratio = float(buffer_ratio_raw) if isinstance(buffer_ratio_raw, (int, float)) else None
    base = float(h90["shortfall_probability"])
    upper95 = float(h90["shortfall_probability_ci95_upper"])
    stress = float(max_stress["shortfall_probability"])

    status = "ROBUST"
    label = "有緩衝"
    summary = "目前模擬顯示安全水位有足夠緩衝，但仍應持續更新真實現金流資料。"

    if base >= 0.5:
        status = "HIGH_RISK"
        label = "高風險"
        summary = "正常情境下已有大量模擬路徑跌破安全水位，應優先確認真實現金流與短期資金安排。"
    elif base >= 0.1:
        status = "WATCH"
        label = "需注意"
        summary = "正常情境已出現可觀的跌破機率，建議優先檢查應收、應付與固定支出時點。"
    elif buffer_ratio is not None and buffer_ratio <= 0.25:
        status = "NEAR_THRESHOLD"
        label = "接近臨界"
        summary = "目前跌破機率可能仍低，但悲觀路徑的最低現金已接近安全水位，小幅偏差就可能改變結論。"
    elif stress >= 0.2 and stress >= max(0.1, base + 0.15):
        status = "STRESS_SENSITIVE"
        label = "壓力敏感"
        summary = "正常情境看起來穩定，但壓力情境會明顯推高資金缺口風險，不能只看基準情境。"
    elif base > 0 or upper95 >= 0.02:
        status = "WATCH"
        label = "低風險但需追蹤"
        summary = "模擬跌破事件很少，但統計不確定性與資料估算仍存在，建議持續追蹤。"

    reasons: list[str] = []
    breach_count = int(h90["shortfall_breach_count"])
    path_count = int(h90["simulated_path_count"])
    if breach_count == 0:
        reasons.append(
            f"{path_count:,} 條模擬中未觀察到跌破；這不代表真實風險為 0，95% 信賴上界約為 {upper95 * 100:.2f}%。"
        )
    else:
        reasons.append(
            f"90 天基準情境有 {breach_count} / {path_count} 條路徑跌破安全水位。"
        )

    if buffer_ratio is not None:
        reasons.append(
            f"90 天悲觀最低現金 P10 約比安全水位多 {float(h90['p10_buffer_above_floor']):,.0f} 元（{buffer_ratio * 100:.0f}% 緩衝）。"
        )

    reasons.append(
        f"最敏感壓力情境「{max_stress['stress']}」會把 90 天缺口機率推到 {stress * 100:.1f}%。"
    )

    return {
        "status": status,
        "label": label,
        "summary": summary,
        "reasons": reasons,
        "base_90_probability": base,
        "base_90_ci95_upper": upper95,
        "p10_min_cash_90": h90["min_cash_p10"],
        "p10_buffer_above_floor_90": h90["p10_buffer_above_floor"],
        "p10_buffer_ratio_90": buffer_ratio,
        "most_sensitive_stress": max_stress["stress"],
        "most_sensitive_stress_probability": stress,
        "safety_cash_floor": profile.safety_cash_floor,
    }


def _adjustment_recommendations(
    profile: LiquidityProfile,
    *,
    simulations: int,
) -> list[dict[str, object]]:
    seed = 20260917
    stressed_base = _apply_stress(profile, "combined")
    base_paths = _simulate_paths(
        stressed_base,
        simulations=simulations,
        days=90,
        seed=seed,
    )
    base_result = _metrics(
        base_paths,
        stressed_base.safety_cash_floor,
        90,
        stressed_base.current_cash,
    )
    before = float(base_result["shortfall_probability"])

    scenarios: list[tuple[str, str, str, LiquidityProfile]] = []

    if profile.receivables:
        idx = max(range(len(profile.receivables)), key=lambda i: profile.receivables[i].amount)
        receivables = list(profile.receivables)
        current = receivables[idx]
        receivables[idx] = replace(
            current,
            due_day=max(1, current.due_day - 10),
            delay_mean_days=max(0.0, current.delay_mean_days - 5),
        )
        scenarios.append(
            (
                "accelerate_receivable",
                "優先催收最大筆應收帳款",
                "模擬把最大筆應收提前 10 天，並把平均延遲縮短 5 天。",
                replace(profile, receivables=tuple(receivables)),
            )
        )

    if profile.payables:
        idx = max(range(len(profile.payables)), key=lambda i: profile.payables[i].amount)
        payables = list(profile.payables)
        current = payables[idx]
        payables[idx] = replace(current, due_day=min(180, current.due_day + 15))
        scenarios.append(
            (
                "reschedule_payable",
                "協商最大筆應付款延後",
                "模擬把最大筆應付款延後 15 天，觀察短期現金水位是否改善。",
                replace(profile, payables=tuple(payables)),
            )
        )

    if profile.fixed_daily_outflow > 0:
        scenarios.append(
            (
                "reduce_fixed_cost",
                "短期降低固定營運支出 10%",
                "模擬未來 90 天固定營運支出下降 10%，不動薪資與應付款。",
                replace(
                    profile,
                    fixed_daily_outflow=profile.fixed_daily_outflow * 0.9,
                ),
            )
        )

    if profile.fx_receivable_share > 0.05:
        scenarios.append(
            (
                "reduce_fx_exposure",
                "降低未避險外幣曝險",
                "模擬把外幣應收曝險占比降低一半，再承受同一組壓力測試。",
                replace(
                    profile,
                    fx_receivable_share=profile.fx_receivable_share * 0.5,
                ),
            )
        )

    results: list[dict[str, object]] = []
    for code, title, rationale, scenario_profile in scenarios:
        stressed = _apply_stress(scenario_profile, "combined")
        paths = _simulate_paths(
            stressed,
            simulations=simulations,
            days=90,
            seed=seed,
        )
        result = _metrics(
            paths,
            stressed.safety_cash_floor,
            90,
            stressed.current_cash,
        )
        after = float(result["shortfall_probability"])
        results.append(
            {
                "code": code,
                "title": title,
                "rationale": rationale,
                "before_shortfall_probability": before,
                "after_shortfall_probability": after,
                "improvement_percentage_points": round(max(0.0, before - after) * 100, 2),
                "ending_cash_p50_after": result["ending_cash_p50"],
            }
        )

    results.sort(
        key=lambda row: float(row["improvement_percentage_points"]),
        reverse=True,
    )
    return results[:4]


def _profile_fingerprint(
    profile: LiquidityProfile,
    *,
    simulations: int,
    seed: int,
) -> str:
    payload = {
        "profile": asdict(profile),
        "simulations": simulations,
        "seed": seed,
        "engine_version": ENGINE_VERSION,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def forecast_liquidity(
    profile: LiquidityProfile,
    *,
    simulations: int = 2500,
    seed: int = 20260827,
) -> dict[str, object]:
    base_paths = _simulate_paths(
        profile,
        simulations=simulations,
        days=90,
        seed=seed,
    )
    horizons = [
        _metrics(
            base_paths,
            profile.safety_cash_floor,
            h,
            profile.current_cash,
        )
        for h in HORIZONS
    ]

    stress_tests: list[dict[str, object]] = []
    for stress in (
        "major_customer_delay_30d",
        "revenue_down_15pct",
        "twd_strengthens_5pct",
        "combined",
    ):
        stressed = _apply_stress(profile, stress)
        paths = _simulate_paths(
            stressed,
            simulations=simulations,
            days=90,
            seed=seed,
        )
        m = _metrics(
            paths,
            stressed.safety_cash_floor,
            90,
            stressed.current_cash,
        )
        stress_tests.append(
            {
                "stress": stress,
                "shortfall_probability": m["shortfall_probability"],
                "ending_cash_p50": m["ending_cash_p50"],
                "median_first_breach_day": m["median_first_breach_day"],
            }
        )

    drivers = _drivers(profile)
    return {
        "engine": {
            "version": ENGINE_VERSION,
            "probabilistic": True,
            "simulations": simulations,
            "seed": seed,
            "input_fingerprint": _profile_fingerprint(
                profile,
                simulations=simulations,
                seed=seed,
            ),
            "horizons": list(HORIZONS),
            "assumptions": {
                "nonnegative_inflow_distribution": "lognormal_mean_std_calibrated",
                "receivable_delay_distribution": "truncated_normal_nonnegative",
                "day0_floor_breach_included": True,
                "deterministic_seed_for_demo": True,
                "scenario_comparison_design": "common_random_numbers",
            },
        },
        "profile": {
            "name": profile.name,
            "industry": profile.industry,
            "description": profile.description,
            "current_cash": round(profile.current_cash, 2),
            "safety_cash_floor": round(profile.safety_cash_floor, 2),
        },
        "horizons": horizons,
        "stress_tests": stress_tests,
        "risk_interpretation": _risk_interpretation(
            profile,
            horizons,
            stress_tests,
        ),
        "drivers": drivers,
        "rm_next_step": _action_hint(
            str(drivers[0]["driver"]) if drivers else ""
        ),
        "adjustment_recommendations": _adjustment_recommendations(
            profile,
            simulations=simulations,
        ),
        "guardrails": {
            "is_credit_decision": False,
            "is_loan_approval": False,
            "automatic_product_sale": False,
            "human_review_required": True,
            "profile_persisted": False,
        },
    }
