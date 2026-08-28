import { createHash, randomBytes } from "node:crypto";
import { generateText, Output } from "ai";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MODEL_ID = "google/gemini-3.7-flash";
const MAX_BODY_BYTES = 3_072;
const RATE_WINDOW_MS = 60_000;
const RATE_LIMIT = 5;
const rateSalt = randomBytes(16).toString("hex");
const rateBuckets = new Map<string, { count: number; resetAt: number }>();

const RiskStatusSchema = z.enum([
  "ROBUST",
  "WATCH",
  "NEAR_THRESHOLD",
  "STRESS_SENSITIVE",
  "HIGH_RISK",
]);
const StressSchema = z.enum([
  "major_customer_delay_30d",
  "revenue_down_15pct",
  "twd_strengthens_5pct",
  "combined",
]);
const DriverSchema = z.enum([
  "應收帳款延遲／違約暴露",
  "已知應付款",
  "薪資固定負擔",
  "日常營運支出",
  "外幣應收曝險",
]);
const AdjustmentCodeSchema = z.enum([
  "accelerate_receivable",
  "reschedule_payable",
  "reduce_fixed_cost",
  "reduce_fx_exposure",
]);
const EvidenceIdSchema = z.enum([
  "BASE_RISK",
  "UPPER_BOUND",
  "BUFFER",
  "STRESS",
  "DRIVER",
  "ADJUSTMENT",
]);
const QuestionIdSchema = z.enum([
  "CONFIRM_CASH_FLOWS",
  "CONFIRM_SAFETY_FLOOR",
  "REVIEW_RECEIVABLE",
  "REVIEW_PAYABLE",
  "REVIEW_FIXED_COST",
  "REVIEW_FX",
]);
const PrioritySchema = z.enum([
  "MONITOR",
  "CONTACT_WITHIN_7_DAYS",
  "CONTACT_WITHIN_48_HOURS",
]);

const RequestSchema = z.object({
  consent: z.literal(true),
  evidence: z.object({
    data_mode: z.enum(["synthetic_demo", "user_supplied_or_estimated"]),
    risk_status: RiskStatusSchema,
    base_probability: z.number().finite().min(0).max(1),
    base_ci95_upper: z.number().finite().min(0).max(1),
    buffer_ratio: z.number().finite().min(-1_000).max(1_000).nullable(),
    most_sensitive_stress: StressSchema,
    most_sensitive_probability: z.number().finite().min(0).max(1),
    top_driver: DriverSchema,
    best_adjustment: z.object({
      code: AdjustmentCodeSchema,
      improvement_percentage_points: z.number().finite().min(0).max(100),
    }).nullable(),
    engine_fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
  }).strict(),
}).strict();

const SelectionSchema = z.object({
  priority: PrioritySchema,
  evidence_ids: z.array(EvidenceIdSchema).min(3).max(4),
  question_ids: z.array(QuestionIdSchema).min(3).max(4),
}).strict();

type Evidence = z.infer<typeof RequestSchema>["evidence"];
type Selection = z.infer<typeof SelectionSchema>;
type EvidenceId = z.infer<typeof EvidenceIdSchema>;
type QuestionId = z.infer<typeof QuestionIdSchema>;

const stressLabels: Record<z.infer<typeof StressSchema>, string> = {
  major_customer_delay_30d: "最大客戶延遲 30 天",
  revenue_down_15pct: "日常收入下降 15%",
  twd_strengthens_5pct: "新台幣升值 5%",
  combined: "綜合壓力",
};

const adjustmentLabels: Record<z.infer<typeof AdjustmentCodeSchema>, string> = {
  accelerate_receivable: "優先催收最大筆應收帳款",
  reschedule_payable: "協商最大筆應付款延後",
  reduce_fixed_cost: "短期降低固定營運支出 10%",
  reduce_fx_exposure: "降低未避險外幣曝險",
};

const questionLabels: Record<QuestionId, string> = {
  CONFIRM_CASH_FLOWS: "請確認未來 90 天已知入帳與付款時點，哪些仍是估算值？",
  CONFIRM_SAFETY_FLOOR: "目前設定的安全現金水位是否足以涵蓋必要營運與還款需求？",
  REVIEW_RECEIVABLE: "最大筆應收的付款人、到期日與近期延遲紀錄為何？",
  REVIEW_PAYABLE: "未來 90 天最大筆應付款是否有調整付款時點的空間？",
  REVIEW_FIXED_COST: "薪資與固定營運支出是否存在短期不可延後的集中付款？",
  REVIEW_FX: "外幣應收的幣別、預計收款日與目前避險比例為何？",
};

const priorityLabels: Record<z.infer<typeof PrioritySchema>, { label: string; headline: string }> = {
  MONITOR: {
    label: "持續監測",
    headline: "目前先維持監測，重點是確認資料與壓力敏感度。",
  },
  CONTACT_WITHIN_7_DAYS: {
    label: "7 天內聯絡",
    headline: "建議 RM 一週內確認現金流時點與主要曝險。",
  },
  CONTACT_WITHIN_48_HOURS: {
    label: "48 小時內聯絡",
    headline: "建議 RM 優先聯絡，先核對真實資金缺口與近期付款安排。",
  },
};

function sameOrigin(request: NextRequest) {
  const secFetchSite = request.headers.get("sec-fetch-site");
  return !secFetchSite || ["same-origin", "same-site", "none"].includes(secFetchSite);
}

function rateKey(request: NextRequest) {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = forwarded || request.headers.get("x-real-ip") || "unknown";
  return createHash("sha256").update(`${rateSalt}:${address}`).digest("hex");
}

function isRateLimited(request: NextRequest) {
  const now = Date.now();
  if (rateBuckets.size > 2_000) {
    for (const [key, bucket] of rateBuckets) {
      if (bucket.resetAt <= now) rateBuckets.delete(key);
    }
  }
  const key = rateKey(request);
  const current = rateBuckets.get(key);
  if (!current || current.resetAt <= now) {
    if (rateBuckets.size >= 2_000 && !current) return true;
    rateBuckets.set(key, { count: 1, resetAt: now + RATE_WINDOW_MS });
    return false;
  }
  current.count += 1;
  return current.count > RATE_LIMIT;
}

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function availableEvidence(evidence: Evidence): Record<EvidenceId, string | null> {
  return {
    BASE_RISK: `90 天基準情境缺口機率為 ${pct(evidence.base_probability)}。`,
    UPPER_BOUND: `90 天缺口機率的 Wilson 95% 信賴上界為 ${pct(evidence.base_ci95_upper)}。`,
    BUFFER: evidence.buffer_ratio === null
      ? null
      : `悲觀路徑的安全水位緩衝比為 ${(evidence.buffer_ratio * 100).toFixed(0)}%。`,
    STRESS: `${stressLabels[evidence.most_sensitive_stress]}是最敏感情境，缺口機率為 ${pct(evidence.most_sensitive_probability)}。`,
    DRIVER: `最大金額／延遲曝險分類為「${evidence.top_driver}」；此排序不是因果歸因。`,
    ADJUSTMENT: evidence.best_adjustment
      ? `反事實測試中「${adjustmentLabels[evidence.best_adjustment.code]}」的缺口機率估計改善 ${evidence.best_adjustment.improvement_percentage_points.toFixed(1)} 個百分點。`
      : null,
  };
}

function deterministicSelection(evidence: Evidence): Selection {
  const priority: Selection["priority"] =
    evidence.risk_status === "HIGH_RISK" || evidence.base_probability >= 0.5
      ? "CONTACT_WITHIN_48_HOURS"
      : evidence.risk_status === "WATCH" ||
          evidence.risk_status === "NEAR_THRESHOLD" ||
          evidence.risk_status === "STRESS_SENSITIVE"
        ? "CONTACT_WITHIN_7_DAYS"
        : "MONITOR";
  const evidenceIds: EvidenceId[] = ["BASE_RISK", "UPPER_BOUND", "STRESS", "DRIVER"];
  if (evidence.best_adjustment) evidenceIds[3] = "ADJUSTMENT";

  const driverQuestion: Record<z.infer<typeof DriverSchema>, QuestionId> = {
    "應收帳款延遲／違約暴露": "REVIEW_RECEIVABLE",
    已知應付款: "REVIEW_PAYABLE",
    薪資固定負擔: "REVIEW_FIXED_COST",
    日常營運支出: "REVIEW_FIXED_COST",
    外幣應收曝險: "REVIEW_FX",
  };
  return {
    priority,
    evidence_ids: evidenceIds,
    question_ids: [
      "CONFIRM_CASH_FLOWS",
      driverQuestion[evidence.top_driver],
      "CONFIRM_SAFETY_FLOOR",
    ],
  };
}

function unique<T>(values: T[]) {
  return [...new Set(values)];
}

function logGatewayFailure(error: unknown) {
  const value = error && typeof error === "object"
    ? error as {
        name?: unknown;
        message?: unknown;
        statusCode?: unknown;
        cause?: { name?: unknown; message?: unknown; statusCode?: unknown };
      }
    : null;
  console.error("[sme-ai-brief] gateway failure", {
    name: typeof value?.name === "string" ? value.name : typeof error,
    message: typeof value?.message === "string" ? value.message.slice(0, 500) : "unavailable",
    statusCode: typeof value?.statusCode === "number" ? value.statusCode : null,
    causeName: typeof value?.cause?.name === "string" ? value.cause.name : null,
    causeMessage: typeof value?.cause?.message === "string"
      ? value.cause.message.slice(0, 500)
      : null,
    causeStatusCode: typeof value?.cause?.statusCode === "number"
      ? value.cause.statusCode
      : null,
  });
}

function renderBrief(
  selection: Selection,
  evidence: Evidence,
  mode: "AI_GATEWAY" | "DETERMINISTIC_FALLBACK",
) {
  const fallback = deterministicSelection(evidence);
  const evidenceCatalog = availableEvidence(evidence);
  const selectedEvidence = unique<EvidenceId>([
    "BASE_RISK",
    "STRESS",
    ...selection.evidence_ids,
  ])
    .map((id) => ({ id, text: evidenceCatalog[id] }))
    .filter((item): item is { id: EvidenceId; text: string } => Boolean(item.text));
  for (const id of fallback.evidence_ids) {
    const text = evidenceCatalog[id];
    if (text && !selectedEvidence.some((item) => item.id === id)) {
      selectedEvidence.push({ id, text });
    }
    if (selectedEvidence.length >= 3) break;
  }

  const selectedQuestions = unique<QuestionId>([
    "CONFIRM_CASH_FLOWS",
    ...selection.question_ids,
  ])
    .slice(0, 4)
    .map((id) => ({ id, text: questionLabels[id] }));
  for (const id of fallback.question_ids) {
    if (!selectedQuestions.some((item) => item.id === id)) {
      selectedQuestions.push({ id, text: questionLabels[id] });
    }
    if (selectedQuestions.length >= 3) break;
  }

  const priorityRank: Record<Selection["priority"], number> = {
    MONITOR: 0,
    CONTACT_WITHIN_7_DAYS: 1,
    CONTACT_WITHIN_48_HOURS: 2,
  };
  const priority = priorityRank[selection.priority] >= priorityRank[fallback.priority]
    ? selection.priority
    : fallback.priority;

  return {
    mode,
    model: mode === "AI_GATEWAY" ? MODEL_ID : null,
    priority,
    priority_label: priorityLabels[priority].label,
    headline: priorityLabels[priority].headline,
    evidence: selectedEvidence.slice(0, 4),
    rm_questions: selectedQuestions.slice(0, 4),
    governance: {
      numbers_generated_by_ai: false,
      raw_financial_fields_sent: false,
      company_identity_sent: false,
      prompt_training_disallowed: mode === "AI_GATEWAY",
      human_review_required: true,
      engine_fingerprint: evidence.engine_fingerprint.slice(0, 12),
    },
  };
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) {
    return NextResponse.json(
      { error: "cross-site request rejected" },
      { status: 403, headers: { "cache-control": "no-store" } },
    );
  }
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return NextResponse.json(
      { error: "application/json required" },
      { status: 415, headers: { "cache-control": "no-store" } },
    );
  }
  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (declaredLength > MAX_BODY_BYTES || isRateLimited(request)) {
    return NextResponse.json(
      { error: declaredLength > MAX_BODY_BYTES ? "request too large" : "rate limit exceeded" },
      {
        status: declaredLength > MAX_BODY_BYTES ? 413 : 429,
        headers: { "cache-control": "no-store", "retry-after": "60" },
      },
    );
  }

  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) {
    return NextResponse.json(
      { error: "request too large" },
      { status: 413, headers: { "cache-control": "no-store" } },
    );
  }

  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch (error) {
    logGatewayFailure(error);
    return NextResponse.json(
      { error: "invalid JSON" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  const parsed = RequestSchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid de-identified evidence payload" },
      { status: 422, headers: { "cache-control": "no-store" } },
    );
  }

  const { evidence } = parsed.data;
  const fallback = deterministicSelection(evidence);
  try {
    const { output } = await generateText({
      model: MODEL_ID,
      output: Output.object({ schema: SelectionSchema }),
      instructions:
        "你是銀行 RM 的風險證據路由器。只能從 schema 的列舉值選擇優先級、三到四個證據 ID 與三到四個問題 ID。不得新增數字、公司事實、授信結論或金融商品推薦。基準引擎是唯一數值權威，所有結果均需人工覆核。",
      prompt: JSON.stringify(evidence),
      temperature: 0,
      maxOutputTokens: 250,
      maxRetries: 1,
      timeout: 8_000,
      providerOptions: {
        gateway: {
          disallowPromptTraining: true,
          tags: ["feature:sme-rm-brief", "env:competition"],
          user: "public-competition-demo",
        },
      },
    });
    return NextResponse.json(renderBrief(output, evidence, "AI_GATEWAY"), {
      headers: { "cache-control": "no-store", "x-content-type-options": "nosniff" },
    });
  } catch {
    return NextResponse.json(
      {
        ...renderBrief(fallback, evidence, "DETERMINISTIC_FALLBACK"),
        fallback_reason: "AI_UNAVAILABLE",
      },
      { headers: { "cache-control": "no-store", "x-content-type-options": "nosniff" } },
    );
  }
}
