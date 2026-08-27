"use client";

import { FormEvent, useMemo, useState } from "react";
import styles from "./sme.module.css";

type Horizon = {
  horizon_days: number;
  ending_cash_p10: number;
  ending_cash_p50: number;
  ending_cash_p90: number;
  shortfall_probability: number;
  expected_min_cash: number;
  cash_flow_at_risk_p50_to_p10: number;
  median_first_breach_day: number | null;
};

type Stress = {
  stress: string;
  shortfall_probability: number;
  ending_cash_p50: number;
  median_first_breach_day: number | null;
};

type Forecast = {
  profile: {
    id: string;
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
    horizons: number[];
    data_mode: string;
  };
  horizons: Horizon[];
  stress_tests: Stress[];
  drivers: Array<{ driver: string; exposure_amount: number }>;
  rm_next_step: { route: string; reason: string };
  guardrails: {
    is_credit_decision: boolean;
    is_loan_approval: boolean;
    automatic_product_sale: boolean;
    human_review_required: boolean;
    profile_persisted?: boolean;
    synthetic_data_only: boolean;
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

const defaultInput: InputState = {
  company_name: "宏昇精密",
  industry: "出口製造",
  current_cash: "4200000",
  safety_cash_floor: "1200000",
  avg_monthly_inflow: "2760000",
  monthly_fixed_outflow: "2460000",
  monthly_payroll: "920000",
  largest_receivable_amount: "2100000",
  largest_receivable_due_days: "28",
  receivable_delay_mean_days: "11",
  largest_payable_amount: "1350000",
  largest_payable_due_days: "42",
  fx_receivable_share_percent: "55",
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

const inputFields: Array<{
  key: keyof InputState;
  label: string;
  hint: string;
  type?: "text" | "number";
}> = [
  { key: "company_name", label: "公司名稱", hint: "Demo 名稱即可", type: "text" },
  { key: "industry", label: "產業", hint: "例如出口製造", type: "text" },
  { key: "current_cash", label: "目前現金", hint: "目前可動用現金", type: "number" },
  { key: "safety_cash_floor", label: "安全現金水位", hint: "低於多少就視為壓力", type: "number" },
  { key: "avg_monthly_inflow", label: "平均每月入帳", hint: "近幾月平均", type: "number" },
  { key: "monthly_fixed_outflow", label: "每月固定營運支出", hint: "不含薪資", type: "number" },
  { key: "monthly_payroll", label: "每月薪資", hint: "固定人事支出", type: "number" },
  { key: "largest_receivable_amount", label: "最大筆應收帳款", hint: "沒有可填 0", type: "number" },
  { key: "largest_receivable_due_days", label: "最大應收幾天後到期", hint: "1–180 天", type: "number" },
  { key: "receivable_delay_mean_days", label: "平均延遲付款天數", hint: "歷史常晚幾天", type: "number" },
  { key: "largest_payable_amount", label: "最大筆應付款", hint: "沒有可填 0", type: "number" },
  { key: "largest_payable_due_days", label: "最大應付幾天後到期", hint: "1–180 天", type: "number" },
  { key: "fx_receivable_share_percent", label: "外幣收入占比", hint: "0–100%", type: "number" },
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

function riskLabel(value: number) {
  if (value >= 0.5) return "高風險";
  if (value >= 0.2) return "需注意";
  return "穩定";
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
  const [form, setForm] = useState<InputState>(defaultInput);
  const [data, setData] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setFailed(false);
    setData(null);

    try {
      const payload = {
        company_name: form.company_name,
        industry: form.industry,
        current_cash: Number(form.current_cash),
        safety_cash_floor: Number(form.safety_cash_floor),
        avg_monthly_inflow: Number(form.avg_monthly_inflow),
        monthly_fixed_outflow: Number(form.monthly_fixed_outflow),
        monthly_payroll: Number(form.monthly_payroll),
        largest_receivable_amount: Number(form.largest_receivable_amount),
        largest_receivable_due_days: Number(form.largest_receivable_due_days),
        receivable_delay_mean_days: Number(form.receivable_delay_mean_days),
        largest_payable_amount: Number(form.largest_payable_amount),
        largest_payable_due_days: Number(form.largest_payable_due_days),
        fx_receivable_share_percent: Number(form.fx_receivable_share_percent),
        income_volatility: form.income_volatility,
      };
      setData(await requestForecast({ custom_profile: payload }));
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

  return (
    <section className={styles.demo} id="demo">
      <div className={styles.demoHeader}>
        <div>
          <span className={styles.kicker}>STEP 1 · 輸入企業資料</span>
          <h2>先告訴系統「現在的錢怎麼進、怎麼出」。</h2>
          <p>
            不需要上傳帳戶或身分證。競賽 PoC 只用這些現金流欄位，即時計算後不保存。
            不想自己填，也可以先按下方三個快速範例。
          </p>
        </div>
        <div className={styles.outputPromise}>
          <span>你最後會得到</span>
          <strong>30 / 60 / 90 天缺口機率</strong>
          <strong>4 種壓力測試</strong>
          <strong>主要風險原因 + RM 下一步</strong>
        </div>
      </div>

      <div className={styles.quickExamples}>
        <span>不想填？先看範例</span>
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
              <strong>企業資金輸入</strong>
              <small>金額單位：新台幣元</small>
            </div>
          </div>
          <p>先用粗粒度數字即可。正式銀行版可由企業網銀、ERP 或銀行內部資料自動帶入。</p>
        </div>

        <div className={styles.inputGrid}>
          {inputFields.map((field) => (
            <label key={field.key} className={styles.inputField}>
              <span>{field.label}</span>
              <input
                type={field.type ?? "number"}
                min={field.type === "number" ? "0" : undefined}
                value={form[field.key]}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    [field.key]: event.target.value,
                  }))
                }
                required
              />
              <small>{field.hint}</small>
            </label>
          ))}
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
            <small>影響 Monte Carlo 每日入帳波動</small>
          </label>
        </div>

        <div className={styles.submitBar}>
          <div>
            <span>STEP 2</span>
            <strong>系統會跑 {new Intl.NumberFormat("zh-TW").format(2500)} 條 90 天現金路徑</strong>
          </div>
          <button type="submit" disabled={loading}>
            {loading ? "正在評估…" : "開始 90 天資金壓力評估"}
          </button>
        </div>
      </form>

      {failed && (
        <div className={styles.statePanel}>
          輸入資料未通過檢查或模型暫時不可用。請確認安全水位、到期天數與百分比是否合理。
        </div>
      )}

      {!data && !loading && !failed && (
        <div className={styles.emptyResult}>
          <span>STEP 3 · 尚未開始</span>
          <h3>完成上方輸入後，評估結果會出現在這裡。</h3>
          <p>不會寄 Email；目前是當頁即時計算、即時顯示。</p>
        </div>
      )}

      {data && (
        <div id="forecast-result" className={styles.resultSection}>
          <div className={styles.resultIntro}>
            <div>
              <span className={styles.kicker}>STEP 3 · 你的評估結果</span>
              <h2>{data.profile.name} 的 90 天資金壓力報告</h2>
              <p>
                這不是核貸結果，而是「未來資金壓力預警」。
                數字越高，代表模擬路徑中有越多情境會跌破你設定的安全現金水位。
              </p>
            </div>
            <div className={styles.engineSeal}>
              <span>ENGINE</span>
              <strong>{data.engine.version}</strong>
              <small>{data.engine.simulations.toLocaleString("zh-TW")} paths</small>
              <small>
                {data.engine.data_mode === "user_supplied_demo"
                  ? "你剛輸入的資料 · 不保存"
                  : "合成範例資料"}
              </small>
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
            {data.horizons.map((item) => (
              <article key={item.horizon_days}>
                <div className={styles.horizonTop}>
                  <span>{item.horizon_days} 天後</span>
                  <strong
                    className={
                      item.shortfall_probability >= 0.5
                        ? styles.riskHigh
                        : item.shortfall_probability >= 0.2
                          ? styles.riskMid
                          : styles.riskLow
                    }
                  >
                    {riskLabel(item.shortfall_probability)}
                  </strong>
                </div>
                <h3>{prob(item.shortfall_probability)}</h3>
                <p>期間內跌破安全現金水位機率</p>
                <dl>
                  <div><dt>悲觀情境 P10</dt><dd>{money(item.ending_cash_p10)}</dd></div>
                  <div><dt>中位情境 P50</dt><dd>{money(item.ending_cash_p50)}</dd></div>
                  <div><dt>樂觀情境 P90</dt><dd>{money(item.ending_cash_p90)}</dd></div>
                  <div><dt>Cash-flow-at-Risk</dt><dd>{money(item.cash_flow_at_risk_p50_to_p10)}</dd></div>
                </dl>
              </article>
            ))}
          </div>

          <div className={styles.resultMeaning}>
            <span>這三張卡怎麼看？</span>
            <p>
              例如「90 天 54%」不是說公司一定會缺錢，而是 2,500 條模擬未來中，
              約 54% 曾跌破安全水位。這讓銀行可以提前聯絡，而不是等逾期才處理。
            </p>
          </div>

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
                <strong>主要資金壓力從哪裡來？</strong>
              </div>
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

          <section className={styles.rmPanel}>
            <div>
              <span>STEP 6 · 銀行端會拿到什麼</span>
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
