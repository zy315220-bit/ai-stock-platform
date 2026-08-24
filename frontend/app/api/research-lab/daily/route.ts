import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const RESULT_URL =
  "https://raw.githubusercontent.com/zy315220-bit/ai-stock-platform/research-data/daily/latest.json";
const WORKFLOW_RUNS_URL =
  "https://api.github.com/repos/zy315220-bit/ai-stock-platform/actions/workflows/daily-autoresearch.yml/runs?per_page=1";

type WorkflowRun = {
  id?: number;
  status?: string;
  conclusion?: string | null;
  event?: string;
  created_at?: string;
  updated_at?: string;
  run_started_at?: string;
  html_url?: string;
};

function nextTaipeiWeekdayRun(now = new Date()): string {
  const candidate = new Date(now);
  candidate.setUTCHours(10, 30, 0, 0);
  if (candidate <= now) candidate.setUTCDate(candidate.getUTCDate() + 1);
  while (candidate.getUTCDay() === 0 || candidate.getUTCDay() === 6) {
    candidate.setUTCDate(candidate.getUTCDate() + 1);
  }
  return candidate.toISOString();
}

async function fetchJson(url: string): Promise<unknown> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": "ai-stock-platform-autoresearch-status",
    },
    next: { revalidate: 300 },
  });
  if (!response.ok) throw new Error(`GitHub returned ${response.status}`);
  return response.json();
}

export async function GET() {
  const [snapshotResult, workflowResult] = await Promise.allSettled([
    fetchJson(RESULT_URL),
    fetchJson(WORKFLOW_RUNS_URL),
  ]);
  const snapshot =
    snapshotResult.status === "fulfilled" ? snapshotResult.value : null;
  const workflowPayload =
    workflowResult.status === "fulfilled" &&
    workflowResult.value &&
    typeof workflowResult.value === "object"
      ? (workflowResult.value as { workflow_runs?: WorkflowRun[] })
      : null;
  const latestRun = workflowPayload?.workflow_runs?.[0] ?? null;

  return NextResponse.json({
    enabled: true,
    manual_action_required: false,
    schedule: {
      cron: "30 10 * * 1-5",
      timezone: "Asia/Taipei",
      label: "每個台股交易日 18:30",
      next_scheduled_at: nextTaipeiWeekdayRun(),
    },
    workflow: latestRun
      ? {
          id: latestRun.id,
          status: latestRun.status,
          conclusion: latestRun.conclusion,
          event: latestRun.event,
          created_at: latestRun.created_at,
          started_at: latestRun.run_started_at,
          updated_at: latestRun.updated_at,
          url: latestRun.html_url,
        }
      : null,
    latest_snapshot: snapshot,
    snapshot_available: snapshot !== null,
    status_sources: {
      snapshot: snapshotResult.status,
      workflow: workflowResult.status,
    },
  });
}
