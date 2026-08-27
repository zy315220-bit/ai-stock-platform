"use client";

import { useEffect, useMemo, useState } from "react";

import styles from "./tbb.module.css";

type Candidate = {
  stock_code?: string;
  candidate_id?: string;
  strategy_family?: string;
  hypothesis?: string;
  decision?: string;
  research_score?: number;
  eligible_for_one_shot_holdout?: boolean;
  gate_reasons?: string[];
  confirmation_gate_pass_count?: number;
  confirmation_gate_total?: number;
  regime_robust?: boolean;
  walk_forward_sample_sufficient?: boolean;
  walk_forward_positive_slice_ratio?: number;
  validation?: {
    completed_trades?: number;
    win_rate_percent?: number;
    wilson_lower_percent?: number;
    total_return_percent?: number;
    max_drawdown_percent?: number;
    probabilistic_sharpe_ratio_percent?: number;
    statistical_quality_pass?: boolean;
    deflated_sharpe_probability_percent?: number;
    deflated_sharpe_pass?: boolean;
  };
  model_selection?: {
    cscv_pbo_available?: boolean;
    cscv_pbo_probability_percent?: number;
    cscv_pbo_pass?: boolean;
    hansen_spa_available?: boolean;
    hansen_spa_p_value?: number;
    hansen_spa_pass?: boolean;
  };
};

type ResearchStatus = {
  latest_snapshot?: {
    as_of_date?: string;
    generated_at_utc?: string;
    universe_size?: number;
    completed_symbol_count?: number;
    candidate_count?: number;
    eligible_candidate_count?: number;
    integrity_status?: string;
    top_candidate?: Candidate | null;
    candidates?: Candidate[];
    training_memory?: {
      unique_experiment_count?: number;
      strategy_family_count?: number;
    };
  } | null;
  system_audit?: {
    system_status?: string;
    system_ready?: boolean;
    passed_check_count?: number;
    failed_check_count?: number;
  } | null;
  certified_robots?: {
    certified_robot_count?: number;
  } | null;
};

const reasonLabels: Record<string, string> = {
  validation_gate_not_ready: "獨立 Validation 尚未達標",
  bull_bear_robustness_failed: "牛／熊／盤整環境不夠穩健",
  walk_forward_stability_failed: "Walk-forward 跨期穩定性不足",
  psr_mintrl_bootstrap_failed: "樣本量／Sharpe 統計可信度不足",
  deflated_sharpe_failed: "DSR 未排除多重嘗試造成的假好成績",
  cscv_pbo_failed_or_unavailable: "PBO 顯示過擬合風險仍高或證據不足",
  hansen_spa_failed_or_unavailable: "Hansen SPA 未證明優於基準",
};

function pct(value?: number, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(digits)}%`
    : "—";
}

function gateRows(candidate: Candidate | null) {
  const wfPass = Boolean(
    candidate?.walk_forward_sample_sufficient &&
      (candidate.walk_forward_positive_slice_ratio ?? 0) >= 0.5,
  );

  return [
    {
      label: "Validation",
      pass: Boolean(candidate?.validation?.statistical_quality_pass),
      plain: "獨立樣本統計品質",
    },
    {
      label: "Walk-forward",
      pass: wfPass,
      plain: "換時間區段還能不能維持",
    },
    {
      label: "Regime",
      pass: Boolean(candidate?.regime_robust),
      plain: "牛／熊／盤整都不能只靠單一行情",
    },
    {
      label: "DSR",
      pass: Boolean(candidate?.validation?.deflated_sharpe_pass),
      plain: "排除大量試驗後碰巧跑出漂亮績效",
    },
    {
      label: "PBO",
      pass: Boolean(candidate?.model_selection?.cscv_pbo_pass),
      plain: "估計策略被挑中只是過擬合的風險",
    },
    {
      label: "SPA",
      pass: Boolean(candidate?.model_selection?.hansen_spa_pass),
      plain: "檢查是否真的優於比較基準",
    },
    {
      label: "Final Holdout",
      pass: Boolean(candidate?.eligible_for_one_shot_holdout),
      plain: "最後一次、不能反覆偷看的測試資格",
    },
  ];
}

function verdict(candidate: Candidate | null) {
  if (!candidate) {
    return {
      code: "NO_EVIDENCE",
      title: "沒有完整研究證據",
      body: "系統不會補假答案，維持鎖定。",
      tone: "blocked",
    } as const;
  }

  if (candidate.eligible_for_one_shot_holdout) {
    return {
      code: "RESEARCH_READY",
      title: "可進一步研究",
      body: "研究證據已達 Final Holdout 資格；仍不等於對客推薦或保證獲利。",
      tone: "review",
    } as const;
  }

  const passCount = candidate.confirmation_gate_pass_count ?? 0;
  if (passCount >= 4) {
    return {
      code: "MORE_EVIDENCE",
      title: "證據不足，繼續驗證",
      body: "回測可能很好看，但仍有重要統計 Gate 沒通過，所以不能把它當成可信投資結論。",
      tone: "warning",
    } as const;
  }

  return {
    code: "LOCKED",
    title: "鎖定，不採用",
    body: "目前證據不足以支持這個 AI 研究候選，系統拒絕往下一步放行。",
    tone: "blocked",
  } as const;
}

export default function TrustResearchDemo() {
  const [status, setStatus] = useState<ResearchStatus | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const response = await fetch("/api/research-lab/daily", {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("research unavailable");
        const payload = (await response.json()) as ResearchStatus;
        setStatus(payload);
        const first =
          payload.latest_snapshot?.top_candidate?.candidate_id ??
          payload.latest_snapshot?.candidates?.[0]?.candidate_id ??
          "";
        setSelectedId(first);
        setFailed(false);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setFailed(true);
      } finally {
        setLoading(false);
      }
    }

    void load();
    return () => controller.abort();
  }, []);

  const candidates = status?.latest_snapshot?.candidates ?? [];
  const selected = useMemo(() => {
    if (!candidates.length) return status?.latest_snapshot?.top_candidate ?? null;
    return (
      candidates.find((item) => item.candidate_id === selectedId) ??
      status?.latest_snapshot?.top_candidate ??
      candidates[0] ??
      null
    );
  }, [candidates, selectedId, status]);

  const gates = gateRows(selected);
  const result = verdict(selected);
  const failedReasons = (selected?.gate_reasons ?? []).map(
    (reason) => reasonLabels[reason] ?? reason.replaceAll("_", " "),
  );

  if (loading) {
    return (
      <section className={styles.trustDemo} id="demo">
        <div className={styles.trustLoading}>正在讀取最新 Research Lab 完整快照…</div>
      </section>
    );
  }

  if (failed || !status?.latest_snapshot) {
    return (
      <section className={styles.trustDemo} id="demo">
        <div className={styles.trustFail}>
          <span>FAIL-CLOSED</span>
          <h2>研究證據目前不可用。</h2>
          <p>系統不會用預製數字代替真實研究結果，因此維持鎖定。</p>
        </div>
      </section>
    );
  }

  const snapshot = status.latest_snapshot;
  const passCount = gates.filter((gate) => gate.pass).length;

  return (
    <section className={styles.trustDemo} id="demo" aria-labelledby="trust-demo-title">
      <header className={styles.trustDemoHeader}>
        <div>
          <span className={styles.kicker}>LIVE RESEARCH EVIDENCE</span>
          <h2 id="trust-demo-title">挑一個 AI 研究候選，直接驗它值不值得信。</h2>
          <p>
            這裡讀的是現有 Research Lab 最新完整快照。你不需要懂統計名詞，
            只要看最後「通過／失敗／為什麼被擋」。
          </p>
        </div>
        <div className={styles.snapshotSeal}>
          <span>SNAPSHOT</span>
          <strong>{snapshot.as_of_date ?? "—"}</strong>
          <small>
            {snapshot.completed_symbol_count ?? 0}/{snapshot.universe_size ?? 0} 檔完成
          </small>
        </div>
      </header>

      <div className={styles.candidateChooser}>
        <span>選擇研究候選</span>
        <div>
          {candidates.slice(0, 8).map((candidate) => {
            const active = candidate.candidate_id === selected?.candidate_id;
            return (
              <button
                type="button"
                key={candidate.candidate_id ?? candidate.stock_code}
                className={active ? styles.candidateActive : styles.candidateButton}
                onClick={() => setSelectedId(candidate.candidate_id ?? "")}
              >
                <strong>{candidate.stock_code ?? "—"}</strong>
                <small>{candidate.confirmation_gate_pass_count ?? 0}/7 Gates</small>
              </button>
            );
          })}
        </div>
      </div>

      <div className={styles.trustWorkbench}>
        <section className={styles.strategyEvidence}>
          <div className={styles.workbenchLabel}>
            <span>01</span>
            <strong>先看「很容易讓人心動」的回測數字</strong>
          </div>

          <div className={styles.strategyTitle}>
            <div>
              <span>研究候選 · 非推薦</span>
              <h3>{selected?.stock_code ?? "—"}</h3>
              <p>{selected?.strategy_family?.replaceAll("_", " ") ?? "—"}</p>
            </div>
            <div className={styles.researchScore}>
              <span>RESEARCH SCORE</span>
              <strong>{selected?.research_score?.toFixed(1) ?? "—"}</strong>
            </div>
          </div>

          <div className={styles.metricGrid}>
            <div>
              <span>Validation 報酬</span>
              <strong>{pct(selected?.validation?.total_return_percent)}</strong>
            </div>
            <div>
              <span>勝率</span>
              <strong>{pct(selected?.validation?.win_rate_percent)}</strong>
            </div>
            <div>
              <span>交易樣本</span>
              <strong>{selected?.validation?.completed_trades ?? "—"}</strong>
            </div>
            <div>
              <span>最大回撤</span>
              <strong>{pct(selected?.validation?.max_drawdown_percent)}</strong>
            </div>
          </div>

          <div className={styles.trapNotice}>
            <span>如果只看上面，很容易誤判。</span>
            <p>
              例如高報酬或 100% 勝率，在交易次數很少、跨期不穩或多重測試未修正時，
              仍可能只是偶然。
            </p>
          </div>

          <div className={styles.reasonBlock}>
            <span>目前被擋的主要理由</span>
            {failedReasons.length ? (
              <ul>
                {failedReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            ) : (
              <p>目前沒有列出阻擋理由。</p>
            )}
          </div>
        </section>

        <section className={styles.gateEvidence}>
          <div className={styles.workbenchLabel}>
            <span>02</span>
            <strong>再過 7 個可信度 Gate</strong>
          </div>

          <div className={styles.gateSummary}>
            <div>
              <span>目前通過</span>
              <strong>{passCount}/7</strong>
            </div>
            <div>
              <span>Final Holdout 認證</span>
              <strong>
                {(status.certified_robots?.certified_robot_count ?? 0) > 0
                  ? "已有認證"
                  : "0 名"}
              </strong>
            </div>
          </div>

          <div className={styles.gateBoard}>
            {gates.map((gate) => (
              <div key={gate.label}>
                <span className={gate.pass ? styles.gateOk : styles.gateNo}>
                  {gate.pass ? "PASS" : "HOLD"}
                </span>
                <div>
                  <strong>{gate.label}</strong>
                  <small>{gate.plain}</small>
                </div>
              </div>
            ))}
          </div>

          <div className={styles.plainStats}>
            <div>
              <span>Wilson 95% 下界</span>
              <strong>{pct(selected?.validation?.wilson_lower_percent)}</strong>
              <small>比單看勝率更保守</small>
            </div>
            <div>
              <span>Deflated Sharpe</span>
              <strong>{pct(selected?.validation?.deflated_sharpe_probability_percent)}</strong>
              <small>修正大量嘗試後的假好成績</small>
            </div>
            <div>
              <span>PBO</span>
              <strong>{pct(selected?.model_selection?.cscv_pbo_probability_percent)}</strong>
              <small>過擬合風險估計</small>
            </div>
            <div>
              <span>SPA p-value</span>
              <strong>
                {typeof selected?.model_selection?.hansen_spa_p_value === "number"
                  ? selected.model_selection.hansen_spa_p_value.toFixed(3)
                  : "—"}
              </strong>
              <small>是否有足夠證據優於基準</small>
            </div>
          </div>
        </section>
      </div>

      <section className={styles.finalVerdict}>
        <div>
          <span>03 · TRUST VERDICT</span>
          <strong className={styles[result.tone]}>{result.code}</strong>
        </div>
        <div>
          <h3>{result.title}</h3>
          <p>{result.body}</p>
        </div>
        <div className={styles.verdictRules}>
          <span>平台會做</span>
          <strong>驗證、拒絕、留下理由</strong>
          <span>平台不會做</span>
          <strong>保證獲利、直接下單、把回測當推薦</strong>
        </div>
      </section>

      <div className={styles.liveFooter}>
        <span>累積 Train 實驗：{snapshot.training_memory?.unique_experiment_count?.toLocaleString("zh-TW") ?? "—"}</span>
        <span>候選：{snapshot.candidate_count ?? candidates.length}</span>
        <span>Final Holdout 資格：{snapshot.eligible_candidate_count ?? 0}</span>
        <span>完整性：{snapshot.integrity_status ?? "—"}</span>
      </div>
    </section>
  );
}
