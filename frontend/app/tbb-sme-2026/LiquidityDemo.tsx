"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import styles from "./sme.module.css";

type Horizon = {
  horizon_days: number;
  ending_cash_p10: number;
  ending_cash_p50: number;
  ending_cash_p90: number;
  shortfall_probability: number;
  shortfall_breach_count: number;
  simulated_path_count: number;
  shortfall_probability_ci95_lower: number;
  shortfall_probability_ci95_upper: number;
  expected_min_cash: number;
  min_cash_p10: number;
  min_cash_p50: number;
  p10_buffer_above_floor: number;
  p10_buffer_ratio: number | null;
  cash_flow_at_risk_p50_to_p10: number;
  median_first_breach_day: number | null;
};

type Stress = {
  stress: string;
  shortfall_probability: number;
  ending_cash_p50: number;
  median_first_breach_day: number | null;
};

type CompanyMatch = {
  business_no: string;
  name: string;
  status: string;
  capital: number | null;
  paid_in_capital: number | null;
  location: string;
};

type EstimateRange = {
  low: number;
  mid: number;
  high: number;
  unit: "TWD" | "days" | "percent";
};

type CompanyProfile = {
  official: {
    business_no: string;
    company_name: string;
    status: string;
    capital_stock_amount: number | null;
    paid_in_capital_amount: number | null;
    location: string;
    setup_date: string;
    register_organization: string;
    business_items: string[];
    source: string;
  };
  inferred: {
    industry: {
      label: string;
      confidence: number;
      reason: string;
    };
  };
  market?: {
    public_company: {
      company_code?: string;
      company_name?: string;
      industry?: string;
      market_type?: string;
      source?: string;
    } | null;
    recommended_data_route: "PUBLIC_FINANCIAL_STATEMENTS" | "SME_ESTIMATE_OR_PRIVATE_DATA";
    checked_sources?: string[];
  };
  provenance?: {
    retrieved_at: string;
    public_sources: Array<{ id: string; role: string }>;
    estimate_model: string;
    industry_confidence: number;
    sme_capital_criterion_twd: number;
    sme_employee_alternative_criterion: string;
    sme_rule_source: string;
    public_data_cache_seconds: number;
  };
  estimate: {
    basis: string;
    disclaimer: string;
    fields: {
      current_cash: EstimateRange;
      safety_cash_floor: EstimateRange;
      avg_monthly_inflow: EstimateRange;
      monthly_fixed_outflow: EstimateRange;
      monthly_payroll: EstimateRange;
      largest_receivable_amount: EstimateRange;
      largest_receivable_due_days: EstimateRange;
      receivable_delay_mean_days: EstimateRange;
      largest_payable_amount: EstimateRange;
      largest_payable_due_days: EstimateRange;
      fx_receivable_share_percent: EstimateRange;
      income_volatility: "low" | "medium" | "high";
    };
  };
  quick_estimate_eligibility: {
    status: "ELIGIBLE" | "CAUTION" | "NOT_RECOMMENDED";
    can_run_quick_estimate: boolean;
    requires_human_confirmation: boolean;
    reasons: string[];
  };
};

type AdjustmentRecommendation = {
  code: string;
  title: string;
  rationale: string;
  before_shortfall_probability: number;
  after_shortfall_probability: number;
  improvement_percentage_points: number;
  ending_cash_p50_before: number;
  ending_cash_p50_after: number;
  ending_cash_p50_change: number;
};

type Forecast = {
  profile: {
    name: string;
    industry: string;
    description: string;
    current_cash: number;
    safety_cash_floor: number;
  };
  engine: {
    version: string;
    probabilistic: boolean;
    simulations: number;
    seed: number;
    input_fingerprint: string;
    horizons: number[];
    data_mode: string;
  };
  horizons: Horizon[];
  stress_tests: Stress[];
  risk_interpretation: {
    status:
      | "ROBUST"
      | "WATCH"
      | "NEAR_THRESHOLD"
      | "STRESS_SENSITIVE"
      | "HIGH_RISK";
    label: string;
    summary: string;
    reasons: string[];
    base_90_probability: number;
    base_90_ci95_upper: number;
    p10_min_cash_90: number | null;
    p10_buffer_above_floor_90: number | null;
    p10_buffer_ratio_90: number | null;
    most_sensitive_stress: string | null;
    most_sensitive_stress_probability: number;
    safety_cash_floor: number;
  };
  drivers: Array<{ driver: string; exposure_amount: number }>;
  rm_next_step: { route: string; reason: string };
  adjustment_recommendations: AdjustmentRecommendation[];
  guardrails: {
    is_credit_decision: boolean;
    is_loan_approval: boolean;
    automatic_product_sale: boolean;
    human_review_required: boolean;
    profile_persisted: boolean;
  };
};

type InputState = {
  company_name: string;
  industry: string;
  current_cash: string;
  safety_cash_floor: string;
  avg_monthly_inflow: string;
  monthly_fixed_outflow: string;
  monthly_payroll: string;
  largest_receivable_amount: string;
  largest_receivable_due_days: string;
  receivable_delay_mean_days: string;
  largest_payable_amount: string;
  largest_payable_due_days: string;
  fx_receivable_share_percent: string;
  income_volatility: "low" | "medium" | "high";
};

const emptyInput: InputState = {
  company_name: "",
  industry: "",
  current_cash: "",
  safety_cash_floor: "",
  avg_monthly_inflow: "",
  monthly_fixed_outflow: "",
  monthly_payroll: "",
  largest_receivable_amount: "",
  largest_receivable_due_days: "30",
  receivable_delay_mean_days: "10",
  largest_payable_amount: "",
  largest_payable_due_days: "35",
  fx_receivable_share_percent: "0",
  income_volatility: "medium",
};

const profiles = [
  { id: "exporter", label: "快速範例 A", meta: "出口製造｜美元應收" },
  { id: "wholesaler", label: "快速範例 B", meta: "批發貿易｜應收集中" },
  { id: "service", label: "快速範例 C", meta: "企業服務｜人事成本高" },
];

const stressLabels: Record<string, string> = {
  major_customer_delay_30d: "最大客戶延遲 30 天",
  revenue_down_15pct: "營收下降 15%",
  twd_strengthens_5pct: "台幣升值 5%",
  combined: "三項同時發生",
};

const privateFields: Array<{
  key: keyof InputState;
  label: string;
  hint: string;
  suffix?: string;
}> = [
  { key: "current_cash", label: "目前現金", hint: "目前可動用現金" },
  { key: "safety_cash_floor", label: "安全現金水位", hint: "低於多少就視為壓力" },
  { key: "avg_monthly_inflow", label: "平均每月入帳", hint: "近幾月平均" },
  { key: "monthly_fixed_outflow", label: "每月固定營運支出", hint: "不含薪資" },
  { key: "monthly_payroll", label: "每月薪資", hint: "固定人事支出" },
  { key: "largest_receivable_amount", label: "最大筆應收帳款", hint: "沒有可填 0" },
  { key: "largest_receivable_due_days", label: "最大應收幾天後到期", hint: "1–180 天", suffix: "天" },
  { key: "receivable_delay_mean_days", label: "平均延遲付款天數", hint: "歷史常晚幾天", suffix: "天" },
  { key: "largest_payable_amount", label: "最大筆應付款", hint: "沒有可填 0" },
  { key: "largest_payable_due_days", label: "最大應付幾天後到期", hint: "1–180 天", suffix: "天" },
  { key: "fx_receivable_share_percent", label: "外幣收入占比", hint: "0–100%", suffix: "%" },
];

function money(value: number) {
  const sign = value < 0 ? "−" : "";
  return `${sign}${Math.abs(value / 10_000).toLocaleString("zh-TW", {
    maximumFractionDigits: 0,
  })} 萬`;
}

function prob(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function probabilityDisplay(item: Horizon) {
  if (item.shortfall_breach_count === 0) {
    return {
      primary: "本次未觀察到",
      secondary: `0 / ${item.simulated_path_count.toLocaleString("zh-TW")} 路徑跌破`,
      uncertainty: `95% 上界約 ${(item.shortfall_probability_ci95_upper * 100).toFixed(2)}%`,
    };
  }

  return {
    primary: prob(item.shortfall_probability),
    secondary: `${item.shortfall_breach_count.toLocaleString("zh-TW")} / ${item.simulated_path_count.toLocaleString("zh-TW")} 路徑跌破`,
    uncertainty: `95% CI ${(item.shortfall_probability_ci95_lower * 100).toFixed(2)}%–${(item.shortfall_probability_ci95_upper * 100).toFixed(2)}%`,
  };
}

function horizonRiskLabel(item: Horizon, stressMax: number) {
  if (item.shortfall_probability >= 0.5) return "高風險";
  if (item.shortfall_probability >= 0.1) return "需注意";
  if (
    typeof item.p10_buffer_ratio === "number" &&
    item.p10_buffer_ratio <= 0.25
  ) {
    return "接近臨界";
  }
  if (
    item.horizon_days === 90 &&
    stressMax >= 0.2 &&
    stressMax >= item.shortfall_probability + 0.15
  ) {
    return "壓力敏感";
  }
  if (item.shortfall_breach_count === 0) return "有緩衝";
  return "低風險";
}

function rangeLabel(range?: EstimateRange) {
  if (!range) return "—";
  if (range.unit === "TWD") {
    return `${money(range.low)} ～ ${money(range.high)}`;
  }
  if (range.unit === "days") {
    return `${range.low}～${range.high} 天`;
  }
  return `${range.low}～${range.high}%`;
}

function round10k(value: number) {
  return Math.max(0, Math.round(value / 10000) * 10000);
}

function fallbackMoneyRange(mid: number): EstimateRange {
  return {
    low: round10k(mid * 0.65),
    mid: round10k(mid),
    high: round10k(mid * 1.35),
    unit: "TWD",
  };
}

function buildFallbackProfile(company: CompanyMatch): CompanyProfile {
  const capital = Math.min(
    300000000,
    Math.max(1000000, company.paid_in_capital ?? company.capital ?? 10000000),
  );
  const monthlyInflow = (capital * 3.5) / 12;
  const fixed = monthlyInflow * 0.55;
  const payroll = monthlyInflow * 0.18;
  const cash = monthlyInflow * 0.6;
  const safety = (fixed + payroll) * 0.45;

  return {
    official: {
      business_no: company.business_no,
      company_name: company.name,
      status: company.status,
      capital_stock_amount: company.capital,
      paid_in_capital_amount: company.paid_in_capital,
      location: company.location,
      setup_date: "",
      register_organization: "",
      business_items: [],
      source: "MOEA_GCIS_SEARCH",
    },
    inferred: {
      industry: {
        label: "一般企業",
        confidence: 0.35,
        reason: "先用公司登記規模建立保守基準；背景取得營業項目後會再自動精修。",
      },
    },
    estimate: {
      basis: "registered_capital_fallback_v1",
      disclaimer:
        "目前先依官方登記資本額建立保守估算；這不是公司真實財務資料。背景取得更多公開資料後會自動精修。",
      fields: {
        current_cash: fallbackMoneyRange(cash),
        safety_cash_floor: fallbackMoneyRange(safety),
        avg_monthly_inflow: fallbackMoneyRange(monthlyInflow),
        monthly_fixed_outflow: fallbackMoneyRange(fixed),
        monthly_payroll: fallbackMoneyRange(payroll),
        largest_receivable_amount: fallbackMoneyRange(monthlyInflow * 0.3),
        largest_receivable_due_days: {
          low: 18,
          mid: 30,
          high: 42,
          unit: "days",
        },
        receivable_delay_mean_days: {
          low: 4,
          mid: 10,
          high: 16,
          unit: "days",
        },
        largest_payable_amount: fallbackMoneyRange(monthlyInflow * 0.25),
        largest_payable_due_days: {
          low: 23,
          mid: 35,
          high: 47,
          unit: "days",
        },
        fx_receivable_share_percent: {
          low: 0,
          mid: 10,
          high: 22,
          unit: "percent",
        },
        income_volatility: "medium",
      },
    },
    quick_estimate_eligibility: {
      status: "CAUTION",
      can_run_quick_estimate: false,
      requires_human_confirmation: true,
      reasons: [
        "正在完成公司類型、公開市場身分與資料完整性檢查；完成前不放行快速估算。",
      ],
    },
  };
}

async function requestForecast(body: Record<string, unknown>): Promise<Forecast> {
  const response = await fetch("/api/sme-liquidity/forecast", {
    method: "POST",
    cache: "no-store",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("forecast unavailable");
  return response.json() as Promise<Forecast>;
}

export default function LiquidityDemo() {
  const [form, setForm] = useState<InputState>(emptyInput);
  const [data, setData] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [companyMatches, setCompanyMatches] = useState<CompanyMatch[]>([]);
  const [companySearching, setCompanySearching] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState<CompanyMatch | null>(null);
  const [companyProfile, setCompanyProfile] = useState<CompanyProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileFailed, setProfileFailed] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  useEffect(() => {
    const query = form.company_name.trim();
    if (!query || selectedCompany?.name === query) {
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setCompanySearching(true);
      try {
        const response = await fetch(
          `/api/sme-liquidity/company-search?q=${encodeURIComponent(query)}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (!response.ok) throw new Error("company search unavailable");
        const payload = (await response.json()) as { results?: CompanyMatch[] };
        setCompanyMatches(payload.results ?? []);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setCompanyMatches([]);
      } finally {
        setCompanySearching(false);
      }
    }, 300);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [form.company_name, selectedCompany]);

  function applyEstimate(profile: CompanyProfile) {
    const fields = profile.estimate.fields;
    setForm((current) => ({
      ...current,
      company_name: profile.official.company_name,
      industry: profile.inferred.industry.label,
      current_cash: String(fields.current_cash.mid),
      safety_cash_floor: String(fields.safety_cash_floor.mid),
      avg_monthly_inflow: String(fields.avg_monthly_inflow.mid),
      monthly_fixed_outflow: String(fields.monthly_fixed_outflow.mid),
      monthly_payroll: String(fields.monthly_payroll.mid),
      largest_receivable_amount: String(fields.largest_receivable_amount.mid),
      largest_receivable_due_days: String(fields.largest_receivable_due_days.mid),
      receivable_delay_mean_days: String(fields.receivable_delay_mean_days.mid),
      largest_payable_amount: String(fields.largest_payable_amount.mid),
      largest_payable_due_days: String(fields.largest_payable_due_days.mid),
      fx_receivable_share_percent: String(fields.fx_receivable_share_percent.mid),
      income_volatility: fields.income_volatility,
    }));
  }

  async function selectCompany(company: CompanyMatch) {
    setSelectedCompany(company);
    setCompanyMatches([]);
    setCompanySearching(false);
    setProfileFailed(false);
    setProfileLoading(true);
    setAdvancedOpen(false);
    setData(null);

    const fallback = buildFallbackProfile(company);
    setCompanyProfile(fallback);
    applyEstimate(fallback);

    try {
      const response = await fetch(
        `/api/sme-liquidity/company-profile?business_no=${encodeURIComponent(company.business_no)}`,
        { cache: "no-store" },
      );
      if (!response.ok) throw new Error("profile unavailable");
      const profile = (await response.json()) as CompanyProfile;
      setCompanyProfile(profile);
      applyEstimate(profile);
    } catch {
      setProfileFailed(true);
    } finally {
      setProfileLoading(false);
    }
  }

  function payloadFromForm() {
    return {
      company_name: form.company_name,
      industry: form.industry || "一般企業",
      current_cash: Number(form.current_cash || 0),
      safety_cash_floor: Number(form.safety_cash_floor || 0),
      avg_monthly_inflow: Number(form.avg_monthly_inflow || 0),
      monthly_fixed_outflow: Number(form.monthly_fixed_outflow || 0),
      monthly_payroll: Number(form.monthly_payroll || 0),
      largest_receivable_amount: Number(form.largest_receivable_amount || 0),
      largest_receivable_due_days: Number(form.largest_receivable_due_days || 30),
      receivable_delay_mean_days: Number(form.receivable_delay_mean_days || 10),
      largest_payable_amount: Number(form.largest_payable_amount || 0),
      largest_payable_due_days: Number(form.largest_payable_due_days || 35),
      fx_receivable_share_percent: Number(form.fx_receivable_share_percent || 0),
      income_volatility: form.income_volatility,
    };
  }

  async function runCustomForecast() {
    setLoading(true);
    setFailed(false);
    setData(null);
    try {
      setData(await requestForecast({ custom_profile: payloadFromForm() }));
      requestAnimationFrame(() =>
        document.getElementById("forecast-result")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        }),
      );
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCustomForecast();
  }

  async function loadPreset(profileId: string) {
    setLoading(true);
    setFailed(false);
    setData(null);
    try {
      setData(await requestForecast({ profile_id: profileId }));
      requestAnimationFrame(() =>
        document.getElementById("forecast-result")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        }),
      );
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  const h90 = useMemo(
    () => data?.horizons.find((item) => item.horizon_days === 90) ?? null,
    [data],
  );

  const maxDriver = useMemo(() => {
    if (!data?.drivers.length) return 1;
    return Math.max(...data.drivers.map((item) => item.exposure_amount), 1);
  }, [data]);

  const maxStressProbability = useMemo(() => {
    if (!data?.stress_tests.length) return 0;
    return Math.max(...data.stress_tests.map((item) => item.shortfall_probability));
  }, [data]);

  const estimateFields = companyProfile?.estimate.fields;

  return (
    <section className={styles.demo} id="demo">
      <div className={styles.demoHeader}>
        <div>
          <span className={styles.kicker}>STEP 1 · 找到公司</span>
          <h2>先找公司，網站查得到的資料全部自己帶。</h2>
          <p>
            選到公司後，系統先抓官方登記資料、推測產業，再建立一份可直接評估的資金估算。
            想更準時才需要補私有財務資料。
          </p>
        </div>
        <div className={styles.outputPromise}>
          <span>最少操作</span>
          <strong>搜尋公司</strong>
          <strong>確認自動資料</strong>
          <strong>按一次快速評估</strong>
        </div>
      </div>

      <div className={styles.quickExamples}>
        <span>只想先看效果？</span>
        {profiles.map((profile) => (
          <button
            key={profile.id}
            type="button"
            onClick={() => void loadPreset(profile.id)}
            disabled={loading}
          >
            <strong>{profile.label}</strong>
            <small>{profile.meta}</small>
          </button>
        ))}
      </div>

      <form className={styles.inputPanel} onSubmit={submit}>
        <div className={styles.inputPanelHead}>
          <div>
            <span>01</span>
            <div>
              <strong>搜尋你的公司</strong>
              <small>來源：經濟部商工行政資料開放平臺</small>
            </div>
          </div>
          <p>輸入一個字即可開始搜尋；選定後不必再輸入公司全名、統編、地址或資本額。</p>
        </div>

        <div className={styles.companyLookupOnly}>
          <label className={`${styles.inputField} ${styles.companySearchField}`}>
            <span>公司名稱</span>
            <div className={styles.companySearchBox}>
              <input
                type="text"
                value={form.company_name}
                autoComplete="off"
                placeholder="例如：台、鴻、統"
                onChange={(event) => {
                  setSelectedCompany(null);
                  setCompanyProfile(null);
                  setProfileFailed(false);
                  setAdvancedOpen(false);
                  setData(null);
                  setCompanyMatches([]);
                  setCompanySearching(false);
                  setForm({
                    ...emptyInput,
                    company_name: event.target.value,
                  });
                }}
                required
              />
              {companySearching && (
                <small className={styles.companySearchState}>搜尋中…</small>
              )}
              {!companySearching && companyMatches.length > 0 && (
                <div className={styles.companySuggestions} role="listbox">
                  {companyMatches.map((company) => (
                    <button
                      key={`${company.business_no}-${company.name}`}
                      type="button"
                      onClick={() => void selectCompany(company)}
                    >
                      <strong>{company.name}</strong>
                      <span>
                        統編 {company.business_no}
                        {company.capital ? ` · 資本額 ${money(company.capital)}` : ""}
                      </span>
                      {company.location && <small>{company.location}</small>}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <small>
              {selectedCompany
                ? `已選：${selectedCompany.name} · 統編 ${selectedCompany.business_no}`
                : "打一個字後會顯示可能公司"}
            </small>
          </label>
        </div>

        {profileLoading && companyProfile && (
          <div className={styles.autoLoading}>
            已可快速評估；背景正在抓更多官方資料，自動精修產業與估算…
          </div>
        )}

        {profileFailed && selectedCompany && companyProfile && (
          <div className={styles.autoWarning}>
            完整營業項目暫時取不到，目前已用公司搜尋取得的官方登記資料＋保守估算，不需要你補填。
          </div>
        )}

        {companyProfile && (
          <>
            <section className={styles.autoProfile}>
              <div className={styles.autoProfileHead}>
                <div>
                  <span className={styles.kicker}>STEP 2 · 已自動完成</span>
                  <h3>{companyProfile.official.company_name}</h3>
                  <p>
                    統編 {companyProfile.official.business_no}
                    {companyProfile.official.status ? ` · ${companyProfile.official.status}` : ""}
                  </p>
                </div>
                <div className={styles.sourceBadges}>
                  <span>官方資料</span>
                  <span>產業推測</span>
                  <span>財務估算</span>
                </div>
              </div>

              <div className={styles.officialGrid}>
                <div>
                  <span>產業</span>
                  <strong>{companyProfile.inferred.industry.label}</strong>
                  <small>{companyProfile.inferred.industry.reason}</small>
                </div>
                <div>
                  <span>登記／實收資本</span>
                  <strong>
                    {money(
                      companyProfile.official.paid_in_capital_amount ??
                        companyProfile.official.capital_stock_amount ??
                        0,
                    )}
                  </strong>
                  <small>官方登記資料</small>
                </div>
                <div>
                  <span>公司所在地</span>
                  <strong>{companyProfile.official.location || "—"}</strong>
                  <small>官方登記資料</small>
                </div>
                <div>
                  <span>營業項目</span>
                  <strong>
                    {companyProfile.official.business_items.slice(0, 2).join("、") || "—"}
                  </strong>
                  <small>
                    {companyProfile.official.business_items.length > 2
                      ? `另有 ${companyProfile.official.business_items.length - 2} 項`
                      : "官方登記資料"}
                  </small>
                </div>
              </div>

              {companyProfile.quick_estimate_eligibility.status === "NOT_RECOMMENDED" ? (
                <div className={styles.outOfScopePanel}>
                  <span>已停止 SME 快速估算</span>
                  <strong>
                    {companyProfile.market?.recommended_data_route === "PUBLIC_FINANCIAL_STATEMENTS"
                      ? "此競賽版不對公開市場公司啟用 SME 快速估算"
                      : "這家公司需要更多 SME 身分／真實財務資料"}
                  </strong>
                  <p>
                    系統不展示資本額 heuristic 推出的現金、營收或應收估值，避免製造假精準；完整產品應改接公開財報資料後另行建模。
                  </p>
                  {companyProfile.market?.public_company?.company_code && (
                    <small>
                      官方市場辨識：{companyProfile.market.public_company.company_code}
                      {companyProfile.market.public_company.company_name
                        ? ` · ${companyProfile.market.public_company.company_name}`
                        : ""}
                    </small>
                  )}
                </div>
              ) : (
                <div className={styles.quickEstimate}>
                  <div>
                    <span>網站先幫你估</span>
                    <strong>可直接開始，不必先填 11 個財務欄位</strong>
                    <p>{companyProfile.estimate.disclaimer}</p>
                  </div>
                  <div className={styles.estimateSummary}>
                    <div>
                      <span>月入帳估算</span>
                      <strong>{money(estimateFields?.avg_monthly_inflow.mid ?? 0)}</strong>
                      <small>{rangeLabel(estimateFields?.avg_monthly_inflow)}</small>
                    </div>
                    <div>
                      <span>目前現金估算</span>
                      <strong>{money(estimateFields?.current_cash.mid ?? 0)}</strong>
                      <small>{rangeLabel(estimateFields?.current_cash)}</small>
                    </div>
                    <div>
                      <span>每月薪資估算</span>
                      <strong>{money(estimateFields?.monthly_payroll.mid ?? 0)}</strong>
                      <small>{rangeLabel(estimateFields?.monthly_payroll)}</small>
                    </div>
                    <div>
                      <span>最大應收估算</span>
                      <strong>{money(estimateFields?.largest_receivable_amount.mid ?? 0)}</strong>
                      <small>{rangeLabel(estimateFields?.largest_receivable_amount)}</small>
                    </div>
                  </div>
                </div>
              )}

              <div
                className={`${styles.eligibilityGate} ${styles[`eligibility_${companyProfile.quick_estimate_eligibility.status}`] ?? ""}`}
              >
                <div>
                  <span>快速估算適用性</span>
                  <strong>
                    {companyProfile.quick_estimate_eligibility.status === "ELIGIBLE"
                      ? "可先使用"
                      : companyProfile.quick_estimate_eligibility.status === "CAUTION"
                        ? "可用，但需注意"
                        : "不建議直接使用"}
                  </strong>
                </div>
                <ul>
                  {companyProfile.quick_estimate_eligibility.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>

              <div className={styles.quickActionBar}>
                <div>
                  <span>最快路徑</span>
                  <strong>直接用公開資料＋產業／規模估算先跑一次</strong>
                </div>
                <button
                  type="button"
                  onClick={() => void runCustomForecast()}
                  disabled={
                    loading ||
                    profileLoading ||
                    companyProfile.quick_estimate_eligibility.can_run_quick_estimate === false
                  }
                >
                  {loading
                    ? "正在評估…"
                    : profileLoading
                      ? "正在驗證公司資料…"
                      : companyProfile.quick_estimate_eligibility.can_run_quick_estimate
                        ? "開始快速情境篩檢"
                        : "此公司尚未通過快速估算 Gate"}
                </button>
              </div>
            </section>

            <section className={styles.precisionPanel}>
              <button
                type="button"
                className={styles.precisionToggle}
                onClick={() => setAdvancedOpen((current) => !current)}
              >
                <span>想讓結果更準？</span>
                <strong>
                  {advancedOpen ? "收起私有財務校正" : "補充／修正私有財務資料"}
                </strong>
              </button>

              {advancedOpen && (
                <>
                  <div className={styles.precisionNotice}>
                    <strong>只有公開查不到的資料才需要你確認。</strong>
                    <p>
                      下方已先填入產業／公司規模估算。若你知道真實數字，直接覆蓋即可；
                      不知道就保留估算值。
                    </p>
                  </div>

                  <div className={styles.inputGrid}>
                    {privateFields.map((field) => {
                      const estimate =
                        field.key in (estimateFields ?? {})
                          ? (estimateFields as unknown as Record<string, EstimateRange>)[field.key]
                          : undefined;
                      return (
                        <label key={field.key} className={styles.inputField}>
                          <span>{field.label}</span>
                          <input
                            type="number"
                            min="0"
                            value={form[field.key]}
                            onChange={(event) =>
                              setForm((current) => ({
                                ...current,
                                [field.key]: event.target.value,
                              }))
                            }
                            required
                          />
                          <small>
                            {estimate
                              ? `系統估算常見範圍：${rangeLabel(estimate)}`
                              : field.hint}
                          </small>
                        </label>
                      );
                    })}
                    <label className={styles.inputField}>
                      <span>收入波動程度</span>
                      <select
                        value={form.income_volatility}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            income_volatility: event.target.value as InputState["income_volatility"],
                          }))
                        }
                      >
                        <option value="low">低</option>
                        <option value="medium">中</option>
                        <option value="high">高</option>
                      </select>
                      <small>系統已依產業先帶入，可手動修正</small>
                    </label>
                  </div>

                  <div className={styles.submitBar}>
                    <div>
                      <span>精準模式</span>
                      <strong>用你修正後的私有財務數字重新評估</strong>
                    </div>
                    <button type="submit" disabled={loading}>
                      {loading ? "正在重算…" : "用修正資料重新評估"}
                    </button>
                  </div>
                </>
              )}
            </section>
          </>
        )}
      </form>

      {failed && (
        <div className={styles.statePanel}>
          資料未通過檢查或模型暫時不可用。請稍後重試，或展開精準模式確認數字。
        </div>
      )}

      {!data && !loading && !failed && !companyProfile && (
        <div className={styles.emptyResult}>
          <span>還沒開始</span>
          <h3>先在上面搜尋公司。</h3>
          <p>選到公司後，能自動查的資料會全部先幫你帶進來。</p>
        </div>
      )}

      {data && (
        <div id="forecast-result" className={styles.resultSection}>
          <div className={styles.resultIntro}>
            <div>
              <span className={styles.kicker}>你的情境篩檢結果</span>
              <h2>{data.profile.name} 的 90 天資金壓力報告</h2>
              <p>
                這不是核貸結果，而是未來資金壓力情境篩檢。快速模式使用公開資料＋scenario prior；
                若補入企業真實私有數據，可進一步提高準確度。
              </p>
            </div>
            <div className={styles.engineSeal}>
              <span>ENGINE</span>
              <strong>{data.engine.version}</strong>
              <small>{data.engine.simulations.toLocaleString("zh-TW")} paths · seed {data.engine.seed}</small>
              <small>fingerprint {data.engine.input_fingerprint.slice(0, 12)}</small>
              <small>即時計算 · 不保存輸入</small>
            </div>
          </div>

          <div className={styles.companyBar}>
            <div>
              <span>企業</span>
              <strong>{data.profile.name}</strong>
              <small>{data.profile.industry}</small>
            </div>
            <p>{data.profile.description}</p>
            <div className={styles.cashNow}>
              <span>目前現金</span>
              <strong>{money(data.profile.current_cash)}</strong>
              <small>安全水位 {money(data.profile.safety_cash_floor)}</small>
            </div>
          </div>

          <div className={styles.horizonGrid}>
            {data.horizons.map((item) => {
              const display = probabilityDisplay(item);
              const label = horizonRiskLabel(item, maxStressProbability);
              const riskClass =
                label === "高風險"
                  ? styles.riskHigh
                  : label === "需注意" ||
                      label === "接近臨界" ||
                      label === "壓力敏感"
                    ? styles.riskMid
                    : styles.riskLow;

              return (
                <article key={item.horizon_days}>
                  <div className={styles.horizonTop}>
                    <span>{item.horizon_days} 天</span>
                    <strong className={riskClass}>{label}</strong>
                  </div>
                  <h3 className={styles.probabilityPrimary}>{display.primary}</h3>
                  <p>期間內跌破安全現金水位</p>
                  <div className={styles.probabilityEvidence}>
                    <span>{display.secondary}</span>
                    <strong>{display.uncertainty}</strong>
                  </div>
                  <dl>
                    <div><dt>悲觀期末 P10</dt><dd>{money(item.ending_cash_p10)}</dd></div>
                    <div><dt>悲觀最低現金 P10</dt><dd>{money(item.min_cash_p10)}</dd></div>
                    <div><dt>安全水位緩衝</dt><dd>{money(item.p10_buffer_above_floor)}</dd></div>
                    <div><dt>P50→P10 下行差距</dt><dd>{money(item.cash_flow_at_risk_p50_to_p10)}</dd></div>
                  </dl>
                </article>
              );
            })}
          </div>

          <section
            className={`${styles.dynamicInterpretation} ${styles[`interpretation_${data.risk_interpretation.status}`] ?? ""}`}
          >
            <div className={styles.dynamicInterpretationHead}>
              <div>
                <span>動態判讀</span>
                <h3>{data.risk_interpretation.label}</h3>
              </div>
              <p>{data.risk_interpretation.summary}</p>
            </div>
            <ul>
              {data.risk_interpretation.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </section>

          <div className={styles.analysisGrid}>
            <section>
              <div className={styles.panelLabel}>
                <span>04</span>
                <strong>如果事情變差，風險會變多少？</strong>
              </div>
              <div className={styles.stressList}>
                <div className={styles.stressBase}>
                  <span>正常情境 / 90 天</span>
                  <strong>{h90 ? prob(h90.shortfall_probability) : "—"}</strong>
                </div>
                {data.stress_tests.map((stress) => (
                  <div key={stress.stress}>
                    <span>{stressLabels[stress.stress] ?? stress.stress}</span>
                    <strong>{prob(stress.shortfall_probability)}</strong>
                    <small>
                      P50 {money(stress.ending_cash_p50)}
                      {stress.median_first_breach_day
                        ? ` · 常見首次跌破約第 ${stress.median_first_breach_day} 天`
                        : " · 多數路徑未跌破"}
                    </small>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className={styles.panelLabel}>
                <span>05</span>
                <strong>主要曝險集中在哪裡？</strong>
              </div>
              <p className={styles.driverDisclaimer}>
                依金額與延遲／固定負擔曝險排序，用於協助 RM 排查；這不是因果歸因、SHAP 值或授信風險權重。
              </p>
              <div className={styles.driverList}>
                {data.drivers.slice(0, 5).map((driver) => (
                  <div key={driver.driver}>
                    <div>
                      <span>{driver.driver}</span>
                      <strong>{money(driver.exposure_amount)}</strong>
                    </div>
                    <div className={styles.driverTrack}>
                      <span
                        style={{
                          width: `${Math.max(
                            4,
                            (driver.exposure_amount / maxDriver) * 100,
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>

          {data.adjustment_recommendations?.length > 0 && (
            <section className={styles.adjustmentPanel}>
              <div className={styles.adjustmentHead}>
                <div>
                  <span className={styles.kicker}>可以怎麼調整？</span>
                  <h3>不只告訴你有風險，直接重跑「如果這樣做」的結果。</h3>
                  <p>
                    以下使用相同隨機種子做反事實壓力測試，是模型估計，不是保證效果。
                  </p>
                </div>
              </div>
              <div className={styles.adjustmentGrid}>
                {data.adjustment_recommendations.map((item, index) => (
                  <article key={item.code}>
                    <div className={styles.adjustmentRank}>0{index + 1}</div>
                    <h4>{item.title}</h4>
                    <p>{item.rationale}</p>
                    <div className={styles.adjustmentImpact}>
                      <div>
                        <span>調整前</span>
                        <strong>{prob(item.before_shortfall_probability)}</strong>
                      </div>
                      <span aria-hidden="true">→</span>
                      <div>
                        <span>調整後</span>
                        <strong>{prob(item.after_shortfall_probability)}</strong>
                      </div>
                    </div>
                    <div className={styles.adjustmentBenefit}>
                      {item.improvement_percentage_points > 0
                        ? `缺口機率估計降低 ${item.improvement_percentage_points.toFixed(1)} 個百分點`
                        : `90 天 P50 現金估計增加 ${money(item.ending_cash_p50_change)}`}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}

          <section className={styles.rmPanel}>
            <div>
              <span>銀行端下一步</span>
              <h3>{data.rm_next_step.route}</h3>
              <p>{data.rm_next_step.reason}</p>
            </div>
            <div className={styles.rmRules}>
              <span>AI 可以</span>
              <strong>預警 · 解釋 · 排序待聯絡客戶</strong>
              <span>AI 不可以</span>
              <strong>自動核貸 · 自動賣商品 · 取代理專決策</strong>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
