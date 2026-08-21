import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET() {
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    return NextResponse.json({ ok: false, detail: "Backend service is not configured" }, { status: 503 });
  }

  const upstream = new URL("/api/research-lab/run", backendUrl);
  upstream.searchParams.set("stock_code", "2330");
  upstream.searchParams.set("start_date", "2024-01-01");
  upstream.searchParams.set("end_date", "2025-12-31");
  upstream.searchParams.set("max_generations", "1");
  upstream.searchParams.set("max_experiments", "1");

  try {
    const response = await fetch(upstream, {
      method: "POST",
      cache: "no-store",
      signal: AbortSignal.timeout(55_000),
    });
    const body = await response.json().catch(() => null);
    return NextResponse.json(
      {
        ok: response.ok,
        upstream_status: response.status,
        result: body,
      },
      { status: response.ok ? 200 : 502 },
    );
  } catch (error) {
    return NextResponse.json(
      { ok: false, detail: error instanceof Error ? error.message : "Smoke test failed" },
      { status: 502 },
    );
  }
}
