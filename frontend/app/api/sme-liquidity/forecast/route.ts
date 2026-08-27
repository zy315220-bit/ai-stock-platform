import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type Receivable = {
  amount: number;
  dueDay: number;
  delayMeanDays: number;
  delayStdDays: number;
  defaultProbability: number;
};

type Payable = {
  amount: number;
  dueDay: number;
};

type Profile = {
  id: string;
  name: string;
  industry: string;
  description: string;
  currentCash: number;
  safetyCashFloor: number;
  baselineDailyInflow: number;
  dailyInflowVolatility: number;
  fixedDailyOutflow: number;
  payrollAmount: number;
  payrollEveryDays: number;
  receivables: Receivable[];
  payables: Payable[];
  fxReceivableShare: number;
};

const PROFILES: Record<string, Profile> = {
  exporter: {
    id: "exporter",
    name: "宏昇精密",
    industry: "出口製造",
    description: "美元應收較高、兩筆大額應付款集中於未來 90 天。",
    currentCash: 4_200_000,
    safetyCashFloor: 1_200_000,
    baselineDailyInflow: 92_000,
    dailyInflowVolatility: 38_000,
    fixedDailyOutflow: 82_000,
    payrollAmount: 920_000,
    payrollEveryDays: 30,
    receivables: [
      {
        amount: 2_100_000,
        dueDay: 28,
        delayMeanDays: 11,
        delayStdDays: 8,
        defaultProbability: 0.02,
      },
      {
        amount: 1_450_000,
        dueDay: 52,
        delayMeanDays: 7,
        delayStdDays: 6,
        defaultProbability: 0.01,
      },
    ],
    payables: [
      { amount: 1_350_000, dueDay: 42 },
      { amount: 1_100_000, dueDay: 73 },
    ],
    fxReceivableShare: 0.55,
  },
  wholesaler: {
    id: "wholesaler",
    name: "海岳商貿",
    industry: "批發貿易",
    description: "應收帳款占比高，現金安全水位對客戶延遲付款非常敏感。",
    currentCash: 3_100_000,
    safetyCashFloor: 1_000_000,
    baselineDailyInflow: 76_000,
    dailyInflowVolatility: 34_000,
    fixedDailyOutflow: 72_000,
    payrollAmount: 560_000,
    payrollEveryDays: 30,
    receivables: [
      {
        amount: 2_700_000,
        dueDay: 24,
        delayMeanDays: 16,
        delayStdDays: 10,
        defaultProbability: 0.03,
      },
      {
        amount: 980_000,
        dueDay: 61,
        delayMeanDays: 9,
        delayStdDays: 7,
        defaultProbability: 0.015,
      },
    ],
    payables: [
      { amount: 1_600_000, dueDay: 39 },
      { amount: 850_000, dueDay: 68 },
    ],
    fxReceivableShare: 0.18,
  },
  service: {
    id: "service",
    name: "沐光數位",
    industry: "企業服務",
    description: "固定人事成本高、應收款較分散，主要壓力來自收入下滑。",
    currentCash: 2_800_000,
    safetyCashFloor: 900_000,
    baselineDailyInflow: 88_000,
    dailyInflowVolatility: 29_000,
    fixedDailyOutflow: 66_000,
    payrollAmount: 1_180_000,
    payrollEveryDays: 30,
    receivables: [
      {
        amount: 760_000,
        dueDay: 32,
        delayMeanDays: 5,
        delayStdDays: 4,
        defaultProbability: 0.01,
      },
      {
        amount: 690_000,
        dueDay: 57,
        delayMeanDays: 4,
        delayStdDays: 4,
        defaultProbability: 0.01,
      },
    ],
    payables: [{ amount: 420_000, dueDay: 50 }],
    fxReceivableShare: 0.03,
  },
};

function sameOrigin(request: NextRequest) {
  const secFetchSite = request.headers.get("sec-fetch-site");
  return (
    !secFetchSite ||
    ["same-origin", "same-site", "none"].includes(secFetchSite)
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function validNumber(value: unknown, min: number, max: number) {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= min &&
    value <= max
  );
}

function parseCustomProfile(value: unknown): Profile | null {
  if (!isObject(value)) return null;

  const allowed = new Set([
    "company_name",
    "industry",
    "current_cash",
    "safety_cash_floor",
    "avg_monthly_inflow",
    "monthly_fixed_outflow",
    "monthly_payroll",
    "largest_receivable_amount",
    "largest_receivable_due_days",
    "receivable_delay_mean_days",
    "largest_payable_amount",
    "largest_payable_due_days",
    "fx_receivable_share_percent",
    "income_volatility",
  ]);
  if (Object.keys(value).some((key) => !allowed.has(key))) return null;

  const companyName = value.company_name;
  const industry = value.industry;
  const volatility = value.income_volatility;

  if (
    typeof companyName !== "string" ||
    companyName.trim().length < 1 ||
    companyName.trim().length > 80 ||
    typeof industry !== "string" ||
    industry.trim().length < 1 ||
    industry.trim().length > 80 ||
    !["low", "medium", "high"].includes(String(volatility))
  ) {
    return null;
  }

  const checks: Array<[unknown, number, number]> = [
    [value.current_cash, 0, 100_000_000_000],
    [value.safety_cash_floor, 0, 100_000_000_000],
    [value.avg_monthly_inflow, 0, 100_000_000_000],
    [value.monthly_fixed_outflow, 0, 100_000_000_000],
    [value.monthly_payroll, 0, 100_000_000_000],
    [value.largest_receivable_amount, 0, 100_000_000_000],
    [value.largest_receivable_due_days, 1, 180],
    [value.receivable_delay_mean_days, 0, 90],
    [value.largest_payable_amount, 0, 100_000_000_000],
    [value.largest_payable_due_days, 1, 180],
    [value.fx_receivable_share_percent, 0, 100],
  ];
  if (checks.some(([v, min, max]) => !validNumber(v, min, max))) {
    return null;
  }

  const monthlyInflow = value.avg_monthly_inflow as number;
  const dailyInflow = monthlyInflow / 30;
  const volatilityFactor =
    volatility === "low" ? 0.15 : volatility === "high" ? 0.6 : 0.35;
  const receivableAmount = value.largest_receivable_amount as number;
  const payableAmount = value.largest_payable_amount as number;
  const delayMean = value.receivable_delay_mean_days as number;

  return {
    id: "custom",
    name: companyName.trim(),
    industry: industry.trim(),
    description: "使用者輸入或系統估算的競賽 PoC 情境；本頁不保存。",
    currentCash: value.current_cash as number,
    safetyCashFloor: value.safety_cash_floor as number,
    baselineDailyInflow: dailyInflow,
    dailyInflowVolatility: dailyInflow * volatilityFactor,
    fixedDailyOutflow: (value.monthly_fixed_outflow as number) / 30,
    payrollAmount: value.monthly_payroll as number,
    payrollEveryDays: 30,
    receivables:
      receivableAmount > 0
        ? [
            {
              amount: receivableAmount,
              dueDay: Math.round(value.largest_receivable_due_days as number),
              delayMeanDays: delayMean,
              delayStdDays: Math.max(2, delayMean * 0.6),
              defaultProbability: 0.015,
            },
          ]
        : [],
    payables:
      payableAmount > 0
        ? [
            {
              amount: payableAmount,
              dueDay: Math.round(value.largest_payable_due_days as number),
            },
          ]
        : [],
    fxReceivableShare: (value.fx_receivable_share_percent as number) / 100,
  };
}

function toBackendPayload(profile: Profile) {
  return {
    name: profile.name,
    industry: profile.industry,
    description: profile.description,
    current_cash: profile.currentCash,
    safety_cash_floor: profile.safetyCashFloor,
    baseline_daily_inflow: profile.baselineDailyInflow,
    daily_inflow_volatility: profile.dailyInflowVolatility,
    fixed_daily_outflow: profile.fixedDailyOutflow,
    payroll_amount: profile.payrollAmount,
    payroll_every_days: profile.payrollEveryDays,
    receivables: profile.receivables.map((item) => ({
      amount: item.amount,
      due_day: item.dueDay,
      delay_mean_days: item.delayMeanDays,
      delay_std_days: item.delayStdDays,
      default_probability: item.defaultProbability,
    })),
    payables: profile.payables.map((item) => ({
      amount: item.amount,
      due_day: item.dueDay,
    })),
    fx_receivable_share: profile.fxReceivableShare,
    simulations: 2500,
    seed: 20260827,
  };
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) {
    return NextResponse.json(
      { error: "cross-site request rejected" },
      { status: 403 },
    );
  }

  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    return NextResponse.json(
      { error: "application/json required" },
      { status: 415 },
    );
  }

  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > 4096) {
    return NextResponse.json({ error: "request too large" }, { status: 413 });
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  if (!isObject(payload)) {
    return NextResponse.json({ error: "invalid payload" }, { status: 422 });
  }

  const keys = Object.keys(payload);
  if (
    keys.length !== 1 ||
    !["profile_id", "custom_profile"].includes(keys[0])
  ) {
    return NextResponse.json({ error: "invalid payload" }, { status: 422 });
  }

  let profile: Profile | null = null;
  let dataMode = "synthetic_demo";

  if ("profile_id" in payload) {
    const profileId = payload.profile_id;
    if (typeof profileId !== "string" || !(profileId in PROFILES)) {
      return NextResponse.json({ error: "unknown profile" }, { status: 422 });
    }
    profile = PROFILES[profileId];
  } else {
    profile = parseCustomProfile(payload.custom_profile);
    dataMode = "user_supplied_or_estimated";
    if (!profile) {
      return NextResponse.json(
        { error: "custom profile validation failed" },
        { status: 422 },
      );
    }
  }

  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    return NextResponse.json(
      { error: "authoritative liquidity engine unavailable" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12_000);

  try {
    const response = await fetch(
      `${backendUrl.replace(/\/$/, "")}/api/sme-liquidity/forecast`,
      {
        method: "POST",
        cache: "no-store",
        signal: controller.signal,
        headers: {
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify(toBackendPayload(profile)),
      },
    );

    if (!response.ok) {
      return NextResponse.json(
        {
          error: "authoritative liquidity engine rejected request",
          upstream_status: response.status,
        },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }

    const result = (await response.json()) as Record<string, unknown>;
    const engine =
      isObject(result.engine) ? { ...result.engine, data_mode: dataMode } : null;

    return NextResponse.json(
      {
        ...result,
        engine,
      },
      {
        headers: {
          "cache-control": "no-store",
          "x-content-type-options": "nosniff",
          "x-sme-liquidity-engine": "python-authoritative-v2",
        },
      },
    );
  } catch {
    return NextResponse.json(
      { error: "authoritative liquidity engine unavailable" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  } finally {
    clearTimeout(timer);
  }
}
