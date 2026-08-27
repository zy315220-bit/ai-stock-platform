import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json(
      { error: "not found" },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  }

  const target = new URL("/api/sme-liquidity/forecast", request.url);
  const response = await fetch(target, {
    method: "POST",
    cache: "no-store",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      "sec-fetch-site": "same-origin",
    },
    body: JSON.stringify({ profile_id: "exporter" }),
  });

  if (!response.ok) {
    return NextResponse.json(
      {
        status: "FAIL_CLOSED",
        upstream_status: response.status,
      },
      {
        status: 503,
        headers: { "cache-control": "no-store" },
      },
    );
  }

  const payload = (await response.json()) as {
    engine?: { version?: string; simulations?: number };
    horizons?: Array<{
      horizon_days?: number;
      shortfall_probability?: number;
      ending_cash_p50?: number;
    }>;
    stress_tests?: Array<{
      stress?: string;
      shortfall_probability?: number;
    }>;
    guardrails?: Record<string, unknown>;
  };

  const combined = payload.stress_tests?.find(
    (item) => item.stress === "combined",
  );

  return NextResponse.json(
    {
      status: "PASS",
      engine: payload.engine,
      horizons: payload.horizons,
      combined_stress_probability: combined?.shortfall_probability ?? null,
      guardrails: payload.guardrails,
    },
    {
      headers: {
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    },
  );
}
