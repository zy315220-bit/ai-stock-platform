import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET() {
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) return NextResponse.json({ ok: false, detail: "Backend service is not configured" }, { status: 503 });

  const upstream = new URL("/api/research-lab/run", backendUrl);
  upstream.searchParams.set("stock_code", "2330");
  upstream.searchParams.set("start_date", "2023-01-01");
  upstream.searchParams.set("end_date", "2025-08-07");
  upstream.searchParams.set("max_generations", "2");
  upstream.searchParams.set("max_experiments", "9");
  upstream.searchParams.set("min_validation_trades", "1");

  try {
    const response = await fetch(upstream, { method: "POST", cache: "no-store", signal: AbortSignal.timeout(55_000) });
    const body = await response.json().catch(() => null);
    const rounds = Array.isArray(body?.rounds) ? body.rounds : [];
    const generation2 = rounds.find((round: { generation?: number }) => round.generation === 2);
    const lineageItems = Array.isArray(generation2?.evaluated)
      ? generation2.evaluated.filter((item: { candidate?: { parent_id?: string | null } }) => Boolean(item?.candidate?.parent_id))
      : [];
    const hasLineage = lineageItems.length > 0;
    const researchPayloadValid = Boolean(
      body &&
      typeof body.experiments_run === "number" &&
      typeof body.generations_run === "number" &&
      body.research_audit?.holdout_used_during_search === false &&
      body.holdout_status === "LOCKED_REQUIRES_PROMOTION_GATE"
    );
    const systemHealthy = response.ok && researchPayloadValid;
    const researchOutcome = hasLineage
      ? "LINEAGE_PRODUCED"
      : body?.stopped_reason === "no_surviving_candidates"
        ? "NO_CANDIDATE_PASSED_VALIDATION"
        : "NO_LINEAGE_PRODUCED";

    return NextResponse.json(
      {
        ok: systemHealthy,
        system_healthy: systemHealthy,
        upstream_status: response.status,
        research_outcome: researchOutcome,
        lineage_verified: hasLineage,
        generation2_lineage_count: lineageItems.length,
        result: body,
      },
      { status: systemHealthy ? 200 : 502 },
    );
  } catch (error) {
    return NextResponse.json({ ok: false, system_healthy: false, detail: error instanceof Error ? error.message : "Smoke test failed" }, { status: 502 });
  }
}
