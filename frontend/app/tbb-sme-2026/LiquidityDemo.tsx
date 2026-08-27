"use client";

import { useEffect, useMemo, useState } from "react";
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
    synthetic_data_only: boolean;
  };
};

const profiles = [
  { id: "exporter", label: "宏昇精密", meta: "出口製造｜美元應收" },
  { id: "wholesaler", label: "海岳商貿", meta: "批發貿易｜應收集中" },
  { id: "service", label: "沐光數位", meta: "企業服務｜人事成本高" },
];

const stressLabels: Record<string, string> = {
  major_customer_delay_30d: "最大客戶延遲 30 天",
  revenue_down_15pct: "營收下降 15%",
  twd_strengthens_5pct: "台幣升值 5%",
  combined: "三項同時發生",
};

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

export default function LiquidityDemo() {
  const [profileId, setProfileId] = useState("exporter");
  const [data, setData] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFailed(false);

    fetch("/api/sme-liquidity/forecast", {
      method: "POST",
      cache: "no-store",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify({ profile_id: profileId }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("forecast unavailable");
        return (await response.json()) as Forecast;
      })
      .then((payload) => setData(payload))
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setFailed(true);
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [profileId]);

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
          <span className={styles.kicker}>LIVE PROBABILISTIC DEMO</span>
          <h2>現在帳上有錢，不代表 90 天後安全。</h2>
          <p>
            這個 Demo 使用合成企業資料。系統不是預測一個「神準數字」，
            而是估計未來現金分布、跌破安全水位的機率，以及壓力情境下的變化。
          </p>
        </div>
        {data && (
          <div className={styles.engineSeal}>
            <span>ENGINE</span>
            <strong>{data.engine.version}</strong>
            <small>{data.engine.simulations.toLocaleString("zh-TW")} paths</small>
          </div>
        )}
      </div>

      <div className={styles.profileTabs}>
        {profiles.map((profile) => (
          <button
            key={profile.id}
            type="button"
            onClick={() => setProfileId(profile.id)}
            className={profile.id === profileId ? styles.profileActive : styles.profileButton}
          >
            <strong>{profile.label}</strong>
            <span>{profile.meta}</span>
          </button>
        ))}
      </div>

      {loading && <div className={styles.statePanel}>正在跑 30 / 60 / 90 天機率式模擬…</div>}
      {failed && <div className={styles.statePanel}>模型暫時不可用，系統不補假結果。</div>}

      {!loading && !failed && data && (
        <>
          <div className={styles.companyBar}>
            <div>
              <span>企業情境</span>
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
                  <span>{item.horizon_days} DAYS</span>
                  <strong className={
                    item.shortfall_probability >= 0.5
                      ? styles.riskHigh
                      : item.shortfall_probability >= 0.2
                        ? styles.riskMid
                        : styles.riskLow
                  }>
                    {riskLabel(item.shortfall_probability)}
                  </strong>
                </div>
                <h3>{prob(item.shortfall_probability)}</h3>
                <p>期間內跌破安全現金水位機率</p>
                <dl>
                  <div><dt>悲觀 P10</dt><dd>{money(item.ending_cash_p10)}</dd></div>
                  <div><dt>中位 P50</dt><dd>{money(item.ending_cash_p50)}</dd></div>
                  <div><dt>樂觀 P90</dt><dd>{money(item.ending_cash_p90)}</dd></div>
                  <div><dt>Cash-flow-at-Risk</dt><dd>{money(item.cash_flow_at_risk_p50_to_p10)}</dd></div>
                </dl>
              </article>
            ))}
          </div>

          <div className={styles.analysisGrid}>
            <section>
              <div className={styles.panelLabel}>
                <span>01</span>
                <strong>壓力測試</strong>
              </div>
              <div className={styles.stressList}>
                <div className={styles.stressBase}>
                  <span>BASE / 90 天</span>
                  <strong>{h90 ? prob(h90.shortfall_probability) : "—"}</strong>
                </div>
                {data.stress_tests.map((stress) => (
                  <div key={stress.stress}>
                    <span>{stressLabels[stress.stress] ?? stress.stress}</span>
                    <strong>{prob(stress.shortfall_probability)}</strong>
                    <small>
                      P50 {money(stress.ending_cash_p50)}
                      {stress.median_first_breach_day
                        ? ` · 中位首次跌破第 ${stress.median_first_breach_day} 天`
                        : " · 多數路徑未跌破"}
                    </small>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className={styles.panelLabel}>
                <span>02</span>
                <strong>主要現金流暴露</strong>
              </div>
              <div className={styles.driverList}>
                {data.drivers.slice(0, 5).map((driver) => (
                  <div key={driver.driver}>
                    <div>
                      <span>{driver.driver}</span>
                      <strong>{money(driver.exposure_amount)}</strong>
                    </div>
                    <div className={styles.driverTrack}>
                      <span style={{ width: `${Math.max(4, (driver.exposure_amount / maxDriver) * 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className={styles.rmPanel}>
            <div>
              <span>03 · RM NEXT BEST ACTION</span>
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
        </>
      )}
    </section>
  );
}
