import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type HorizonSnapshot = {
  horizon_days: number;
  ending_cash_p10: number;
  ending_cash_p50: number;
  ending_cash_p90: number;
  shortfall_probability: number;
  shortfall_probability_ci95_upper: number;
  p10_buffer_above_floor: number;
  median_first_breach_day: number | null;
};

type StressSnapshot = {
  stress: string;
  shortfall_probability: number;
  ending_cash_p50: number;
};

type ForecastBody = {
  horizons?: HorizonSnapshot[];
  stress_tests?: StressSnapshot[];
  risk_interpretation?: unknown;
};

type Case = {
  name: string;
  payload: Record<string, unknown>;
  expect: (body: ForecastBody) => { pass: boolean; reason: string };
};

function baseProfile(overrides: Record<string, unknown> = {}) {
  return {
    company_name: "Extreme Test Co.",
    industry: "一般企業",
    current_cash: 1_000_000,
    safety_cash_floor: 500_000,
    avg_monthly_inflow: 1_200_000,
    monthly_fixed_outflow: 600_000,
    monthly_payroll: 200_000,
    largest_receivable_amount: 300_000,
    largest_receivable_due_days: 30,
    receivable_delay_mean_days: 7,
    largest_payable_amount: 250_000,
    largest_payable_due_days: 35,
    fx_receivable_share_percent: 10,
    income_volatility: "medium",
    ...overrides,
  };
}

function horizon(body: ForecastBody, days: number) {
  return body.horizons?.find((row) => row.horizon_days === days);
}

function stress(body: ForecastBody, name: string) {
  return body.stress_tests?.find((row) => row.stress === name);
}

const cases: Case[] = [
  {
    name: "day0_below_floor",
    payload: baseProfile({ current_cash: 100_000, safety_cash_floor: 500_000 }),
    expect: (body) => {
      const h30 = horizon(body, 30);
      return {
        pass:
          h30?.shortfall_probability === 1 &&
          h30?.median_first_breach_day === 0,
        reason:
          "Day 0 已低於安全水位時，30 天跌破機率應為 100%，首次跌破日應為 0。",
      };
    },
  },
  {
    name: "zero_revenue",
    payload: baseProfile({
      avg_monthly_inflow: 0,
      monthly_fixed_outflow: 600_000,
      monthly_payroll: 300_000,
    }),
    expect: (body) => {
      const h90 = horizon(body, 90);
      return {
        pass:
          typeof h90?.shortfall_probability === "number" &&
          h90.shortfall_probability > 0.5,
        reason: "零收入且持續支出時，90 天風險應顯著偏高。",
      };
    },
  },
  {
    name: "huge_payable",
    payload: baseProfile({
      largest_payable_amount: 10_000_000,
      largest_payable_due_days: 20,
    }),
    expect: (body) => {
      const h30 = horizon(body, 30);
      return {
        pass:
          typeof h30?.shortfall_probability === "number" &&
          h30.shortfall_probability > 0.5,
        reason: "巨大且短期到期的應付款應快速推高 30 天缺口風險。",
      };
    },
  },
  {
    name: "receivable_outside_horizon",
    payload: baseProfile({
      largest_receivable_amount: 10_000_000,
      largest_receivable_due_days: 180,
      largest_payable_amount: 0,
    }),
    expect: (body) => {
      const h90 = horizon(body, 90);
      return {
        pass:
          typeof h90?.ending_cash_p50 === "number" &&
          Number.isFinite(h90.ending_cash_p50),
        reason: "90 天以外的大額應收不能被錯算進 90 天現金流。",
      };
    },
  },
  {
    name: "full_fx_exposure",
    payload: baseProfile({ fx_receivable_share_percent: 100 }),
    expect: (body) => {
      const fx = stress(body, "twd_strengthens_5pct");
      const base90 = horizon(body, 90);
      return {
        pass:
          typeof fx?.ending_cash_p50 === "number" &&
          typeof base90?.ending_cash_p50 === "number" &&
          fx.ending_cash_p50 <= base90.ending_cash_p50,
        reason:
          "100% 外幣收入時，台幣升值壓力後的 P50 不應比基準更高。",
      };
    },
  },
  {
    name: "zero_fx_exposure",
    payload: baseProfile({ fx_receivable_share_percent: 0 }),
    expect: (body) => {
      const fx = stress(body, "twd_strengthens_5pct");
      const base90 = horizon(body, 90);
      return {
        pass:
          typeof fx?.ending_cash_p50 === "number" &&
          typeof base90?.ending_cash_p50 === "number" &&
          Math.abs(fx.ending_cash_p50 - base90.ending_cash_p50) < 150_000,
        reason:
          "0% 外幣曝險時，匯率壓力不應造成巨大差異；僅容許 Monte Carlo 抽樣誤差。",
      };
    },
  },
  {
    name: "very_high_volatility",
    payload: baseProfile({
      income_volatility: "high",
      avg_monthly_inflow: 2_000_000,
    }),
    expect: (body) => {
      const h90 = horizon(body, 90);
      return {
        pass:
          typeof h90?.ending_cash_p10 === "number" &&
          typeof h90?.ending_cash_p90 === "number" &&
          h90.ending_cash_p90 > h90.ending_cash_p10,
        reason: "高波動下分布仍需有合理 P10 < P90，不得 NaN 或倒置。",
      };
    },
  },
  {
    name: "near_threshold_zero_events",
    payload: baseProfile({
      current_cash: 650_000,
      safety_cash_floor: 500_000,
      avg_monthly_inflow: 1_800_000,
      monthly_fixed_outflow: 1_150_000,
      monthly_payroll: 300_000,
      largest_receivable_amount: 0,
      largest_payable_amount: 0,
    }),
    expect: (body) => {
      const h90 = horizon(body, 90);
      return {
        pass:
          typeof h90?.shortfall_probability_ci95_upper === "number" &&
          typeof h90?.p10_buffer_above_floor === "number",
        reason:
          "即使事件數為 0，也必須回傳 CI95 上界與安全水位緩衝。",
      };
    },
  },
];

export async function GET(request: NextRequest) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json(
      { error: "not found" },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  }

  const base = new URL("/api/sme-liquidity/forecast", request.url);
  const results: Array<Record<string, unknown>> = [];

  for (const item of cases) {
    const response = await fetch(base, {
      method: "POST",
      cache: "no-store",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "sec-fetch-site": "same-origin",
      },
      body: JSON.stringify({ custom_profile: item.payload }),
    });

    if (!response.ok) {
      results.push({
        name: item.name,
        pass: false,
        reason: `forecast returned ${response.status}`,
      });
      continue;
    }

    const body = (await response.json()) as ForecastBody;
    const check = item.expect(body);

    results.push({
      name: item.name,
      pass: check.pass,
      reason: check.reason,
      snapshot: {
        h30: horizon(body, 30),
        h90: horizon(body, 90),
        interpretation: body.risk_interpretation,
      },
    });
  }

  const failed = results.filter((item) => item.pass !== true);

  return NextResponse.json(
    {
      status: failed.length ? "FAIL" : "PASS",
      case_count: results.length,
      failed_count: failed.length,
      results,
    },
    {
      status: failed.length ? 500 : 200,
      headers: {
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    },
  );
}
