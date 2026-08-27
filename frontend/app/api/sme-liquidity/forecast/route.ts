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

type StressName =
  | "base"
  | "major_customer_delay_30d"
  | "revenue_down_15pct"
  | "twd_strengthens_5pct"
  | "combined";

type Volatility = "low" | "medium" | "high";

type CustomProfileInput = {
  company_name: string;
  industry: string;
  current_cash: number;
  safety_cash_floor: number;
  avg_monthly_inflow: number;
  monthly_fixed_outflow: number;
  monthly_payroll: number;
  largest_receivable_amount: number;
  largest_receivable_due_days: number;
  receivable_delay_mean_days: number;
  largest_payable_amount: number;
  largest_payable_due_days: number;
  fx_receivable_share_percent: number;
  income_volatility: Volatility;
};

const SIMULATIONS = 2500;
const HORIZONS = [30, 60, 90] as const;
const ENGINE_VERSION = "monte-carlo-baseline-v1";

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

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function normal(random: () => number, mean: number, std: number) {
  let u = 0;
  let v = 0;
  while (u === 0) u = random();
  while (v === 0) v = random();
  const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  return mean + z * std;
}

function quantile(values: number[], q: number) {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const pos = (sorted.length - 1) * q;
  const lower = Math.floor(pos);
  const upper = Math.ceil(pos);
  if (lower === upper) return sorted[lower];
  const weight = pos - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

function applyStress(profile: Profile, stress: StressName): Profile {
  const next: Profile = {
    ...profile,
    receivables: profile.receivables.map((item) => ({ ...item })),
    payables: profile.payables.map((item) => ({ ...item })),
  };

  if (stress === "major_customer_delay_30d" || stress === "combined") {
    if (next.receivables.length) {
      const largest = next.receivables.reduce(
        (best, item, index, all) =>
          item.amount > all[best].amount ? index : best,
        0,
      );
      next.receivables[largest].dueDay += 30;
    }
  }

  if (stress === "revenue_down_15pct" || stress === "combined") {
    next.baselineDailyInflow *= 0.85;
  }

  if (
    (stress === "twd_strengthens_5pct" || stress === "combined") &&
    next.fxReceivableShare > 0
  ) {
    const drag = 0.05 * next.fxReceivableShare;
    next.baselineDailyInflow *= 1 - drag;
    next.receivables = next.receivables.map((item) => ({
      ...item,
      amount: item.amount * (1 - drag),
    }));
  }

  return next;
}

function simulate(profile: Profile, seed: number) {
  const paths: number[][] = [];
  const random = mulberry32(seed);

  for (let sim = 0; sim < SIMULATIONS; sim += 1) {
    let cash = profile.currentCash;
    const path: number[] = [];

    const receiptByDay = new Map<number, number>();
    for (const receivable of profile.receivables) {
      if (random() < receivable.defaultProbability) continue;
      const delay = Math.max(
        0,
        Math.round(
          normal(
            random,
            receivable.delayMeanDays,
            Math.max(0.01, receivable.delayStdDays),
          ),
        ),
      );
      const day = receivable.dueDay + delay;
      if (day >= 1 && day <= 90) {
        receiptByDay.set(
          day,
          (receiptByDay.get(day) ?? 0) + receivable.amount,
        );
      }
    }

    const payableByDay = new Map<number, number>();
    for (const payable of profile.payables) {
      if (payable.dueDay >= 1 && payable.dueDay <= 90) {
        payableByDay.set(
          payable.dueDay,
          (payableByDay.get(payable.dueDay) ?? 0) + payable.amount,
        );
      }
    }

    for (let day = 1; day <= 90; day += 1) {
      const recurringInflow = Math.max(
        0,
        normal(
          random,
          profile.baselineDailyInflow,
          profile.dailyInflowVolatility,
        ),
      );
      let outflow = profile.fixedDailyOutflow;
      if (day % profile.payrollEveryDays === 0) {
        outflow += profile.payrollAmount;
      }
      outflow += payableByDay.get(day) ?? 0;
      cash += recurringInflow + (receiptByDay.get(day) ?? 0) - outflow;
      path.push(cash);
    }

    paths.push(path);
  }

  return paths;
}

function metrics(paths: number[][], floor: number, horizon: number) {
  const endings: number[] = [];
  const minimums: number[] = [];
  const firstBreaches: number[] = [];

  for (const path of paths) {
    const window = path.slice(0, horizon);
    const ending = window[window.length - 1];
    const minimum = Math.min(...window);
    endings.push(ending);
    minimums.push(minimum);

    const first = window.findIndex((cash) => cash < floor);
    if (first >= 0) firstBreaches.push(first + 1);
  }

  const p10 = quantile(endings, 0.1);
  const p50 = quantile(endings, 0.5);
  const p90 = quantile(endings, 0.9);

  return {
    horizon_days: horizon,
    ending_cash_p10: Math.round(p10),
    ending_cash_p50: Math.round(p50),
    ending_cash_p90: Math.round(p90),
    shortfall_probability:
      Math.round((firstBreaches.length / paths.length) * 10000) / 10000,
    expected_min_cash: Math.round(
      minimums.reduce((sum, value) => sum + value, 0) / minimums.length,
    ),
    cash_flow_at_risk_p50_to_p10: Math.round(p50 - p10),
    median_first_breach_day:
      firstBreaches.length > 0
        ? Math.round(quantile(firstBreaches, 0.5))
        : null,
  };
}

function drivers(profile: Profile) {
  const rows = [
    {
      driver: "應收帳款延遲／違約暴露",
      exposure_amount: profile.receivables.reduce(
        (sum, item) =>
          sum +
          item.amount *
            Math.min(
              1,
              Math.max(
                0,
                item.defaultProbability + item.delayMeanDays / 90,
              ),
            ),
        0,
      ),
    },
    {
      driver: "已知應付款",
      exposure_amount: profile.payables
        .filter((item) => item.dueDay <= 90)
        .reduce((sum, item) => sum + item.amount, 0),
    },
    {
      driver: "薪資固定負擔",
      exposure_amount:
        profile.payrollAmount *
        Math.floor(90 / profile.payrollEveryDays),
    },
    {
      driver: "日常營運支出",
      exposure_amount: profile.fixedDailyOutflow * 90,
    },
    {
      driver: "外幣應收曝險",
      exposure_amount:
        profile.fxReceivableShare *
        (profile.baselineDailyInflow * 90 +
          profile.receivables.reduce((sum, item) => sum + item.amount, 0)),
    },
  ];

  return rows
    .filter((row) => row.exposure_amount > 0)
    .sort((a, b) => b.exposure_amount - a.exposure_amount)
    .map((row) => ({
      ...row,
      exposure_amount: Math.round(row.exposure_amount),
    }));
}

function actionHint(topDriver: string) {
  if (topDriver.includes("應收帳款")) {
    return {
      route: "應收帳款管理／承購諮詢",
      reason:
        "先確認最大客戶付款週期與可承作應收帳款，再由 RM 評估合適方案。",
    };
  }
  if (topDriver.includes("外幣")) {
    return {
      route: "外匯避險諮詢",
      reason:
        "先盤點收付款幣別與時點，再由 RM／專責人員評估避險工具。",
    };
  }
  if (topDriver.includes("薪資") || topDriver.includes("營運")) {
    return {
      route: "營運週轉金檢視",
      reason:
        "固定支出對安全水位影響較高，建議 RM 優先了解短期週轉需求。",
    };
  }
  return {
    route: "現金流盤點",
    reason:
      "由 RM 先確認大額付款時點與資金來源，再決定是否進一步媒合金融服務。",
  };
}


function adjustmentRecommendations(profile: Profile) {
  const seed = 20260917;
  const stressedBase = applyStress(profile, "combined");
  const baseResult = metrics(
    simulate(stressedBase, seed),
    stressedBase.safetyCashFloor,
    90,
  );
  const before = baseResult.shortfall_probability;

  const scenarios: Array<{
    code: string;
    title: string;
    rationale: string;
    profile: Profile;
  }> = [];

  if (profile.receivables.length) {
    const idx = profile.receivables.reduce(
      (best, item, index, all) =>
        item.amount > all[best].amount ? index : best,
      0,
    );
    const receivables = profile.receivables.map((item) => ({ ...item }));
    receivables[idx] = {
      ...receivables[idx],
      dueDay: Math.max(1, receivables[idx].dueDay - 10),
      delayMeanDays: Math.max(0, receivables[idx].delayMeanDays - 5),
    };
    scenarios.push({
      code: "accelerate_receivable",
      title: "優先催收最大筆應收帳款",
      rationale: "模擬把最大筆應收提前 10 天，並把平均延遲縮短 5 天。",
      profile: { ...profile, receivables },
    });
  }

  if (profile.payables.length) {
    const idx = profile.payables.reduce(
      (best, item, index, all) =>
        item.amount > all[best].amount ? index : best,
      0,
    );
    const payables = profile.payables.map((item) => ({ ...item }));
    payables[idx] = {
      ...payables[idx],
      dueDay: Math.min(180, payables[idx].dueDay + 15),
    };
    scenarios.push({
      code: "reschedule_payable",
      title: "協商最大筆應付款延後",
      rationale: "模擬把最大筆應付款延後 15 天，觀察短期現金水位是否改善。",
      profile: { ...profile, payables },
    });
  }

  if (profile.fixedDailyOutflow > 0) {
    scenarios.push({
      code: "reduce_fixed_cost",
      title: "短期降低固定營運支出 10%",
      rationale: "模擬未來 90 天固定營運支出下降 10%，不動薪資與應付款。",
      profile: {
        ...profile,
        fixedDailyOutflow: profile.fixedDailyOutflow * 0.9,
      },
    });
  }

  if (profile.fxReceivableShare > 0.05) {
    scenarios.push({
      code: "reduce_fx_exposure",
      title: "降低未避險外幣曝險",
      rationale: "模擬把外幣應收曝險占比降低一半，再承受同一組壓力測試。",
      profile: {
        ...profile,
        fxReceivableShare: profile.fxReceivableShare * 0.5,
      },
    });
  }

  return scenarios
    .map((scenario) => {
      const stressed = applyStress(scenario.profile, "combined");
      const result = metrics(
        simulate(stressed, seed),
        stressed.safetyCashFloor,
        90,
      );
      const after = result.shortfall_probability;
      return {
        code: scenario.code,
        title: scenario.title,
        rationale: scenario.rationale,
        before_shortfall_probability: before,
        after_shortfall_probability: after,
        improvement_percentage_points: Math.round(
          Math.max(0, before - after) * 10000,
        ) / 100,
        ending_cash_p50_after: result.ending_cash_p50,
      };
    })
    .sort(
      (a, b) =>
        b.improvement_percentage_points - a.improvement_percentage_points,
    )
    .slice(0, 4);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function validNumber(
  value: unknown,
  min: number,
  max: number,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= min &&
    value <= max
  );
}

function parseCustomProfile(value: unknown): Profile | null {
  if (!isPlainObject(value)) return null;

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
    companyName.trim().length > 40 ||
    typeof industry !== "string" ||
    industry.trim().length < 1 ||
    industry.trim().length > 40 ||
    !["low", "medium", "high"].includes(String(volatility))
  ) {
    return null;
  }

  const numericChecks: Array<[unknown, number, number]> = [
    [value.current_cash, 0, 10_000_000_000],
    [value.safety_cash_floor, 0, 10_000_000_000],
    [value.avg_monthly_inflow, 0, 10_000_000_000],
    [value.monthly_fixed_outflow, 0, 10_000_000_000],
    [value.monthly_payroll, 0, 10_000_000_000],
    [value.largest_receivable_amount, 0, 10_000_000_000],
    [value.largest_receivable_due_days, 1, 180],
    [value.receivable_delay_mean_days, 0, 90],
    [value.largest_payable_amount, 0, 10_000_000_000],
    [value.largest_payable_due_days, 1, 180],
    [value.fx_receivable_share_percent, 0, 100],
  ];
  if (numericChecks.some(([v, min, max]) => !validNumber(v, min, max))) {
    return null;
  }

  if (
    (value.safety_cash_floor as number) >
    Math.max(value.current_cash as number, value.avg_monthly_inflow as number)
  ) {
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
    description: "使用者手動輸入的競賽 PoC 情境；本頁不保存這份資料。",
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
    fxReceivableShare:
      (value.fx_receivable_share_percent as number) / 100,
  };
}

function sameOrigin(request: NextRequest) {
  const secFetchSite = request.headers.get("sec-fetch-site");
  if (
    secFetchSite &&
    !["same-origin", "same-site", "none"].includes(secFetchSite)
  ) {
    return false;
  }
  return true;
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

  if (!isPlainObject(payload)) {
    return NextResponse.json({ error: "invalid payload" }, { status: 422 });
  }

  const topLevelKeys = Object.keys(payload);
  if (
    topLevelKeys.length !== 1 ||
    !["profile_id", "custom_profile"].includes(topLevelKeys[0])
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
    dataMode = "user_supplied_demo";
    if (!profile) {
      return NextResponse.json(
        { error: "custom profile validation failed" },
        { status: 422 },
      );
    }
  }

  const basePaths = simulate(profile, 20260827);
  const horizons = HORIZONS.map((horizon) =>
    metrics(basePaths, profile.safetyCashFloor, horizon),
  );

  const stressNames: StressName[] = [
    "major_customer_delay_30d",
    "revenue_down_15pct",
    "twd_strengthens_5pct",
    "combined",
  ];

  const stress_tests = stressNames.map((stress, index) => {
    const stressed = applyStress(profile, stress);
    const stressedPaths = simulate(stressed, 20260827 + index + 1);
    const result = metrics(stressedPaths, stressed.safetyCashFloor, 90);
    return {
      stress,
      shortfall_probability: result.shortfall_probability,
      ending_cash_p50: result.ending_cash_p50,
      median_first_breach_day: result.median_first_breach_day,
    };
  });

  const driverRows = drivers(profile);
  const suggested = actionHint(driverRows[0]?.driver ?? "");
  const adjustment_recommendations = adjustmentRecommendations(profile);

  return NextResponse.json(
    {
      profile: {
        id: profile.id,
        name: profile.name,
        industry: profile.industry,
        description: profile.description,
        current_cash: profile.currentCash,
        safety_cash_floor: profile.safetyCashFloor,
      },
      engine: {
        version: ENGINE_VERSION,
        probabilistic: true,
        simulations: SIMULATIONS,
        horizons: [30, 60, 90],
        data_mode: dataMode,
      },
      horizons,
      stress_tests,
      drivers: driverRows,
      rm_next_step: suggested,
      adjustment_recommendations,
      guardrails: {
        is_credit_decision: false,
        is_loan_approval: false,
        automatic_product_sale: false,
        human_review_required: true,
        profile_persisted: false,
        synthetic_data_only: dataMode === "synthetic_demo",
      },
    },
    {
      headers: {
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    },
  );
}
