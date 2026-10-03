type Snapshot = {
  generated_at_utc?: string;
  integrity_status?: string;
  completed_symbol_count?: number;
  universe_size?: number;
};

type Workflow = { status?: string; conclusion?: string | null };
type Audit = { generated_at_utc?: string; system_ready?: boolean };

export type ResearchHealth = {
  state: "OPERATIONAL" | "RUNNING" | "QUEUED" | "DEGRADED" | "WAITING";
  label: string;
  reason: string;
  snapshot_fresh: boolean;
  snapshot_age_hours: number | null;
  audit_current: boolean;
};

function timestamp(value?: string): number | null {
  const parsed = value ? Date.parse(value) : NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

export function getResearchHealth(
  snapshot: Snapshot | null,
  workflow: Workflow | null,
  audit: Audit | null,
  now = Date.now(),
): ResearchHealth {
  const generated = timestamp(snapshot?.generated_at_utc);
  const age = generated === null ? null : (now - generated) / 3_600_000;
  // Two runs are scheduled per day; a full day without a complete result
  // must be visible even when the last persisted integrity audit passed.
  const fresh = age !== null && age >= 0 && age <= 24;
  const audited = timestamp(audit?.generated_at_utc);
  const auditCurrent = Boolean(
    audit?.system_ready && generated !== null && audited !== null &&
    audited >= generated && audited <= now,
  );
  const base = {
    snapshot_fresh: fresh,
    snapshot_age_hours: age === null ? null : Math.round(age * 100) / 100,
    audit_current: auditCurrent,
  };
  if (workflow?.status === "in_progress") {
    return { ...base, state: "RUNNING", label: "研究執行中",
      reason: fresh ? "完成後發布新結果。" : "目前展示的是舊結果；等待本輪完整發布。" };
  }
  if (["queued", "pending", "waiting", "requested"].includes(workflow?.status ?? "")) {
    return { ...base, state: "QUEUED", label: "研究已排入佇列",
      reason: "尚未完成本輪研究。" };
  }
  if (workflow?.conclusion && workflow.conclusion !== "success") {
    return { ...base, state: "DEGRADED", label: "研究更新中斷",
      reason: "最近一輪研究未成功，舊稽核不代表目前正常運作。" };
  }
  if (!snapshot) {
    return { ...base, state: "WAITING", label: "等待完整研究結果",
      reason: "尚未取得可驗證的研究快照。" };
  }
  if (!fresh) {
    return { ...base, state: "DEGRADED", label: "研究結果已過期",
      reason: "超過 24 小時沒有完整新結果，請查看最新執行紀錄。" };
  }
  if (snapshot.integrity_status !== "PASS" || !auditCurrent ||
      !snapshot.universe_size || snapshot.completed_symbol_count !== snapshot.universe_size) {
    return { ...base, state: "DEGRADED", label: "研究完整性待確認",
      reason: "最新快照或對應稽核不完整，不能標示正常運作。" };
  }
  if (!workflow || workflow.conclusion !== "success") {
    return { ...base, state: "DEGRADED", label: "執行狀態待確認",
      reason: "無法確認最近一輪排程是否成功。" };
  }
  return { ...base, state: "OPERATIONAL", label: "自動研究正常",
    reason: "最新完整結果與對應稽核均已通過。" };
}
