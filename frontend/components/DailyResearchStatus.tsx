"use client";

import { useEffect, useState } from "react";

type Candidate = {
  stock_code?: string;
  candidate_id?: string;
  strategy_family?: string;
  research_score?: number;
  eligible_for_one_shot_holdout?: boolean;
  regime_robust?: boolean;
  validation?: {
    wilson_lower_percent?: number;
    total_return_percent?: number;
    max_drawdown_percent?: number;
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

type DailyStatus = {
  enabled: boolean;
  manual_action_required: boolean;
  schedule: {
    label: string;
    timezone: string;
    next_scheduled_at: string;
  };
  workflow: null | {
    status?: string;
    conclusion?: string | null;
    updated_at?: string;
    url?: string;
  };
  latest_snapshot: DailySnapshot | null;
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
  const running = status?.workflow?.status === "in_progress";

  return (
    <section className="daily-research-card" aria-live="polite">
      <div className="daily-research-heading">
        <div>
          <p className="panel-kicker">DAILY AUTONOMOUS RESEARCH</p>
          <h2>每日自動研究</h2>
          <p>不需開著網頁；每天會延續前次 Train 研究、避開已測實驗並保存候選版本。</p>
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
          <small>{status?.schedule.label ?? "每個台股交易日 18:30"}</small>
        </article>
        <article>
          <span>下次自動研究</span>
          <strong>{formatTaipeiTime(status?.schedule.next_scheduled_at)}</strong>
          <small>Asia/Taipei・無需手動</small>
        </article>
        <article>
          <span>最近完整快照</span>
          <strong>{formatTaipeiTime(snapshot?.generated_at_utc)}</strong>
          <small>{snapshot ? `${snapshot.completed_symbol_count ?? 0}/${snapshot.universe_size ?? 0} 檔完成` : "等待首次排程結果"}</small>
        </article>
        <article>
          <span>Promotion Gate</span>
          <strong>{snapshot ? `${snapshot.eligible_candidate_count ?? 0} 名具驗收資格` : "尚無候選"}</strong>
          <small>Final Holdout：{snapshot?.holdout_opened ? "異常開啟" : "鎖定"}</small>
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

      {top ? (
        <div className="daily-top-candidate">
          <div>
            <span>最新最高證據候選・尚非正式冠軍</span>
            <strong>{top.stock_code}・{top.candidate_id}</strong>
            <small>{top.strategy_family}・Research Score {formatMetric(top.research_score)}</small>
          </div>
          <dl>
            <div><dt>Wilson 下界</dt><dd>{formatMetric(top.validation?.wilson_lower_percent)}%</dd></div>
            <div><dt>Validation 報酬</dt><dd>{formatMetric(top.validation?.total_return_percent)}%</dd></div>
            <div><dt>最大回撤</dt><dd>{formatMetric(top.validation?.max_drawdown_percent)}%</dd></div>
          </dl>
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
