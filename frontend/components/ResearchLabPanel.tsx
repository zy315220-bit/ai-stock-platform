"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import DailyResearchStatus from "./DailyResearchStatus";

type Candidate = {
  candidate_id: string;
  parent_id: string | null;
  strategy_family: string;
  hypothesis: string;
  parameters: Record<string, unknown>;
};

type ExperimentResult = {
  candidate: Candidate;
  validation_metrics: Record<string, unknown>;
  decision: "KEEP" | "DISCARD" | "HOLDOUT_READY";
  research_score: number;
  reasons: string[];
  evaluation_phase: "train" | "validation";
};

type RegimeSummary = {
  slice_count: number;
  completed_trades: number;
  winning_trades: number;
  win_rate_percent: number;
  wilson_win_rate_lower_bound_percent: number;
  mean_return_percent: number;
  mean_benchmark_return_percent: number;
  mean_alpha_percent: number;
  positive_alpha_slice_ratio: number;
  worst_drawdown_percent: number;
};

type RegimeTournamentRow = {
  rank: number;
  validation_result: ExperimentResult;
  market_regime_matrix: {
    candidate_id: string;
    benchmark_code: string;
    slices: Array<Record<string, unknown>>;
    by_regime: Record<"BULL" | "BEAR" | "SIDEWAYS", RegimeSummary>;
    data_fingerprints: string[];
    robustness: {
      robust_across_required_regimes: boolean;
      conservative_wilson_lower_bound_percent: number;
      conservative_return_percent: number;
      conservative_alpha_percent: number;
      robustness_score: number;
      reasons: string[];
      holdout_used: false;
    };
  };
};

type ResearchResponse = {
  research_run_id: string;
  data_fingerprints: string[];
  stock_code: string;
  experiments_run: number;
  generations_run: number;
  stopped_reason: string;
  holdout_status: string;
  training_best_result: ExperimentResult | null;
  validation_finalists: ExperimentResult[];
  best_result: ExperimentResult | null;
  selected_candidate: Candidate | null;
  market_regime_tournament: RegimeTournamentRow[];
  model_selection_evidence: {
    trial_count_for_deflated_sharpe: number;
    cscv_pbo: {
      available: boolean;
      pbo_probability_percent?: number;
      combination_count?: number;
      overfitting_risk_pass?: boolean;
      reason?: string;
    };
    hansen_spa: {
      available: boolean;
      spa_p_value?: number;
      bootstrap_samples?: number;
      superior_predictive_ability_pass?: boolean;
      reason?: string;
    };
  };
  walk_forward_matrix: null | {
    candidate_id: string;
    slices: Array<Record<string, unknown>>;
    aggregate: {
      slice_count: number;
      positive_slice_count: number;
      positive_slice_ratio: number;
      mean_return_percent: number;
      mean_sharpe_ratio: number;
      worst_slice_drawdown_percent: number;
      completed_trades: number;
      open_position_count: number;
      evidence_quality: {
        sample_sufficient: boolean;
        evidence_label: string;
      };
      holdout_used: false;
    };
  };
  promotion_eligibility: {
    eligible_for_one_shot_holdout: boolean;
    reasons: string[];
    holdout_opened: false;
  };
  research_audit: {
    pipeline: string[];
    training_used_for_search: boolean;
    validation_used_during_adaptive_search: boolean;
    holdout_used_during_search: boolean;
    walk_forward_holdout_used: boolean;
    market_regime_holdout_used: boolean;
  };
  split: {
    train: [string, string];
    validation: [string, string];
    holdout: [string, string];
  };
};

const regimeLabels = {
  BULL: "牛市",
  BEAR: "熊市",
  SIDEWAYS: "盤整",
} as const;

const methodReferences = [
  ["PSR / MinTRL", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1821643"],
  ["Deflated Sharpe", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2465675"],
  ["CSCV / PBO", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253"],
  ["Hamilton Regime", "https://www.jstor.org/stable/1912559"],
  ["Stationary Bootstrap", "https://doi.org/10.1080/01621459.1994.10476870"],
  ["Hansen SPA", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=264569"],
] as const;

const reasonLabels: Record<string, string> = {
  no_validation_survivor: "沒有候選通過獨立驗證",
  validation_gate_not_ready: "Validation 分數尚未達放行門檻",
  bull_bear_robustness_failed: "牛熊市穩健性門檻未通過",
  walk_forward_sample_insufficient: "Walk-forward 完成交易樣本不足",
  walk_forward_stability_failed: "跨時段正報酬比例不足",
  psr_mintrl_bootstrap_failed: "PSR、MinTRL 或區塊 Bootstrap 證據不足",
  deflated_sharpe_failed: "DSR 多重測試修正未通過",
  cscv_pbo_failed_or_unavailable: "CSCV / PBO 過度擬合檢查未通過",
  hansen_spa_failed_or_unavailable: "Hansen SPA 未證明候選優於基準",
  missing_bull_regime: "研究期間缺少牛市樣本",
  missing_bear_regime: "研究期間缺少熊市樣本",
  insufficient_bull_trades: "牛市完成交易不足",
  insufficient_bear_trades: "熊市完成交易不足",
  negative_bull_return: "牛市平均報酬為負",
  negative_bear_return: "熊市平均報酬為負",
  negative_bull_alpha: "牛市未勝過 0050",
  negative_bear_alpha: "熊市未勝過 0050",
  bull_drawdown_too_high: "牛市回撤超標",
  bear_drawdown_too_high: "熊市回撤超標",
};

function numberValue(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatNumber(value: unknown, digits = 2): string {
  return numberValue(value).toLocaleString("zh-TW", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatSeconds(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes > 0 ? `${minutes} 分 ${remainder} 秒` : `${remainder} 秒`;
}

function parameterLabel(key: string): string {
  const labels: Record<string, string> = {
    entry_score: "進場分數",
    exit_score: "出場分數",
    initial_capital: "研究本金",
    require_ema_trend: "EMA 趨勢過濾",
    ema_fast_column: "快速均線",
    ema_slow_column: "慢速均線",
    exit_mode: "出場模式",
    max_holding_days: "最長持有日",
  };
  return labels[key] ?? key;
}

export default function ResearchLabPanel() {
  const [stock, setStock] = useState("2330");
  const [start, setStart] = useState("2020-01-01");
  const [end, setEnd] = useState("2025-12-31");
  const [experimentBudget, setExperimentBudget] = useState(40);
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState("");
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  const champion = result?.market_regime_tournament[0] ?? null;
  const championMetrics = result?.best_result?.validation_metrics ?? null;
  const statisticalEvidence = championMetrics?.statistical_evidence as
    | {
        probabilistic_sharpe_ratio_percent?: number;
        minimum_track_record_observations?: number | null;
        observations?: number;
        track_record_sufficient?: boolean;
        statistical_quality_pass?: boolean;
        stationary_bootstrap?: {
          available?: boolean;
          annualized_arithmetic_return_ci_percent?: [number, number];
        };
      }
    | undefined;
  const deflatedSharpe = championMetrics?.deflated_sharpe as
    | {
        available?: boolean;
        deflated_sharpe_probability_percent?: number;
        trial_count?: number;
        multiple_testing_pass?: boolean;
      }
    | undefined;
  const parameterEntries = Object.entries(
    result?.selected_candidate?.parameters ?? {},
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRunning(true);
    setElapsedSeconds(0);
    setError("");
    setResult(null);
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const query = new URLSearchParams({
      stock_code: stock.trim(),
      start_date: start,
      end_date: end,
      max_generations: "3",
      max_experiments: String(experimentBudget),
      min_validation_trades: "6",
      validation_finalists: "5",
      walk_forward_slices: "3",
      regime_candidate_count: "2",
      regime_slices: "6",
      min_regime_trades: "1",
    });

    try {
      const response = await fetch(`/api/research-lab/run?${query}`, {
        method: "POST",
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          typeof payload?.detail === "string"
            ? payload.detail
            : "AI 研究工作階段執行失敗。",
        );
      }
      setResult(payload as ResearchResponse);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setError("本輪研究已取消，Final Holdout 仍維持鎖定。");
        return;
      }
      setError(
        reason instanceof Error
          ? reason.message
          : "AI 研究工作階段執行失敗。",
      );
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setRunning(false);
      }
    }
  }

  function cancelResearch() {
    controllerRef.current?.abort();
  }

  return (
    <section className="research-lab-shell">
      <header className="research-lab-hero">
        <div>
          <p className="panel-kicker">AUTONOMOUS RESEARCH / NO LOOK-AHEAD</p>
          <h1>AI 選股機器人研究室</h1>
          <p>
            每個台股交易日收盤後自動研究，讓候選策略先在 Train 自主進化，再進入
            獨立 Validation、牛熊盤整情境與 Walk-forward 審核。Final Holdout 全程鎖定。
          </p>
        </div>
        <div className="research-holdout-lock">
          <span>FINAL HOLDOUT</span>
          <strong>鎖定</strong>
          <small>只有所有前置 Gate 通過，才具備一次性驗收資格</small>
        </div>
      </header>

      <DailyResearchStatus />

      <div className="research-pipeline" aria-label="研究資料流程">
        <article><span>01</span><strong>Train</strong><small>進化與淘汰</small></article>
        <article><span>02</span><strong>Validation</strong><small>獨立決選</small></article>
        <article><span>03</span><strong>Regimes</strong><small>牛熊盤整壓測</small></article>
        <article><span>04</span><strong>Walk-forward</strong><small>跨時段穩定性</small></article>
        <article className="locked"><span>05</span><strong>Holdout</strong><small>一次性最終驗收</small></article>
      </div>

      <div className="research-manual-heading">
        <div>
          <p className="panel-kicker">OPTIONAL ON-DEMAND RUN</p>
          <h2>臨時指定研究</h2>
        </div>
        <small>每日研究不依賴此表單；只有想立即加跑某檔股票時才需要使用。</small>
      </div>

      <form className="research-run-form" onSubmit={submit}>
        <label>
          <span>股票代號</span>
          <input
            maxLength={10}
            onChange={(event) => setStock(event.target.value)}
            required
            value={stock}
          />
        </label>
        <label>
          <span>研究開始</span>
          <input
            onChange={(event) => setStart(event.target.value)}
            required
            type="date"
            value={start}
          />
        </label>
        <label>
          <span>研究結束</span>
          <input
            onChange={(event) => setEnd(event.target.value)}
            required
            type="date"
            value={end}
          />
        </label>
        <label>
          <span>實驗預算</span>
          <select
            onChange={(event) => setExperimentBudget(Number(event.target.value))}
            value={experimentBudget}
          >
            <option value={24}>快速・24 次</option>
            <option value={40}>標準・40 次</option>
            <option value={60}>深入・60 次</option>
          </select>
        </label>
        <button
          onClick={running ? cancelResearch : undefined}
          type={running ? "button" : "submit"}
        >
          {running ? "取消本輪研究" : "立即加跑（選用）"}
        </button>
      </form>

      {running ? (
        <div className="research-running" role="status" aria-live="polite">
          <div className="research-running-orbit"><i /><i /><i /></div>
          <div>
            <strong>完整研究工作階段執行中</strong>
            <span>已執行 {formatSeconds(elapsedSeconds)}</span>
            <small>
              後端正在依序完成候選進化、獨立驗證、0050 市況標記與跨時段稽核；真實歷史資料研究通常需要數十秒至數分鐘。
            </small>
          </div>
        </div>
      ) : null}

      {error ? <div className="research-error" role="alert">{error}</div> : null}

      {result ? (
        <div className="research-results" aria-live="polite">
          <section className="research-result-head">
            <div>
              <p className="panel-kicker">SESSION COMPLETE</p>
              <h2>{result.stock_code} 本輪研究結果</h2>
              <p>
                {result.experiments_run} 次 Train 實驗・{result.generations_run} 個世代・
                {result.validation_finalists.length} 名獨立驗證決選者
              </p>
              <code className="research-run-id">Run {result.research_run_id}・Data {result.data_fingerprints.join(", ") || "N/A"}</code>
            </div>
            <div className={result.promotion_eligibility.eligible_for_one_shot_holdout ? "research-gate pass" : "research-gate blocked"}>
              <span>正式候選 Gate</span>
              <strong>{result.promotion_eligibility.eligible_for_one_shot_holdout ? "具備 Holdout 驗收資格" : "尚未放行"}</strong>
              <small>Holdout 本次未開啟</small>
            </div>
          </section>

          {result.best_result && champion && championMetrics ? (
            <>
              <div className="research-metric-grid">
                <article><span>Validation Score</span><strong>{formatNumber(result.best_result.research_score)}</strong><small>{result.best_result.decision}</small></article>
                <article><span>驗證報酬</span><strong>{formatNumber(championMetrics.total_return_percent)}%</strong><small>含成本後策略報酬</small></article>
                <article><span>交易勝率</span><strong>{formatNumber(championMetrics.win_rate_percent)}%</strong><small>{formatNumber(championMetrics.completed_trades, 0)} 筆完成交易</small></article>
                <article><span>保守勝率下界</span><strong>{formatNumber(championMetrics.wilson_win_rate_lower_bound_percent)}%</strong><small>Wilson 95% 下界</small></article>
                <article><span>相對 Buy & Hold Alpha</span><strong>{formatNumber(championMetrics.alpha_percent)}%</strong><small>同股同期含息報酬差</small></article>
                <article><span>牛熊穩健分</span><strong>{formatNumber(champion.market_regime_matrix.robustness.robustness_score)}</strong><small>{champion.market_regime_matrix.robustness.robust_across_required_regimes ? "通過" : "未通過"}</small></article>
              </div>

              <div className="research-detail-grid">
                <article className="research-champion-card">
                  <p className="panel-kicker">BEST CANDIDATE IN THIS SESSION</p>
                  <h3>本輪最佳候選機器人</h3>
                  <strong className="research-candidate-id">{result.selected_candidate?.candidate_id}</strong>
                  <p>{result.selected_candidate?.hypothesis}</p>
                  <div className="research-parameter-grid">
                    {parameterEntries.map(([key, value]) => (
                      <span key={key}>
                        <small>{parameterLabel(key)}</small>
                        <b>{typeof value === "boolean" ? (value ? "啟用" : "關閉") : String(value)}</b>
                      </span>
                    ))}
                  </div>
                </article>

                <article className="research-audit-card">
                  <p className="panel-kicker">INTEGRITY AUDIT</p>
                  <h3>沒有偷看未來</h3>
                  <ul>
                    <li className={result.research_audit.training_used_for_search ? "pass" : "fail"}>自適應搜尋只在 Train</li>
                    <li className={!result.research_audit.validation_used_during_adaptive_search ? "pass" : "fail"}>Validation 未參與進化調參</li>
                    <li className={!result.research_audit.holdout_used_during_search ? "pass" : "fail"}>Final Holdout 未參與搜尋</li>
                    <li className={!result.research_audit.market_regime_holdout_used ? "pass" : "fail"}>市況壓測未碰 Holdout</li>
                    <li className={!result.research_audit.walk_forward_holdout_used ? "pass" : "fail"}>Walk-forward 未碰 Holdout</li>
                  </ul>
                </article>
              </div>

              <section className="research-statistics-section">
                <div className="research-section-title">
                  <div><p className="panel-kicker">STATISTICAL EVIDENCE</p><h3>多重測試與非 IID 信心檢查</h3></div>
                  <small>先過 Gate，再談排名；不把幾筆幸運交易或大量試參數後的假冠軍當成可靠策略。</small>
                </div>
                <div className="research-stat-grid">
                  <article className={statisticalEvidence?.statistical_quality_pass ? "pass" : "blocked"}>
                    <span>PSR</span>
                    <strong>{statisticalEvidence?.probabilistic_sharpe_ratio_percent === undefined ? "資料不足" : `${formatNumber(statisticalEvidence.probabilistic_sharpe_ratio_percent)}%`}</strong>
                    <small>Sharpe 高於 0 的機率</small>
                  </article>
                  <article className={deflatedSharpe?.multiple_testing_pass ? "pass" : "blocked"}>
                    <span>DSR</span>
                    <strong>{deflatedSharpe?.deflated_sharpe_probability_percent === undefined ? "資料不足" : `${formatNumber(deflatedSharpe.deflated_sharpe_probability_percent)}%`}</strong>
                    <small>已修正 {formatNumber(deflatedSharpe?.trial_count, 0)} 次策略試驗</small>
                  </article>
                  <article className={statisticalEvidence?.track_record_sufficient ? "pass" : "blocked"}>
                    <span>MinTRL</span>
                    <strong>{statisticalEvidence?.minimum_track_record_observations ? `${formatNumber(statisticalEvidence.minimum_track_record_observations, 0)} 日` : "未達"}</strong>
                    <small>實際 {formatNumber(statisticalEvidence?.observations, 0)} 日</small>
                  </article>
                  <article className={result.model_selection_evidence.cscv_pbo.overfitting_risk_pass ? "pass" : "blocked"}>
                    <span>CSCV / PBO</span>
                    <strong>{result.model_selection_evidence.cscv_pbo.pbo_probability_percent === undefined ? "資料不足" : `${formatNumber(result.model_selection_evidence.cscv_pbo.pbo_probability_percent)}%`}</strong>
                    <small>回測過度擬合機率</small>
                  </article>
                  <article className={result.model_selection_evidence.hansen_spa.superior_predictive_ability_pass ? "pass" : "blocked"}>
                    <span>Hansen SPA</span>
                    <strong>{result.model_selection_evidence.hansen_spa.spa_p_value === undefined ? "資料不足" : formatNumber(result.model_selection_evidence.hansen_spa.spa_p_value, 4)}</strong>
                    <small>p-value，門檻 &lt; 0.05</small>
                  </article>
                  <article className={(statisticalEvidence?.stationary_bootstrap?.annualized_arithmetic_return_ci_percent?.[0] ?? -1) > 0 ? "pass" : "blocked"}>
                    <span>Stationary Bootstrap</span>
                    <strong>{statisticalEvidence?.stationary_bootstrap?.annualized_arithmetic_return_ci_percent ? `${formatNumber(statisticalEvidence.stationary_bootstrap.annualized_arithmetic_return_ci_percent[0])}%` : "資料不足"}</strong>
                    <small>年化報酬 95% CI 下界</small>
                  </article>
                </div>
              </section>

              <section className="research-regime-section">
                <div className="research-section-title">
                  <div><p className="panel-kicker">MARKET REGIME MATRIX</p><h3>牛市、熊市、盤整分開驗證</h3></div>
                  <small>每一段只用該段開始前已知的 0050 資料，由三狀態 Hamilton Markov-switching 模型判定；市況標籤只用於稽核，不會成為交易訊號。</small>
                </div>
                <div className="research-regime-grid">
                  {(["BULL", "BEAR", "SIDEWAYS"] as const).map((regime) => {
                    const metrics = champion.market_regime_matrix.by_regime[regime];
                    return (
                      <article className={`regime-${regime.toLowerCase()}`} key={regime}>
                        <span>{regimeLabels[regime]}</span>
                        <strong>{formatNumber(metrics.mean_return_percent)}%</strong>
                        <small>策略平均報酬</small>
                        <dl>
                          <div><dt>Alpha</dt><dd>{formatNumber(metrics.mean_alpha_percent)}%</dd></div>
                          <div><dt>勝率下界</dt><dd>{formatNumber(metrics.wilson_win_rate_lower_bound_percent)}%</dd></div>
                          <div><dt>完成交易</dt><dd>{formatNumber(metrics.completed_trades, 0)}</dd></div>
                          <div><dt>最差回撤</dt><dd>{formatNumber(metrics.worst_drawdown_percent)}%</dd></div>
                        </dl>
                      </article>
                    );
                  })}
                </div>
              </section>

              {result.walk_forward_matrix ? (
                <section className="research-walk-forward">
                  <div><p className="panel-kicker">WALK-FORWARD</p><h3>跨時段穩定性</h3></div>
                  <div className="research-wf-stats">
                    <span><small>正報酬切片</small><b>{formatNumber(result.walk_forward_matrix.aggregate.positive_slice_ratio * 100)}%</b></span>
                    <span><small>平均報酬</small><b>{formatNumber(result.walk_forward_matrix.aggregate.mean_return_percent)}%</b></span>
                    <span><small>完成交易</small><b>{formatNumber(result.walk_forward_matrix.aggregate.completed_trades, 0)}</b></span>
                    <span><small>最差回撤</small><b>{formatNumber(result.walk_forward_matrix.aggregate.worst_slice_drawdown_percent)}%</b></span>
                  </div>
                </section>
              ) : null}
            </>
          ) : (
            <div className="research-empty-result">
              <strong>本輪沒有候選通過 Train → Validation</strong>
              <p>系統已 fail-closed，沒有用不足樣本或未實現部位冒充強策略，也沒有開啟 Final Holdout。</p>
            </div>
          )}

          {!result.promotion_eligibility.eligible_for_one_shot_holdout ? (
            <div className="research-blockers">
              <strong>尚未放行的原因</strong>
              <ul>
                {result.promotion_eligibility.reasons.map((reason) => (
                  <li key={reason}>{reasonLabels[reason] ?? reason}</li>
                ))}
                {champion?.market_regime_matrix.robustness.reasons.map((reason) => (
                  <li key={`regime-${reason}`}>{reasonLabels[reason] ?? reason}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="research-disclaimer">
            「最佳」只代表本輪候選在指定歷史資料與嚴格門檻下的相對排名，不保證未來獲利或最高勝率；平台會保留失敗結果，不把回測當投資承諾。
          </p>
          <details className="research-method-references">
            <summary>查看研究方法原始論文</summary>
            <div>
              {methodReferences.map(([label, href]) => (
                <a href={href} key={label} rel="noreferrer" target="_blank">{label}</a>
              ))}
            </div>
          </details>
        </div>
      ) : null}
    </section>
  );
}
