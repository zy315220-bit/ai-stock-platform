import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const target = new URL("/api/sme-liquidity/forecast", request.url);
  const response = await fetch(target, {
    method: "POST",
    cache: "no-store",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      "sec-fetch-site": "same-origin",
    },
    body: JSON.stringify({
      custom_profile: {
        company_name: "自訂測試企業",
        industry: "出口製造",
        current_cash: 4200000,
        safety_cash_floor: 1200000,
        avg_monthly_inflow: 2760000,
        monthly_fixed_outflow: 2460000,
        monthly_payroll: 920000,
        largest_receivable_amount: 2100000,
        largest_receivable_due_days: 28,
        receivable_delay_mean_days: 11,
        largest_payable_amount: 1350000,
        largest_payable_due_days: 42,
        fx_receivable_share_percent: 55,
        income_volatility: "medium",
      },
    }),
  });

  if (!response.ok) {
    return NextResponse.json(
      { status: "FAIL_CLOSED", upstream_status: response.status },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }

  const payload = (await response.json()) as {
    profile?: { name?: string };
    engine?: { data_mode?: string; simulations?: number };
    horizons?: Array<{
      horizon_days?: number;
      shortfall_probability?: number;
    }>;
    guardrails?: { profile_persisted?: boolean };
  };

  return NextResponse.json(
    {
      status: "PASS",
      profile_name: payload.profile?.name ?? null,
      data_mode: payload.engine?.data_mode ?? null,
      simulations: payload.engine?.simulations ?? null,
      horizons: payload.horizons ?? null,
      profile_persisted: payload.guardrails?.profile_persisted ?? null,
    },
    {
      headers: {
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    },
  );
}
