import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const RESULT_URL =
  "https://raw.githubusercontent.com/zy315220-bit/ai-stock-platform/research-data/daily/latest.json";
const SYSTEM_AUDIT_URL =
  "https://raw.githubusercontent.com/zy315220-bit/ai-stock-platform/research-data/daily/diagnostics/research-system-audit.json";
const CERTIFIED_ROBOTS_URL =
  "https://raw.githubusercontent.com/zy315220-bit/ai-stock-platform/research-data/certified-robots.json";
const COMPETITION_CHALLENGERS_URL =
  "https://raw.githubusercontent.com/zy315220-bit/ai-stock-platform/research-data/competition/challengers.json";
const COMPETITION_TOURNAMENT_URL =
  "https://raw.githubusercontent.com/zy315220-bit/ai-stock-platform/research-data/competition/latest-tournament.json";
const WORKFLOW_RUNS_URL =
  "https://api.github.com/repos/zy315220-bit/ai-stock-platform/actions/workflows/daily-autoresearch.yml/runs?per_page=1";

const DAILY_RESEARCH_UTC_HOURS = [10, 22] as const;

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

function nextTaipeiDailyRun(now = new Date()): string {
  const candidates = DAILY_RESEARCH_UTC_HOURS.map((hour) => {
    const candidate = new Date(now);
    candidate.setUTCHours(hour, 30, 0, 0);
    if (candidate <= now) candidate.setUTCDate(candidate.getUTCDate() + 1);
    return candidate;
  });

  const next = candidates.reduce((earliest, candidate) =>
    candidate < earliest ? candidate : earliest,
  );
  return next.toISOString();
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
  const [
    snapshotResult,
    workflowResult,
    auditResult,
    certifiedResult,
    challengersResult,
    tournamentResult,
  ] = await Promise.allSettled([
    fetchJson(RESULT_URL),
    fetchJson(WORKFLOW_RUNS_URL),
    fetchJson(SYSTEM_AUDIT_URL),
    fetchJson(CERTIFIED_ROBOTS_URL),
    fetchJson(COMPETITION_CHALLENGERS_URL),
    fetchJson(COMPETITION_TOURNAMENT_URL),
  ]);
  const snapshot =
    snapshotResult.status === "fulfilled" ? snapshotResult.value : null;
  const systemAudit =
    auditResult.status === "fulfilled" ? auditResult.value : null;
  const certifiedRobots =
    certifiedResult.status === "fulfilled" ? certifiedResult.value : null;
  const competitionChallengers =
    challengersResult.status === "fulfilled" ? challengersResult.value : null;
  const competitionTournament =
    tournamentResult.status === "fulfilled" ? tournamentResult.value : null;
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
      cron: "30 22,10 * * *",
      timezone: "Asia/Taipei",
      label: "每日 06:30 與 18:30",
      sessions_per_day: 2,
      next_scheduled_at: nextTaipeiDailyRun(),
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
    system_audit: systemAudit,
    certified_robots: certifiedRobots,
    competition_challengers: competitionChallengers,
    competition_tournament: competitionTournament,
    snapshot_available: snapshot !== null,
    status_sources: {
      snapshot: snapshotResult.status,
      workflow: workflowResult.status,
      system_audit: auditResult.status,
      certified_robots: certifiedResult.status,
      competition_challengers: challengersResult.status,
      competition_tournament: tournamentResult.status,
    },
  });
}
