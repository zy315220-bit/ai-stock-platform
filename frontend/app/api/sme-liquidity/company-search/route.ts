import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const ENDPOINT =
  "https://data.gcis.nat.gov.tw/od/data/api/6BBA2268-1367-4B42-9CCA-BC17499EBE8C";

const COMPANY_ALIASES: Record<string, string> = {
  台積電: "台灣積體電路製造",
  tsmc: "台灣積體電路製造",
  鴻海: "鴻海精密工業",
  聯發科: "聯發科技",
};

type GcisCompany = {
  Business_Accounting_NO?: string | number;
  Company_Name?: string;
  Company_Status_Desc?: string;
  Capital_Stock_Amount?: number | string;
  Paid_In_Capital_Amount?: number | string;
  Company_Location?: string;
};

function cleanQuery(value: string) {
  return value
    .normalize("NFKC")
    .trim()
    .replace(/[^\p{L}\p{N}\s·・\-（）()股份有限公司企業商行]/gu, "")
    .slice(0, 24);
}

function resolveSearchQuery(q: string) {
  return COMPANY_ALIASES[q.toLowerCase()] ?? q;
}

function num(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get("q") ?? "";
  const q = cleanQuery(raw);

  if (!q) {
    return NextResponse.json(
      { query: "", results: [], source: "MOEA_GCIS" },
      { headers: { "cache-control": "no-store" } },
    );
  }

  const resolvedQuery = resolveSearchQuery(q);
  const url = new URL(ENDPOINT);
  url.searchParams.set("$format", "json");
  url.searchParams.set(
    "$filter",
    `Company_Name like ${resolvedQuery} and Company_Status eq 01`,
  );
  url.searchParams.set("$skip", "0");
  url.searchParams.set("$top", "8");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4500);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        accept: "application/json",
        "user-agent": "SME-Liquidity-Radar-Competition-PoC/1.0",
      },
      next: { revalidate: 3600 },
    });

    if (!response.ok) {
      return NextResponse.json(
        {
          query: q,
          resolved_query: resolvedQuery,
          results: [],
          source: "MOEA_GCIS",
          degraded: true,
        },
        {
          status: 200,
          headers: {
            "cache-control": "public, s-maxage=60, stale-while-revalidate=300",
            "x-content-type-options": "nosniff",
          },
        },
      );
    }

    const payload = (await response.json()) as unknown;
    const rows = Array.isArray(payload) ? (payload as GcisCompany[]) : [];

    const seen = new Set<string>();
    const results = rows
      .map((row) => {
        const name =
          typeof row.Company_Name === "string" ? row.Company_Name.trim() : "";
        const businessNo = String(row.Business_Accounting_NO ?? "").trim();
        return {
          business_no: businessNo,
          name,
          status:
            typeof row.Company_Status_Desc === "string"
              ? row.Company_Status_Desc
              : "",
          capital: num(row.Capital_Stock_Amount),
          paid_in_capital: num(row.Paid_In_Capital_Amount),
          location:
            typeof row.Company_Location === "string"
              ? row.Company_Location
              : "",
        };
      })
      .filter((row) => {
        if (!row.name || !row.business_no) return false;
        const key = `${row.business_no}:${row.name}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 8);

    return NextResponse.json(
      {
        query: q,
        resolved_query: resolvedQuery,
        results,
        source: "MOEA_GCIS",
        attribution: "資料來源：經濟部商業發展署商工行政資料開放平臺",
      },
      {
        headers: {
          "cache-control":
            "public, s-maxage=3600, stale-while-revalidate=86400",
          "x-content-type-options": "nosniff",
        },
      },
    );
  } catch {
    return NextResponse.json(
      {
        query: q,
        resolved_query: resolvedQuery,
        results: [],
        source: "MOEA_GCIS",
        degraded: true,
      },
      {
        status: 200,
        headers: {
          "cache-control": "no-store",
          "x-content-type-options": "nosniff",
        },
      },
    );
  } finally {
    clearTimeout(timer);
  }
}
