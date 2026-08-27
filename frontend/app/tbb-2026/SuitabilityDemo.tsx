"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import styles from "./tbb.module.css";

type GoalPriority = "liquidity" | "income" | "growth" | "legacy";

type FormState = {
  loss_tolerance: number;
  investment_horizon: number;
  liquidity_need: number;
  investment_experience: number;
  income_stability: number;
  business_dependency: number;
  wealth_concentration: number;
  goal_priority: GoalPriority;
};

type Decision = {
  risk_code: "R1" | "R2" | "R3" | "R4";
  risk_name: string;
  decision_state: "RESEARCH_ALLOWED" | "REVIEW_REQUIRED";
  risk_score: number;
  willingness_score: number;
  capacity_score: number;
  max_research_drawdown_percent: number;
  per_trade_risk_budget_percent: number;
  human_review_required: boolean;
  service_route: string;
  profile_conflicts: string[];
  explanations: Array<{
    factor: string;
    impact: "supports" | "limits" | "neutral";
    explanation: string;
  }>;
  allocation_envelope: Array<{
    name: string;
    target_percent: number;
    range_low_percent: number;
    range_high_percent: number;
    purpose: string;
  }>;
  stress_checks: Array<{
    scenario: string;
    state: "PASS" | "REVIEW" | "BLOCK";
    observation: string;
    advisor_action: string;
  }>;
  required_advisor_actions: string[];
  blocked_capabilities: string[];
  governance: {
    pii_collected: boolean;
    exact_balance_collected: boolean;
    prototype_persists_profile: boolean;
    execution_authority: boolean;
    payment_authority: boolean;
    final_holdout_interactive_access: boolean;
    human_review_required: boolean;
    fail_closed: boolean;
  };
  audit: {
    model_version: string;
    decision_fingerprint: string;
    decision_rule: string;
    risk_band_before_hard_caps: string;
    hard_caps_applied: string[];
  };
};

type ResearchCandidate = {
  confirmation_gate_pass_count?: number;
  confirmation_gate_total?: number;
  eligible_for_one_shot_holdout?: boolean;
  regime_robust?: boolean;
  walk_forward_sample_sufficient?: boolean;
  walk_forward_positive_slice_ratio?: number;
  validation?: {
    statistical_quality_pass?: boolean;
    deflated_sharpe_pass?: boolean;
  };
  model_selection?: {
    cscv_pbo_pass?: boolean;
    hansen_spa_pass?: boolean;
  };
};

type ResearchStatus = {
  workflow?: {
    status?: string;
    conclusion?: string | null;
    updated_at?: string;
  } | null;
  latest_snapshot?: {
    as_of_date?: string;
    generated_at_utc?: string;
    universe_size?: number;
    completed_symbol_count?: number;
    eligible_candidate_count?: number;
    holdout_opened?: boolean;
    integrity_status?: string;
    training_memory?: {
      unique_experiment_count?: number;
      last_run_new_experiment_count?: number;
      provenance?: string;
      validation_feedback_used?: boolean;
      holdout_feedback_used?: boolean;
    };
    top_candidate?: ResearchCandidate | null;
  } | null;
  system_audit?: {
    system_status?: "OPERATIONAL" | "FAIL_CLOSED";
    passed_check_count?: number;
    failed_check_count?: number;
  } | null;
  certified_robots?: {
    certified_robot_count?: number;
  } | null;
  snapshot_available?: boolean;
};

type RequestState = "idle" | "loading" | "error";

const OWNER_PROFILE: FormState = {
  loss_tolerance: 3,
  investment_horizon: 3,
  liquidity_need: 2,
  investment_experience: 3,
  income_stability: 3,
  business_dependency: 3,
  wealth_concentration: 3,
  goal_priority: "legacy",
};

const presets: Array<{
  id: string;
  label: string;
  detail: string;
  value: FormState;
}> = [
  {
    id: "owner",
    label: "守成企業主",
    detail: "事業與家庭資產連動",
    value: OWNER_PROFILE,
  },
  {
    id: "successor",
    label: "成長接班人",
    detail: "期限長、收入較穩定",
    value: {
      loss_tolerance: 4,
      investment_horizon: 4,
      liquidity_need: 1,
      investment_experience: 3,
      income_stability: 4,
      business_dependency: 2,
      wealth_concentration: 2,
      goal_priority: "growth",
    },
  },
  {
    id: "liquidity",
    label: "資金壓力情境",
    detail: "近期用錢、財富集中",
    value: {
      loss_tolerance: 3,
      investment_horizon: 2,
      liquidity_need: 4,
      investment_experience: 2,
      income_stability: 2,
      business_dependency: 4,
      wealth_concentration: 4,
      goal_priority: "liquidity",
    },
  },
];

const numericFields: Array<{
  key: Exclude<keyof FormState, "goal_priority">;
  label: string;
  note: string;
  options: string[];
}> = [
  {
    key: "loss_tolerance",
    label: "可承受虧損",
    note: "主觀意願",
    options: ["極低", "低", "中", "高"],
  },
  {
    key: "investment_horizon",
    label: "投資期間",
    note: "資金可用期限",
    options: ["<1 年", "1–3 年", "3–7 年", "7 年+"],
  },
  {
    key: "liquidity_need",
    label: "流動性需求",
    note: "近期用錢程度",
    options: ["低", "中低", "中高", "高"],
  },
  {
    key: "investment_experience",
    label: "投資經驗",
    note: "商品理解能力",
    options: ["初次", "基礎", "熟悉", "進階"],
  },
  {
    key: "income_stability",
    label: "收入穩定度",
    note: "企業外替代收入",
    options: ["波動高", "偏波動", "穩定", "很穩定"],
  },
  {
    key: "business_dependency",
    label: "企業收入依賴",
    note: "家庭收入來自事業",
    options: ["低", "中低", "中高", "高"],
  },
  {
    key: "wealth_concentration",
    label: "財富集中於企業",
    note: "只選區間，不填金額",
    options: ["<25%", "25–50%", "50–75%", ">75%"],
  },
];

const goalOptions: Array<{ value: GoalPriority; label: string }> = [
  { value: "liquidity", label: "流動" },
  { value: "income", label: "收益" },
  { value: "growth", label: "成長" },
  { value: "legacy", label: "傳承" },
];

const stressStateClasses: Record<"PASS" | "REVIEW" | "BLOCK", string> = {
  PASS: styles.stressPASS,
  REVIEW: styles.stressREVIEW,
  BLOCK: styles.stressBLOCK,
};

const impactClasses: Record<"supports" | "limits" | "neutral", string> = {
  supports: styles.impactsupports,
  limits: styles.impactlimits,
  neutral: styles.impactneutral,
};

function formatNumber(value?: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 1 });
}

function formatSnapshotTime(value?: string): string {
  if (!value) return "尚無完整快照";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "時間不可用";
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);
}

function researchGateRows(status: ResearchStatus | null) {
  const candidate = status?.latest_snapshot?.top_candidate;
  const walkForwardPass = Boolean(
    candidate?.walk_forward_sample_sufficient &&
      (candidate.walk_forward_positive_slice_ratio ?? 0) >= 0.5,
  );

  return [
    ["獨立 Validation 統計品質", candidate?.validation?.statistical_quality_pass],
    ["Walk-forward 跨期穩定", walkForwardPass],
    ["牛／熊／盤整穩健性", candidate?.regime_robust],
    ["DSR 多重測試修正", candidate?.validation?.deflated_sharpe_pass],
    ["CSCV／PBO 過擬合檢驗", candidate?.model_selection?.cscv_pbo_pass],
    ["Hansen SPA 優越性檢驗", candidate?.model_selection?.hansen_spa_pass],
    ["一次性 Final Holdout 資格", candidate?.eligible_for_one_shot_holdout],
  ] as const;
}

async function requestDecision(
  nextForm: FormState,
  signal: AbortSignal,
): Promise<Decision> {
  const response = await fetch("/api/tbb-wealth/suitability", {
    method: "POST",
    cache: "no-store",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
    },
    body: JSON.stringify(nextForm),
    signal,
  });
  if (!response.ok) throw new Error("request failed");
  return response.json() as Promise<Decision>;
}

function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === "AbortError";
}

export default function SuitabilityDemo() {
  const [form, setForm] = useState<FormState>(OWNER_PROFILE);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [requestState, setRequestState] = useState<RequestState>("loading");
  const [researchStatus, setResearchStatus] = useState<ResearchStatus | null>(null);
  const [researchUnavailable, setResearchUnavailable] = useState(false);
  const decisionRequest = useRef<AbortController | null>(null);

  const evaluate = useCallback(async (nextForm: FormState) => {
    decisionRequest.current?.abort();
    const controller = new AbortController();
    decisionRequest.current = controller;
    setRequestState("loading");

    try {
      const payload = await requestDecision(nextForm, controller.signal);
      setDecision(payload);
      setRequestState("idle");
    } catch (reason) {
      if (isAbortError(reason)) return;
      setDecision(null);
      setRequestState("error");
    }
  }, []);

  useEffect(() => {
    const initialDecisionController = new AbortController();
    decisionRequest.current = initialDecisionController;
    void requestDecision(OWNER_PROFILE, initialDecisionController.signal)
      .then((payload) => {
        setDecision(payload);
        setRequestState("idle");
      })
      .catch((reason: unknown) => {
        if (isAbortError(reason)) return;
        setDecision(null);
        setRequestState("error");
      });

    const researchController = new AbortController();
    async function loadResearchStatus() {
      try {
        const response = await fetch("/api/research-lab/daily", {
          cache: "no-store",
          signal: researchController.signal,
        });
        if (!response.ok) throw new Error("research unavailable");
        setResearchStatus((await response.json()) as ResearchStatus);
        setResearchUnavailable(false);
      } catch (reason) {
        if (isAbortError(reason)) return;
        setResearchUnavailable(true);
      }
    }
    void loadResearchStatus();

    return () => {
      initialDecisionController.abort();
      researchController.abort();
      decisionRequest.current?.abort();
    };
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void evaluate(form);
  }

  function applyPreset(value: FormState) {
    setForm(value);
    void evaluate(value);
  }

  const snapshot = researchStatus?.latest_snapshot;
  const audit = researchStatus?.system_audit;
  const candidate = snapshot?.top_candidate;
  const certifiedCount =
    researchStatus?.certified_robots?.certified_robot_count ?? 0;
  const latestRunFailed = researchStatus?.workflow?.conclusion === "failure";
  const evidenceReleaseBlocked =
    !snapshot || (snapshot.eligible_candidate_count ?? 0) === 0 || certifiedCount === 0;
  const gateRows = researchGateRows(researchStatus);

  return (
    <section className={styles.demoShell} id="demo" aria-labelledby="demo-title">
      <header className={styles.demoHeader}>
        <div>
          <span className={styles.kicker}>可操作 PoC · 匿名輪廓</span>
          <h2 id="demo-title">企業與家庭，必須一起算風險。</h2>
          <p>
            先把投資意願與實際承受能力拆開，再套用流動性、企業依賴與集中度硬上限。
            高分不能沖掉不能承擔的風險。
          </p>
        </div>
        <div className={styles.demoPrivacy}>
          <span>不填姓名</span>
          <span>不填帳號</span>
          <span>不填金額</span>
          <strong>不落地儲存</strong>
        </div>
      </header>

      <div className={styles.presetRow} aria-label="示範輪廓">
        <span>快速情境</span>
        {presets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            onClick={() => applyPreset(preset.value)}
          >
            <strong>{preset.label}</strong>
            <small>{preset.detail}</small>
          </button>
        ))}
      </div>

      <div className={styles.demoGrid}>
        <form className={styles.formPanel} onSubmit={submit}>
          <div className={styles.panelHeading}>
            <span>01</span>
            <div>
              <strong>建立雙帳本輪廓</strong>
              <small>粗粒度區間即可完成 PoC</small>
            </div>
          </div>

          <div className={styles.fieldList}>
            {numericFields.map((field) => (
              <fieldset className={styles.field} key={field.key}>
                <legend>
                  <span>{field.label}</span>
                  <small>{field.note}</small>
                </legend>
                <div className={styles.optionGrid}>
                  {field.options.map((option, index) => {
                    const value = index + 1;
                    const selected = form[field.key] === value;
                    return (
                      <label
                        className={selected ? styles.optionSelected : styles.option}
                        key={option}
                      >
                        <input
                          type="radio"
                          name={field.key}
                          value={value}
                          checked={selected}
                          onChange={() =>
                            setForm((current) => ({
                              ...current,
                              [field.key]: value,
                            }))
                          }
                        />
                        <span>{option}</span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            ))}

            <fieldset className={styles.field}>
              <legend>
                <span>本次優先目標</span>
                <small>只改資金桶，不提高風險等級</small>
              </legend>
              <div className={styles.optionGrid}>
                {goalOptions.map((option) => {
                  const selected = form.goal_priority === option.value;
                  return (
                    <label
                      className={selected ? styles.optionSelected : styles.option}
                      key={option.value}
                    >
                      <input
                        type="radio"
                        name="goal_priority"
                        value={option.value}
                        checked={selected}
                        onChange={() =>
                          setForm((current) => ({
                            ...current,
                            goal_priority: option.value,
                          }))
                        }
                      />
                      <span>{option.label}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          </div>

          <button
            className={styles.primaryButton}
            type="submit"
            disabled={requestState === "loading"}
          >
            {requestState === "loading" ? "正在重算風險邊界…" : "重算輪廓與研究權限"}
          </button>
          <p className={styles.privacyNote}>
            競賽版只傳送上列 8 個選項；額外欄位、精確資產、身分資料一律由後端拒絕。
          </p>
          {requestState === "error" ? (
            <p className={styles.errorText} role="alert">
              服務暫時無法連線。系統已停止，沒有產生任何結果。
            </p>
          ) : null}
        </form>

        <div
          className={styles.resultPanel}
          aria-busy={requestState === "loading"}
          aria-live="polite"
        >
          <div className={styles.panelHeading}>
            <span>02</span>
            <div>
              <strong>適合度邊界與理專路由</strong>
              <small>可解釋、可覆核、不能自動下單</small>
            </div>
          </div>

          {decision ? (
            <>
              <div className={styles.decisionHero}>
                <div className={styles.riskSeal}>
                  <span>{decision.risk_code}</span>
                  <strong>{decision.risk_name}</strong>
                </div>
                <div>
                  <span
                    className={
                      decision.decision_state === "REVIEW_REQUIRED"
                        ? styles.statusReview
                        : styles.statusPass
                    }
                  >
                    {decision.decision_state === "REVIEW_REQUIRED"
                      ? "需先人工覆核"
                      : "可進入受限研究"}
                  </span>
                  <h3>{decision.service_route}</h3>
                  <p>
                    最終等級取「意願」與「能力」較低者，再套用不可被高分抵銷的硬性上限。
                  </p>
                </div>
              </div>

              <div className={styles.axisGrid}>
                <div className={styles.axisCard}>
                  <div>
                    <span>投資意願</span>
                    <strong>{decision.willingness_score}</strong>
                  </div>
                  <div className={styles.axisTrack} aria-hidden="true">
                    <span style={{ width: `${decision.willingness_score}%` }} />
                  </div>
                  <small>虧損意願 × 期限 × 經驗</small>
                </div>
                <div className={styles.axisCard}>
                  <div>
                    <span>實際承受能力</span>
                    <strong>{decision.capacity_score}</strong>
                  </div>
                  <div className={styles.axisTrack} aria-hidden="true">
                    <span style={{ width: `${decision.capacity_score}%` }} />
                  </div>
                  <small>流動性 × 收入 × 企業依賴 × 集中度</small>
                </div>
              </div>

              <div className={styles.guardrailGrid}>
                <div>
                  <span>候選最大回撤門檻</span>
                  <strong>{decision.max_research_drawdown_percent}%</strong>
                  <small>研究政策上限，並非損失保證</small>
                </div>
                <div>
                  <span>單筆研究風險預算</span>
                  <strong>{decision.per_trade_risk_budget_percent}%</strong>
                  <small>正式商品仍須另做適合度審查</small>
                </div>
                <div>
                  <span>決策指紋</span>
                  <strong className={styles.monoValue}>
                    {decision.audit.decision_fingerprint}
                  </strong>
                  <small>{decision.audit.model_version}</small>
                </div>
              </div>

              {decision.profile_conflicts.length > 0 ? (
                <div className={styles.conflictBox}>
                  <strong>系統偵測到 {decision.profile_conflicts.length} 個輪廓衝突</strong>
                  <ul>
                    {decision.profile_conflicts.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className={styles.clearBox}>
                  <strong>目前沒有硬性輪廓衝突</strong>
                  <p>這只代表可以進入受限研究，不代表任何商品已適合或可以推介。</p>
                </div>
              )}

              <section className={styles.resultSection} aria-labelledby="allocation-title">
                <div className={styles.resultSectionTitle}>
                  <div>
                    <span>資產配置討論框</span>
                    <h3 id="allocation-title">只給區間，不直接推商品</h3>
                  </div>
                  <small>合計 100%</small>
                </div>
                <div className={styles.allocationList}>
                  {decision.allocation_envelope.map((bucket) => (
                    <div className={styles.allocationRow} key={bucket.name}>
                      <div>
                        <strong>{bucket.name}</strong>
                        <small>{bucket.purpose}</small>
                      </div>
                      <div className={styles.allocationVisual}>
                        <div className={styles.allocationTrack} aria-hidden="true">
                          <span style={{ width: `${bucket.target_percent}%` }} />
                        </div>
                        <strong>{bucket.target_percent}%</strong>
                        <small>
                          {bucket.range_low_percent}–{bucket.range_high_percent}%
                        </small>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section className={styles.resultSection} aria-labelledby="stress-title">
                <div className={styles.resultSectionTitle}>
                  <div>
                    <span>雙重壓力檢查</span>
                    <h3 id="stress-title">先看壞情境，再談報酬</h3>
                  </div>
                </div>
                <div className={styles.stressList}>
                  {decision.stress_checks.map((check) => (
                    <article className={styles.stressRow} key={check.scenario}>
                      <span className={stressStateClasses[check.state]}>{check.state}</span>
                      <div>
                        <strong>{check.scenario}</strong>
                        <p>{check.observation}</p>
                        <small>{check.advisor_action}</small>
                      </div>
                    </article>
                  ))}
                </div>
              </section>

              <details className={styles.explanationDetails}>
                <summary>查看 7 項決策理由與硬上限</summary>
                <div className={styles.explanationList}>
                  {decision.explanations.map((item) => (
                    <div key={item.factor}>
                      <span className={impactClasses[item.impact]}>{item.impact}</span>
                      <strong>{item.factor}</strong>
                      <p>{item.explanation}</p>
                    </div>
                  ))}
                </div>
                {decision.audit.hard_caps_applied.length > 0 ? (
                  <div className={styles.hardCaps}>
                    <strong>已套用硬性上限</strong>
                    <ul>
                      {decision.audit.hard_caps_applied.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </details>
            </>
          ) : (
            <div className={styles.emptyState}>
              <span>{requestState === "loading" ? "CALCULATING" : "FAIL CLOSED"}</span>
              <p>
                {requestState === "loading"
                  ? "正在建立可稽核的風險邊界。"
                  : "沒有完整結果時，不發布理財建議。"}
              </p>
            </div>
          )}
        </div>
      </div>

      <section className={styles.researchPanel} aria-labelledby="research-title">
        <div className={styles.researchIntro}>
          <div>
            <span className={styles.kicker}>03 · 真實 Research Lab 證據</span>
            <h2 id="research-title">回測看起來漂亮，也不代表能見客。</h2>
          </div>
          <p>
            這裡不是預製假數字。它讀取既有 AI 台股研究所的最新完整快照；
            自動研究失敗、證據不足或沒有 Final Holdout 認證時，對客發布一律鎖住。
          </p>
        </div>

        <div className={styles.researchStatusBar}>
          <div>
            <span>對客發布閘門</span>
            <strong className={evidenceReleaseBlocked ? styles.releaseBlocked : styles.releaseReview}>
              {researchUnavailable
                ? "狀態不可用 · 停止"
                : evidenceReleaseBlocked
                  ? "LOCKED · 未放行"
                  : "待理專最終覆核"}
            </strong>
          </div>
          <div>
            <span>最新完整快照</span>
            <strong>{formatSnapshotTime(snapshot?.generated_at_utc)}</strong>
          </div>
          <div>
            <span>完整母體</span>
            <strong>
              {formatNumber(snapshot?.completed_symbol_count)}/
              {formatNumber(snapshot?.universe_size)} 檔
            </strong>
          </div>
          <div>
            <span>累積 Train 實驗</span>
            <strong>
              {formatNumber(snapshot?.training_memory?.unique_experiment_count)} 組
            </strong>
          </div>
        </div>

        {latestRunFailed ? (
          <div className={styles.failClosedNotice}>
            <strong>最新排程沒有通過全系統稽核。</strong>
            <span>
              系統未覆寫成果，仍只顯示上一次完整快照；這是預期的 fail-closed 行為。
            </span>
          </div>
        ) : null}

        <div className={styles.researchGrid}>
          <div className={styles.gatePanel}>
            <div className={styles.resultSectionTitle}>
              <div>
                <span>最高證據候選 · 非推薦</span>
                <h3>
                  {candidate
                    ? `${formatNumber(candidate.confirmation_gate_pass_count)}/${formatNumber(candidate.confirmation_gate_total)} Gate 通過`
                    : "尚無可評估候選"}
                </h3>
              </div>
              <small>
                {snapshot?.eligible_candidate_count ?? 0} 名具 Final Holdout 資格
              </small>
            </div>
            <div className={styles.gateList}>
              {gateRows.map(([label, passed]) => (
                <div key={label}>
                  <span className={passed ? styles.gatePass : styles.gateFail}>
                    {passed ? "PASS" : "HOLD"}
                  </span>
                  <strong>{label}</strong>
                </div>
              ))}
            </div>
          </div>

          <aside className={styles.evidencePanel}>
            <span>研究完整性</span>
            <strong>{audit?.system_status ?? "STATUS UNAVAILABLE"}</strong>
            <dl>
              <div>
                <dt>稽核</dt>
                <dd>
                  {audit
                    ? `${audit.passed_check_count ?? 0} 通過 / ${audit.failed_check_count ?? 0} 失敗`
                    : "不可用"}
                </dd>
              </div>
              <div>
                <dt>Train 記憶</dt>
                <dd>{snapshot?.training_memory?.provenance ?? "不可用"}</dd>
              </div>
              <div>
                <dt>Validation 回灌</dt>
                <dd>
                  {snapshot?.training_memory?.validation_feedback_used ? "異常" : "禁止"}
                </dd>
              </div>
              <div>
                <dt>Holdout 回灌</dt>
                <dd>{snapshot?.training_memory?.holdout_feedback_used ? "異常" : "禁止"}</dd>
              </div>
              <div>
                <dt>Final Holdout</dt>
                <dd>{snapshot?.holdout_opened ? "已開啟" : "搜尋期間鎖定"}</dd>
              </div>
              <div>
                <dt>正式認證機器人</dt>
                <dd>{certifiedCount} 名</dd>
              </div>
            </dl>
            <p>
              沒有通過者時顯示「沒有」，不拿最高回測報酬冒充可對客建議。
            </p>
          </aside>
        </div>
      </section>
    </section>
  );
}
