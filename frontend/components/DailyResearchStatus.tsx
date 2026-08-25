"use client";

import { useEffect, useState } from "react";

type Candidate = {
  stock_code?: string;
  candidate_id?: string;
  strategy_family?: string;
  decision?: "DISCARD" | "KEEP" | "HOLDOUT_READY";
  research_score?: number;
  confirmation_gate_pass_count?: number;
  confirmation_gate_total?: number;
  eligible_for_one_shot_holdout?: boolean;
  regime_robust?: boolean;
  walk_forward_sample_sufficient?: boolean;
  walk_forward_positive_slice_ratio?: number;
  validation?: {
    wilson_lower_percent?: number;
    total_return_percent?: number;
    alpha_percent?: number;
    max_drawdown_percent?: number;
    deflated_sharpe_probability_percent?: number;
    deflated_sharpe_pass?: boolean;
  };
  model_selection?: {
    cscv_pbo_pass?: boolean;
    hansen_spa_pass?: boolean;
  };
};

type DailySnapshot = {
  as_of_date?: string;
  campaign_id?: string;
  generated_at_utc?: string;
  universe_size?: number;
  completed_symbol_count?: number;
  candidate_count?: number;
  eligible_candidate_count?: number;
  holdout_opened?: boolean;
  integrity_status?: string;
  ranking_methodology?: {
    schema?: string;
    production_champion_rule?: string;
    small_sample_win_rate_role?: string;
  };
  training_memory?: {
    enabled?: boolean;
    provenance?: string;
    completed_symbol_count?: number;
    continued_symbol_count?: number;
    verified_data_identity_symbol_count?: number;
    migrated_data_identity_symbol_count?: number;
    unique_experiment_count?: number;
    last_run_new_experiment_count?: number;
    last_run_duplicate_skip_count?: number;
    elite_count?: number;
    frontier_count?: number;
    strategy_family_count?: number;
    strategy_families?: string[];
    validation_feedback_used?: boolean;
    holdout_feedback_used?: boolean;
  };
  top_candidate?: Candidate | null;
};

type SystemAudit = {
  system_status?: "OPERATIONAL" | "FAIL_CLOSED";
  system_ready?: boolean;
  research_engine_complete?: boolean;
  competition_research_loop_complete?: boolean;
  competition_challenger_count?: number;
  passed_check_count?: number;
  failed_check_count?: number;
  champion_discovery_status?: string;
};

type CertifiedRobots = {
  certified_robot_count?: number;
};

type CompetitionChallengers = {
  status?: string;
  challenger_count?: number;
};

type CompetitionTournament = {
  status?: string;
  challenger_count?: number;
  incumbent_leader?: {
    robot_id?: string;
    name?: string;
  };
  overall_leader?: {
    robot_id?: string;
    rank?: number;
    trade_count?: number;
    wilson_lower_percent?: number;
    qualified?: boolean;
    origin?: string;
  };
  promotion?: {
    challenger_replaced_incumbent?: boolean;
    promoted_robot_id?: string | null;
    defeated_incumbent_robot_id?: string | null;
    reason?: string;
    competition_feedback_to_same_campaign_train?: boolean;
  };
};

type DailyStatus = {
  enabled: boolean;
  manual_action_required: boolean;
  schedule: {
    label: string;
    timezone: string;
    sessions_per_day?: number;
    next_scheduled_at: string;
  };
  workflow: null | {
    status?: string;
    conclusion?: string | null;
    updated_at?: string;
    url?: string;
  };
  latest_snapshot: DailySnapshot | null;
  system_audit?: SystemAudit | null;
  certified_robots?: CertifiedRobots | null;
  competition_challengers?: CompetitionChallengers | null;
  competition_tournament?: CompetitionTournament | null;
  snapshot_available: boolean;
};

function formatTaipeiTime(value?: string): string {
  if (!value) return "等待首次執行";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "尚無紀錄";
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

function formatMetric(value?: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

function workflowLabel(status: DailyStatus): string {
  if (status.workflow?.status === "in_progress") return "研究執行中";
  if (status.workflow?.status === "queued") return "已排入研究佇列";
  if (status.workflow?.conclusion === "failure") return "上次研究失敗，等待重試";
  if (status.workflow?.conclusion === "success") return "上次研究已完成";
  return status.snapshot_available ? "自動研究正常" : "等待首次自動研究";
}

function decisionLabel(value?: Candidate["decision"]): string {
  if (value === "HOLDOUT_READY") return "HOLDOUT_READY";
  if (value === "KEEP") return "KEEP";
  if (value === "DISCARD") return "DISCARD";
  return "—";
}

export default function DailyResearchStatus() {
  const [status, setStatus] = useState<DailyStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function refresh() {
      try {
        const response = await fetch("/api/research-lab/daily", {
          cache: "no-store",
          signal: controller.signal,
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok || !payload) {
          throw new Error("無法讀取每日自動研究狀態");
        }
        if (active) {
          setStatus(payload as DailyStatus);
          setError("");
        }
      } catch (reason) {
        if (!active || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "自動研究狀態讀取失敗");
      }
    }

    void refresh();
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(timer);
    };
  }, []);

  const snapshot = status?.latest_snapshot ?? null;
  const top = snapshot?.top_candidate ?? null;
  const memory = snapshot?.training_memory ?? null;
  const audit = status?.system_audit ?? null;
  const certifiedCount = status?.certified_robots?.certified_robot_count ?? 0;
  const challengerCount = status?.competition_challengers?.challenger_count ?? 0;
  const tournament = status?.competition_tournament ?? null;
  const promoted = tournament?.promotion?.challenger_replaced_incumbent === true;
  const running = status?.workflow?.status === "in_progress";

  return (
    <section className="daily-research-card" aria-live="polite">
      <div className="daily-research-heading">
        <div>
          <p className="panel-kicker">DAILY AUTONOMOUS RESEARCH</p>
          <h2>每日自動研究</h2>
          <p>不需開著網頁；每天兩輪延續 Train 研究、避開已測實驗並保存候選版本。</p>
        </div>
        <span className={running ? "daily-status running" : "daily-status enabled"}>
          {running ? "RUNNING" : "AUTOMATIC ON"}
        </span>
      </div>

      {error ? <div className="research-error" role="alert">{error}</div> : null}

      <div className="daily-research-grid">
        <article>
          <span>執行狀態</span>
          <strong>{status ? workflowLabel(status) : "讀取中…"}</strong>
          <small>{status?.schedule.label ?? "每日 06:30 與 18:30"}</small>
        </article>
        <article>
          <span>Research Engine</span>
          <strong>{audit?.system_ready ? "OPERATIONAL" : audit ? "FAIL CLOSED" : "等待全系統稽核"}</strong>
          <small>{audit ? `${audit.passed_check_count ?? 0} 項通過・${audit.failed_check_count ?? 0} 項失敗` : "每輪結束自動驗證完整生命週期"}</small>
        </article>
        <article>
          <span>下次自動研究</span>
          <strong>{formatTaipeiTime(status?.schedule.next_scheduled_at)}</strong>
          <small>Asia/Taipei・每天 {status?.schedule.sessions_per_day ?? 2} 輪</small>
        </article>
        <article>
          <span>最近完整快照</span>
          <strong>{formatTaipeiTime(snapshot?.generated_at_utc)}</strong>
          <small>{snapshot ? `${snapshot.completed_symbol_count ?? 0}/${snapshot.universe_size ?? 0} 檔完成` : "等待首次排程結果"}</small>
        </article>
        <article>
          <span>Promotion Gate</span>
          <strong>{snapshot ? `${snapshot.eligible_candidate_count ?? 0} 名具驗收資格` : "尚無候選"}</strong>
          <small>Final Holdout：{snapshot?.holdout_opened ? "異常開啟" : "搜尋階段保持鎖定"}</small>
        </article>
        <article>
          <span>Final Holdout 認證</span>
          <strong>{certifiedCount} 名正式認證</strong>
          <small>{certifiedCount > 0 ? "僅收錄一次性 Final Holdout 通過者" : "尚無通過者，研究會繼續"}</small>
        </article>
        <article>
          <span>研究所 → 競賽橋接</span>
          <strong>{challengerCount} 名認證挑戰者</strong>
          <small>{audit?.competition_research_loop_complete ? "閉環已接通・只讓認證版本參賽" : "等待閉環稽核"}</small>
        </article>
        <article>
          <span>冠軍挑戰結果</span>
          <strong>{promoted ? `新冠軍 ${tournament?.promotion?.promoted_robot_id ?? ""}` : tournament?.status === "completed" ? "舊冠軍守擂" : "等待認證挑戰者"}</strong>
          <small>{promoted ? `擊敗 ${tournament?.promotion?.defeated_incumbent_robot_id ?? "原冠軍"}` : tournament?.overall_leader?.robot_id ? `目前第一：${tournament.overall_leader.robot_id}` : "無認證者時不會硬產生新冠軍"}</small>
        </article>
      </div>

      {memory?.enabled ? (
        <div className="daily-memory-strip">
          <div>
            <span>跨日 Train 記憶</span>
            <strong>{formatMetric(memory.unique_experiment_count)} 組不重複實驗</strong>
            <small>
              {formatMetric(memory.continued_symbol_count)} 檔延續前次研究・
              {formatMetric(memory.verified_data_identity_symbol_count)}/
              {formatMetric(memory.completed_symbol_count)} 檔資料身分連續驗證
            </small>
          </div>
          <dl>
            <div><dt>本輪新實驗</dt><dd>{formatMetric(memory.last_run_new_experiment_count)}</dd></div>
            <div><dt>略過重複</dt><dd>{formatMetric(memory.last_run_duplicate_skip_count)}</dd></div>
            <div><dt>Train 菁英</dt><dd>{formatMetric(memory.elite_count)}</dd></div>
            <div><dt>待探索前沿</dt><dd>{formatMetric(memory.frontier_count)}</dd></div>
            <div><dt>策略家族</dt><dd>{formatMetric(memory.strategy_family_count)}</dd></div>
          </dl>
          <p>
            自適應回饋僅來自 Train；Validation 與 Final Holdout
            {memory.validation_feedback_used || memory.holdout_feedback_used ? " 發生異常回饋" : " 保持隔離"}。
          </p>
        </div>
      ) : null}

      {tournament?.status === "completed" && tournament.overall_leader ? (
        <div className="daily-top-candidate">
          <div>
            <span>研究所 × 機器人競賽・正式擂台</span>
            <strong>{tournament.overall_leader.robot_id}</strong>
            <small>
              {tournament.overall_leader.origin === "research_lab_certified" ? "Final Holdout 認證研究機器人" : "原競賽固定規則機器人"}・
              {tournament.overall_leader.qualified ? "正式冠軍資格" : "暫定第一"}
            </small>
          </div>
          <dl>
            <div><dt>排名</dt><dd>#{formatMetric(tournament.overall_leader.rank)}</dd></div>
            <div><dt>Forward 交易</dt><dd>{formatMetric(tournament.overall_leader.trade_count)}</dd></div>
            <div><dt>Wilson 下界</dt><dd>{formatMetric(tournament.overall_leader.wilson_lower_percent)}%</dd></div>
            <div><dt>認證挑戰者</dt><dd>{formatMetric(tournament.challenger_count)}</dd></div>
          </dl>
          <p>
            {tournament.promotion?.reason ?? "所有參賽者使用相同資金、成本、風控與 forward 排名規則。"}
            競賽結果不回灌同一研究 campaign 的 Train，避免二次過擬合。
          </p>
        </div>
      ) : null}

      {top ? (
        <div className="daily-top-candidate">
          <div>
            <span>最新最高證據候選・尚非正式冠軍</span>
            <strong>{top.stock_code}・{top.candidate_id}</strong>
            <small>
              {top.strategy_family}・{decisionLabel(top.decision)}・Research Score {formatMetric(top.research_score)}
            </small>
          </div>
          <dl>
            <div><dt>確認 Gate</dt><dd>{formatMetric(top.confirmation_gate_pass_count)}/{formatMetric(top.confirmation_gate_total)}</dd></div>
            <div><dt>DSR</dt><dd>{formatMetric(top.validation?.deflated_sharpe_probability_percent)}%</dd></div>
            <div><dt>Validation 報酬</dt><dd>{formatMetric(top.validation?.total_return_percent)}%</dd></div>
            <div><dt>Alpha</dt><dd>{formatMetric(top.validation?.alpha_percent)}%</dd></div>
            <div><dt>Wilson 下界</dt><dd>{formatMetric(top.validation?.wilson_lower_percent)}%</dd></div>
            <div><dt>最大回撤</dt><dd>{formatMetric(top.validation?.max_drawdown_percent)}%</dd></div>
          </dl>
          <p>
            排名採論文導向證據階層；Wilson 只作輔助 tie-breaker，Final Holdout 通過前不稱正式冠軍。
          </p>
        </div>
      ) : null}

      {status?.workflow?.url ? (
        <a className="daily-run-link" href={status.workflow.url} rel="noreferrer" target="_blank">
          查看自動研究執行紀錄
        </a>
      ) : null}
    </section>
  );
}
