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
  upstream.searchParams.set("max_experiments", "5");
  // Smoke-only policy: one completed validation trade is enough to exercise
  // survivor -> mutation -> generation-2 lineage. Production default remains 8.
  upstream.searchParams.set("min_validation_trades", "1");

  try {
    const response = await fetch(upstream, { method: "POST", cache: "no-store", signal: AbortSignal.timeout(55_000) });
    const body = await response.json().catch(() => null);
    const rounds = Array.isArray(body?.rounds) ? body.rounds : [];
    const generation2 = rounds.find((round: { generation?: number }) => round.generation === 2);
    const hasLineage = Boolean(generation2?.evaluated?.some((item: { candidate?: { parent_id?: string | null } }) => item?.candidate?.parent_id));
    return NextResponse.json(
      { ok: response.ok && hasLineage, upstream_status: response.status, lineage_verified: hasLineage, result: body },
      { status: response.ok && hasLineage ? 200 : 502 },
    );
  } catch (error) {
    return NextResponse.json({ ok: false, detail: error instanceof Error ? error.message : "Smoke test failed" }, { status: 502 });
  }
}
