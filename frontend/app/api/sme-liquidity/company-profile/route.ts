import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BASIC_ENDPOINT = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6";
const BUSINESS_ENDPOINT = "https://data.gcis.nat.gov.tw/od/data/api/236EE382-4942-41A9-BD03-CA0709025E7C";
const TWSE_LISTED_COMPANY_ENDPOINT = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L";
const TWSE_PUBLIC_COMPANY_ENDPOINT = "https://openapi.twse.com.tw/v1/opendata/t187ap03_P";
const TPEX_OTC_COMPANY_ENDPOINT = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O";
const MOPS_LISTED_CSV = "https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv";
const MOPS_PUBLIC_CSV = "https://mopsfin.twse.com.tw/opendata/t187ap03_P.csv";
const MOPS_OTC_CSV = "https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv";
const SME_PAID_CAPITAL_CRITERION = 100_000_000;

type JsonObject = Record<string, unknown>;
type Range = { low: number; mid: number; high: number; unit: "TWD" | "days" | "percent" };

type PublicCompanyMatch = {
  company_code: string;
  company_name: string;
  industry: string;
  market_type: "PUBLIC_MARKET_COMPANY" | "PUBLIC_COMPANY";
  source: "OFFICIAL_MARKET_OPENAPI" | "OFFICIAL_MOPS_CSV";
  match_method: "BUSINESS_NO" | "COMPANY_NAME";
};

function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function firstObject(payload: unknown): JsonObject | null {
  if (!Array.isArray(payload)) return isObject(payload) ? payload : null;
  return payload.find(isObject) ?? null;
}
function numberOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
function stringValue(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}
function normalizeBusinessNo(value: unknown) {
  const digits = String(value ?? "").replace(/\D/g, "");
  return digits.length === 8 ? digits : "";
}
function normalizedName(value: unknown) {
  return stringValue(value)
    .replace(/[\s　]/g, "")
    .replace(/股份有限公司$/, "")
    .replace(/有限公司$/, "")
    .toLowerCase();
}
function collectBusinessItems(payload: unknown) {
  const found: string[] = [];
  function walk(value: unknown) {
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    if (!isObject(value)) return;
    const desc = value.Business_Item_Desc;
    if (typeof desc === "string" && desc.trim() && !found.includes(desc.trim())) {
      found.push(desc.trim());
    }
    Object.values(value).forEach(walk);
  }
  walk(payload);
  return found.slice(0, 30);
}

function inferIndustry(name: string, items: string[]) {
  const text = `${name} ${items.join(" ")}`;
  const rules = [
    ["半導體／電子製造", ["半導體", "積體電路", "電子零組件", "晶圓", "光電", "電子材料"], 0.93],
    ["製造業", ["製造", "加工", "機械", "精密", "金屬", "塑膠", "零組件"], 0.86],
    ["批發貿易", ["批發", "國際貿易", "貿易", "進出口"], 0.85],
    ["零售", ["零售", "百貨", "商店"], 0.82],
    ["資訊服務／軟體", ["資訊軟體", "資訊服務", "資料處理", "軟體", "數位", "網路"], 0.9],
    ["專業服務", ["顧問", "設計", "研究", "管理顧問", "技術服務"], 0.8],
    ["營建工程", ["營造", "工程", "建築", "建設", "土木"], 0.87],
    ["食品餐飲", ["食品", "飲料", "餐飲", "餐館"], 0.87],
    ["運輸物流", ["運輸", "倉儲", "物流", "貨運"], 0.87],
    ["生技醫療", ["生技", "醫療", "醫材", "藥品", "生物技術"], 0.87],
  ] as const;
  const ranked = rules
    .map(([label, keywords, confidence]) => ({
      label,
      keywords,
      confidence,
      hits: keywords.filter((keyword) => text.includes(keyword)).length,
    }))
    .filter((row) => row.hits > 0)
    .sort((a, b) => b.hits - a.hits || b.confidence - a.confidence);
  if (!ranked.length) {
    return {
      label: "一般企業",
      confidence: 0.45,
      reason: "公開營業項目不足以明確歸類，先採一般企業基準。",
    };
  }
  const best = ranked[0];
  return {
    label: best.label,
    confidence: Math.min(0.97, best.confidence + Math.max(0, best.hits - 1) * 0.02),
    reason: `依公開營業項目中的「${best.keywords.filter((k) => text.includes(k)).slice(0, 3).join("、")}」推測。`,
  };
}

function round10k(value: number) {
  return Math.max(0, Math.round(value / 10_000) * 10_000);
}
function moneyRange(mid: number, spread = 0.35): Range {
  return { low: round10k(mid * (1 - spread)), mid: round10k(mid), high: round10k(mid * (1 + spread)), unit: "TWD" };
}
function dayRange(mid: number, spread = 7): Range {
  return { low: Math.max(1, Math.round(mid - spread)), mid: Math.max(1, Math.round(mid)), high: Math.max(1, Math.round(mid + spread)), unit: "days" };
}
function percentRange(mid: number, spread = 12): Range {
  return { low: Math.max(0, Math.round(mid - spread)), mid: Math.max(0, Math.min(100, Math.round(mid))), high: Math.max(0, Math.min(100, Math.round(mid + spread))), unit: "percent" };
}

function buildEstimate(paidCapital: number | null, stockCapital: number | null, industry: string, businessItems: string[]) {
  const capital = Math.min(SME_PAID_CAPITAL_CRITERION, Math.max(1_000_000, paidCapital ?? stockCapital ?? 10_000_000));
  const defaultParams = { annualRevenueToCapital: 3.5, fixedCostRatio: 0.55, payrollRatio: 0.18, arRatio: 0.3, apRatio: 0.25, cashMonths: 0.6, delayDays: 10, fxShare: 10, volatility: "medium" as const };
  const specialized: Record<string, typeof defaultParams> = {
    "半導體／電子製造": { ...defaultParams, annualRevenueToCapital: 4.2, fixedCostRatio: 0.52, payrollRatio: 0.17, arRatio: 0.42, apRatio: 0.35, cashMonths: 0.7, fxShare: 45 },
    製造業: { ...defaultParams, annualRevenueToCapital: 3.8, fixedCostRatio: 0.56, payrollRatio: 0.16, arRatio: 0.38, apRatio: 0.34, cashMonths: 0.65, delayDays: 12, fxShare: 28 },
    批發貿易: { ...defaultParams, annualRevenueToCapital: 6.0, fixedCostRatio: 0.62, payrollRatio: 0.1, arRatio: 0.45, apRatio: 0.42, cashMonths: 0.5, delayDays: 15, fxShare: 32 },
    "資訊服務／軟體": { ...defaultParams, annualRevenueToCapital: 3.2, fixedCostRatio: 0.36, payrollRatio: 0.42, arRatio: 0.32, apRatio: 0.12, cashMonths: 0.9, delayDays: 8, fxShare: 12 },
    專業服務: { ...defaultParams, annualRevenueToCapital: 2.8, fixedCostRatio: 0.32, payrollRatio: 0.46, arRatio: 0.35, apRatio: 0.1, cashMonths: 0.85, fxShare: 6 },
  };
  const p = specialized[industry] ?? defaultParams;
  const monthlyInflow = (capital * p.annualRevenueToCapital) / 12;
  const monthlyFixed = monthlyInflow * p.fixedCostRatio;
  const payroll = monthlyInflow * p.payrollRatio;
  const currentCash = monthlyInflow * p.cashMonths;
  const safetyFloor = (monthlyFixed + payroll) * 0.45;
  const hasInternationalTrade = businessItems.some((item) => item.includes("國際貿易") || item.includes("進出口"));
  const fxShare = hasInternationalTrade ? Math.max(p.fxShare, 30) : p.fxShare;
  return {
    basis: "illustrative_industry_capital_prior_v1",
    calibration_status: "SCENARIO_PRIOR_NOT_EMPIRICALLY_CALIBRATED",
    disclaimer: "快速模式使用公開產業／資本額建立情境先驗，用來示範風險篩檢流程；不是公司真實財務資料，也不是經官方產業中位數校準的財務預測。補入企業真實現金流後才適合做較高信心判讀。",
    fields: {
      current_cash: moneyRange(currentCash, 0.4),
      safety_cash_floor: moneyRange(safetyFloor, 0.35),
      avg_monthly_inflow: moneyRange(monthlyInflow, 0.4),
      monthly_fixed_outflow: moneyRange(monthlyFixed, 0.35),
      monthly_payroll: moneyRange(payroll, 0.35),
      largest_receivable_amount: moneyRange(monthlyInflow * p.arRatio, 0.45),
      largest_receivable_due_days: dayRange(30, 12),
      receivable_delay_mean_days: dayRange(p.delayDays, 6),
      largest_payable_amount: moneyRange(monthlyInflow * p.apRatio, 0.45),
      largest_payable_due_days: dayRange(35, 12),
      fx_receivable_share_percent: percentRange(fxShare, 12),
      income_volatility: p.volatility,
    },
  };
}

function publicCompanyFromObject(row: JsonObject, businessNo: string, companyName: string, source: PublicCompanyMatch["source"]): PublicCompanyMatch | null {
  const idKeys = ["營利事業統一編號", "統一編號", "Business_Accounting_NO", "BusinessAccountingNO", "business_no"];
  const nameKeys = ["公司名稱", "公司簡稱", "Company_Name", "CompanyName", "公司"];
  const idMatched = idKeys.some((key) => normalizeBusinessNo(row[key]) === businessNo);
  const target = normalizedName(companyName);
  const rowNames = nameKeys.map((key) => normalizedName(row[key])).filter(Boolean);
  const nameMatched = Boolean(target) && rowNames.some((name) => name === target || name.includes(target) || target.includes(name));
  if (!idMatched && !nameMatched) return null;
  const companyCode = stringValue(row["公司代號"]) || stringValue(row["公司代碼"]) || stringValue(row["證券代號"]) || stringValue(row["Company_Code"]);
  return {
    company_code: companyCode,
    company_name: stringValue(row["公司名稱"]) || stringValue(row["公司簡稱"]) || stringValue(row["Company_Name"]),
    industry: stringValue(row["產業別"]) || stringValue(row["產業類別"]) || stringValue(row["Industry"]),
    market_type: companyCode ? "PUBLIC_MARKET_COMPANY" : "PUBLIC_COMPANY",
    source,
    match_method: idMatched ? "BUSINESS_NO" : "COMPANY_NAME",
  };
}

function findPublicCompany(payload: unknown, businessNo: string, companyName: string, source: PublicCompanyMatch["source"]): PublicCompanyMatch | null {
  if (!Array.isArray(payload)) return null;
  for (const row of payload) {
    if (!isObject(row)) continue;
    const found = publicCompanyFromObject(row, businessNo, companyName, source);
    if (found) return found;
  }
  return null;
}

function parseCsv(text: string): JsonObject[] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '"') {
      if (quoted && text[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (ch === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cell);
      cell = "";
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
    } else {
      cell += ch;
    }
  }
  if (cell.length || row.length) {
    row.push(cell);
    if (row.some((value) => value.length > 0)) rows.push(row);
  }
  if (rows.length < 2) return [];
  const headers = rows[0].map((value) => value.replace(/^\uFEFF/, "").trim());
  return rows.slice(1).map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function assessQuickEstimateEligibility(paidCapital: number | null, stockCapital: number | null, industryConfidence: number, businessItems: string[], publicCompany: PublicCompanyMatch | null) {
  const capital = paidCapital ?? stockCapital ?? null;
  const reasons: string[] = [];
  let status: "CAUTION" | "NOT_RECOMMENDED" = "CAUTION";
  if (publicCompany) {
    status = "NOT_RECOMMENDED";
    reasons.push("已由官方市場資料辨識為公開市場／公開發行公司；此競賽版不套用 SME 快速 scenario prior，完整產品應改接公開財報後另行建模。");
  }
  if (capital === null) {
    reasons.push("缺少可用的登記／實收資本額，無法由公開資料確認是否符合 SME 資本額判準。");
  } else if (capital > SME_PAID_CAPITAL_CRITERION) {
    status = "NOT_RECOMMENDED";
    reasons.push("實收／出資額超過 1 億元，無法僅靠資本額確認 SME 身分；依現行標準仍可能因經常僱用員工未滿 200 人而符合，但需先取得員工數或真實財務資料。");
    reasons.push("本快速 baseline 不對超出 1 億元資本額判準的公司直接放行，避免假精準。");
  } else {
    reasons.push("實收／出資額落在現行 SME 資本額判準 1 億元以下。");
  }
  reasons.push("快速模式的私有財務欄位屬 scenario prior，未以該公司的真實帳務資料校準，因此只能做第一輪情境篩檢。");
  if (businessItems.length === 0) reasons.push("官方營業項目未取得，產業分類只能採較保守推測。");
  if (industryConfidence < 0.6) reasons.push("產業辨識信心偏低，產業參數可能不適合直接套用。");
  return { status, can_run_quick_estimate: status !== "NOT_RECOMMENDED", requires_human_confirmation: true, reasons };
}

async function fetchJson(url: URL, signal: AbortSignal) {
  const response = await fetch(url, {
    signal,
    headers: { accept: "application/json", "user-agent": "SME-Liquidity-Radar-Competition-PoC/1.0" },
    next: { revalidate: 86400 },
  });
  if (!response.ok) throw new Error(`upstream ${response.status}`);
  return response.json() as Promise<unknown>;
}
async function optionalJson(endpoint: string, signal: AbortSignal) {
  try {
    const response = await fetch(endpoint, {
      signal,
      headers: { accept: "application/json", "user-agent": "SME-Liquidity-Radar-Competition-PoC/1.0" },
      next: { revalidate: 86400 },
    });
    return response.ok ? await response.json() : [];
  } catch {
    return [];
  }
}
async function optionalCsv(endpoint: string, signal: AbortSignal) {
  try {
    const response = await fetch(endpoint, {
      signal,
      headers: { accept: "text/csv,*/*;q=0.8", "user-agent": "SME-Liquidity-Radar-Competition-PoC/1.0" },
      next: { revalidate: 86400 },
    });
    if (!response.ok) return [];
    return parseCsv(await response.text());
  } catch {
    return [];
  }
}

export async function GET(request: NextRequest) {
  const businessNo = request.nextUrl.searchParams.get("business_no") ?? "";
  if (!/^[0-9]{8}$/.test(businessNo)) {
    return NextResponse.json({ error: "invalid business_no" }, { status: 422 });
  }

  const basicUrl = new URL(BASIC_ENDPOINT);
  basicUrl.searchParams.set("$format", "json");
  basicUrl.searchParams.set("$filter", `Business_Accounting_NO eq ${businessNo}`);
  basicUrl.searchParams.set("$skip", "0");
  basicUrl.searchParams.set("$top", "50");
  const businessUrl = new URL(BUSINESS_ENDPOINT);
  businessUrl.searchParams.set("$format", "json");
  businessUrl.searchParams.set("$filter", `Business_Accounting_NO eq ${businessNo}`);
  businessUrl.searchParams.set("$skip", "0");
  businessUrl.searchParams.set("$top", "50");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12_000);
  try {
    const [basicPayload, businessPayload, listedPayload, publicPayload, otcPayload] = await Promise.all([
      fetchJson(basicUrl, controller.signal),
      fetchJson(businessUrl, controller.signal).catch(() => []),
      optionalJson(TWSE_LISTED_COMPANY_ENDPOINT, controller.signal),
      optionalJson(TWSE_PUBLIC_COMPANY_ENDPOINT, controller.signal),
      optionalJson(TPEX_OTC_COMPANY_ENDPOINT, controller.signal),
    ]);
    const basic = firstObject(basicPayload);
    if (!basic) return NextResponse.json({ error: "company not found" }, { status: 404 });

    const name = stringValue(basic.Company_Name);
    const paidCapital = numberOrNull(basic.Paid_In_Capital_Amount);
    const stockCapital = numberOrNull(basic.Capital_Stock_Amount);
    const businessItems = collectBusinessItems(businessPayload);

    let publicCompany = [listedPayload, publicPayload, otcPayload]
      .map((payload) => findPublicCompany(payload, businessNo, name, "OFFICIAL_MARKET_OPENAPI"))
      .find(Boolean) ?? null;

    let marketFallbackUsed = false;
    if (!publicCompany) {
      const [listedCsv, publicCsv, otcCsv] = await Promise.all([
        optionalCsv(MOPS_LISTED_CSV, controller.signal),
        optionalCsv(MOPS_PUBLIC_CSV, controller.signal),
        optionalCsv(MOPS_OTC_CSV, controller.signal),
      ]);
      publicCompany = [listedCsv, publicCsv, otcCsv]
        .map((payload) => findPublicCompany(payload, businessNo, name, "OFFICIAL_MOPS_CSV"))
        .find(Boolean) ?? null;
      marketFallbackUsed = true;
    }

    const industry = inferIndustry(name, publicCompany?.industry ? [publicCompany.industry, ...businessItems] : businessItems);
    const estimate = buildEstimate(paidCapital, stockCapital, industry.label, businessItems);
    const eligibility = assessQuickEstimateEligibility(paidCapital, stockCapital, industry.confidence, businessItems, publicCompany);

    return NextResponse.json({
      official: {
        business_no: businessNo,
        company_name: name,
        status: stringValue(basic.Company_Status_Desc),
        capital_stock_amount: stockCapital,
        paid_in_capital_amount: paidCapital,
        location: stringValue(basic.Company_Location),
        setup_date: stringValue(basic.Company_Setup_Date),
        register_organization: stringValue(basic.Register_Organization_Desc),
        business_items: businessItems,
        source: "MOEA_GCIS",
      },
      inferred: { industry },
      market: {
        public_company: publicCompany,
        recommended_data_route: publicCompany ? "PUBLIC_FINANCIAL_STATEMENTS" : "SME_ESTIMATE_OR_PRIVATE_DATA",
        checked_sources: ["TWSE_LISTED_COMPANY", "TWSE_PUBLIC_COMPANY", "TPEX_OTC_COMPANY", "MOPS_LISTED_CSV", "MOPS_PUBLIC_CSV", "MOPS_OTC_CSV"],
        fallback_csv_used: marketFallbackUsed,
      },
      estimate,
      quick_estimate_eligibility: eligibility,
      provenance: {
        retrieved_at: new Date().toISOString(),
        public_sources: [
          { id: "MOEA_GCIS", role: "company_registration_and_business_items" },
          { id: "TWSE_LISTED_COMPANY", role: "listed_company_detection" },
          { id: "TWSE_PUBLIC_COMPANY", role: "public_company_detection" },
          { id: "TPEX_OTC_COMPANY", role: "otc_company_detection" },
          { id: "MOPS_LISTED_CSV", role: "listed_company_detection_fallback" },
          { id: "MOPS_PUBLIC_CSV", role: "public_company_detection_fallback" },
          { id: "MOPS_OTC_CSV", role: "otc_company_detection_fallback" },
        ],
        estimate_model: estimate.basis,
        estimate_calibration_status: estimate.calibration_status,
        industry_confidence: industry.confidence,
        sme_capital_criterion_twd: SME_PAID_CAPITAL_CRITERION,
        sme_employee_alternative_criterion: "fewer_than_200_regular_employees",
        sme_rule_source: "MOEA_STANDARDS_FOR_IDENTIFYING_SMES_2024-11-27",
        public_data_cache_seconds: 86400,
      },
    }, {
      headers: {
        "cache-control": "public, s-maxage=86400, stale-while-revalidate=604800",
        "x-content-type-options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ error: "official company profile unavailable" }, {
      status: 503,
      headers: { "cache-control": "no-store", "x-content-type-options": "nosniff" },
    });
  } finally {
    clearTimeout(timer);
  }
}
