import { NextRequest } from "next/server";

import { BACKEND_API_URL } from "@/lib/server/backend";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

const SNAPSHOT_URL =
  "https://raw.githubusercontent.com/zy315220-bit/ai-stock-platform/research-data/daily/latest.json";
const MAX_BODY_BYTES = 2_048;

type Candidate = {
  stock_code?: string;
  candidate_id?: string;
  strategy_family?: string;
  confirmation_gate_pass_count?: number;
  confirmation_gate_total?: number;
  eligible_for_one_shot_holdout?: boolean;
  validation?: {
    max_drawdown_percent?: number;
  };
};

type Snapshot = {
  integrity_status?: string;
  candidate_count?: number;
  candidates?: Candidate[];
};

type Suitability = {
  risk_code?: string;
  max_research_drawdown_percent?: number;
};

function sameOrigin(request: NextRequest): boolean {
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    return new URL(origin).host === request.nextUrl.host;
  } catch {
    return false;
  }
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) {
    return Response.json(
      { detail: "拒絕跨站請求。" },
      { status: 403, headers: { "cache-control": "no-store" } },
    );
  }

  const type = request.headers.get("content-type") ?? "";
  if (!type.toLowerCase().startsWith("application/json")) {
    return Response.json(
      { detail: "只接受 application/json。" },
      { status: 415, headers: { "cache-control": "no-store" } },
    );
  }

  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) {
    return Response.json(
      { detail: "請求內容過大。" },
      { status: 413, headers: { "cache-control": "no-store" } },
    );
  }

  let profile: unknown;
  try {
    profile = JSON.parse(raw);
  } catch {
    return Response.json(
      { detail: "JSON 格式錯誤。" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);

  try {
    const [suitabilityResponse, snapshotResponse] = await Promise.all([
      fetch(new URL("/api/tbb-wealth/suitability", BACKEND_API_URL), {
        method: "POST",
        cache: "no-store",
        headers: {
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify(profile),
        signal: controller.signal,
      }),
      fetch(SNAPSHOT_URL, {
        cache: "no-store",
        headers: {
          accept: "application/json",
          "user-agent": "bizwealth-guard-research-gate",
        },
        signal: controller.signal,
      }),
    ]);

    if (!suitabilityResponse.ok) {
      const body = await suitabilityResponse.arrayBuffer();
      return new Response(body, {
        status: suitabilityResponse.status,
        headers: {
          "cache-control": "no-store",
          "content-type":
            suitabilityResponse.headers.get("content-type") ??
            "application/json",
        },
      });
    }

    if (!snapshotResponse.ok) {
      return Response.json(
        { detail: "研究證據來源不可用，依 fail-closed 原則停止。" },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }

    const suitability = (await suitabilityResponse.json()) as Suitability;
    const snapshot = (await snapshotResponse.json()) as Snapshot;
    const boundary = finiteNumber(
      suitability.max_research_drawdown_percent,
    );

    if (
      !suitability.risk_code ||
      boundary === null ||
      snapshot.integrity_status !== "PASS" ||
      !Array.isArray(snapshot.candidates)
    ) {
      return Response.json(
        { detail: "研究或適合度證據不完整，依 fail-closed 原則停止。" },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }

    const rows = snapshot.candidates.map((candidate) => {
      const drawdown = finiteNumber(candidate.validation?.max_drawdown_percent);
      const researchGatePass =
        candidate.eligible_for_one_shot_holdout === true;
      const profileBoundaryPass =
        drawdown !== null && drawdown <= boundary;

      return {
        stock_code: candidate.stock_code ?? null,
        candidate_id: candidate.candidate_id ?? null,
        strategy_family: candidate.strategy_family ?? null,
        confirmation_gate_pass_count:
          candidate.confirmation_gate_pass_count ?? 0,
        confirmation_gate_total: candidate.confirmation_gate_total ?? 7,
        max_drawdown_percent: drawdown,
        research_gate_pass: researchGatePass,
        profile_boundary_pass: profileBoundaryPass,
        combined_pass: researchGatePass && profileBoundaryPass,
        state: !researchGatePass
          ? "RESEARCH_EVIDENCE_HOLD"
          : !profileBoundaryPass
            ? "PROFILE_BOUNDARY_BLOCK"
            : "HUMAN_REVIEW_ELIGIBLE",
      };
    });

    return Response.json(
      {
        source: "server_fetched_immutable_research_snapshot",
        fail_closed: true,
        risk_code: suitability.risk_code,
        max_research_drawdown_percent: boundary,
        candidate_count: snapshot.candidate_count ?? rows.length,
        profile_boundary_pass_count: rows.filter(
          (row) => row.profile_boundary_pass,
        ).length,
        combined_pass_count: rows.filter((row) => row.combined_pass).length,
        rows: rows.slice(0, 5),
      },
      {
        status: 200,
        headers: {
          "cache-control": "no-store",
          "x-content-type-options": "nosniff",
        },
      },
    );
  } catch {
    return Response.json(
      { detail: "雙閘門服務不可用，依 fail-closed 原則停止。" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  } finally {
    clearTimeout(timeout);
  }
}
