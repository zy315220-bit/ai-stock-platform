"use client";

import { FormEvent, useState } from "react";

import styles from "./tbb.module.css";

type Decision = {
  risk_code: string;
  risk_name: string;
  risk_score: number;
  max_research_drawdown_percent: number;
  per_trade_risk_budget_percent: number;
  human_review_required: boolean;
  blocked_capabilities: string[];
  governance: {
    pii_collected: boolean;
    execution_authority: boolean;
    final_holdout_interactive_access: boolean;
    fail_closed: boolean;
  };
};

type FormState = {
  loss_tolerance: number;
  investment_horizon: number;
  liquidity_need: number;
  investment_experience: number;
};

const DEFAULT_FORM: FormState = {
  loss_tolerance: 2,
  investment_horizon: 3,
  liquidity_need: 2,
  investment_experience: 2,
};

const fields = [
  { key: "loss_tolerance" as const, label: "可承受虧損", options: ["極低", "低", "中", "高"] },
  { key: "investment_horizon" as const, label: "投資期間", options: ["< 1 年", "1–3 年", "3–7 年", "7 年以上"] },
  { key: "liquidity_need" as const, label: "流動性需求", options: ["低", "中低", "中高", "高"] },
  { key: "investment_experience" as const, label: "投資經驗", options: ["初次", "基礎", "熟悉", "進階"] },
];

export default function SuitabilityDemo() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("loading");

    try {
      const response = await fetch("/api/tbb-wealth/suitability", {
        method: "POST",
        cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!response.ok) throw new Error("request failed");
      setDecision((await response.json()) as Decision);
      setStatus("idle");
    } catch {
      setDecision(null);
      setStatus("error");
    }
  }

  return (
    <section className={styles.demoShell} id="demo" aria-labelledby="demo-title">
      <div className={styles.demoHeader}>
        <div>
          <span className={styles.eyebrow}>LIVE PROTOTYPE</span>
          <h2 id="demo-title">先定風險邊界，再允許 AI 研究。</h2>
        </div>
        <span className={styles.liveBadge}>READ-ONLY</span>
      </div>

      <div className={styles.demoGrid}>
        <form className={styles.formPanel} onSubmit={submit}>
          <p className={styles.panelLabel}>01 / 客戶風險邊界</p>

          {fields.map((field) => (
            <label className={styles.field} key={field.key}>
              <span>{field.label}</span>
              <select
                value={form[field.key]}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    [field.key]: Number(event.target.value),
                  }))
                }
              >
                {field.options.map((option, index) => (
                  <option value={index + 1} key={option}>{option}</option>
                ))}
              </select>
            </label>
          ))}

          <p className={styles.privacyNote}>
            此 Demo 不要求姓名、身分證、帳號或資產明細。額外欄位會被後端拒絕。
          </p>

          <button className={styles.primaryButton} type="submit" disabled={status === "loading"}>
            {status === "loading" ? "計算風險邊界…" : "建立研究權限"}
          </button>

          {status === "error" ? (
            <p className={styles.errorText}>服務暫時無法連線，系統未產生任何建議。</p>
          ) : null}
        </form>

        <div className={styles.resultPanel} aria-live="polite">
          <p className={styles.panelLabel}>02 / AI 研究權限</p>

          {decision ? (
            <>
              <div className={styles.riskHeadline}>
                <span>{decision.risk_code}</span>
                <strong>{decision.risk_name}</strong>
              </div>

              <dl className={styles.metricList}>
                <div><dt>研究最大回撤上限</dt><dd>{decision.max_research_drawdown_percent}%</dd></div>
                <div><dt>單筆風險預算</dt><dd>{decision.per_trade_risk_budget_percent}%</dd></div>
                <div><dt>人工覆核</dt><dd>{decision.human_review_required ? "必要" : "否"}</dd></div>
                <div><dt>自動下單權限</dt><dd>{decision.governance.execution_authority ? "有" : "無"}</dd></div>
              </dl>

              <div className={styles.ruleBlock}>
                <p>系統強制禁止</p>
                <ul>
                  {decision.blocked_capabilities.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </>
          ) : (
            <div className={styles.emptyState}>
              <span>WAITING FOR INPUT</span>
              <p>預設不產生推薦。完成左側非個資問卷後，才建立 Research Lab 可使用的風險邊界。</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
