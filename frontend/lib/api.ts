import type {
  AnalysisResponse,
  BacktestResponse,
  CompetitionPboResponse,
  CompetitionResponse,
  PositionStatus,
  ScannerResponse,
} from "@/types/stock";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
type RequestOptions = { signal?: AbortSignal };
export type HealthResponse = { demo_mode: boolean; status: string };
type FetchJsonOptions = RequestOptions & { fallbackError: string; networkError: string; timeoutError: string; timeoutMs: number };

class RequestError extends Error {
  retryable: boolean;
  constructor(message: string, retryable: boolean) { super(message); this.name = "RequestError"; this.retryable = retryable; }
}
export function isRetryableRequestError(reason: unknown): boolean { return reason instanceof RequestError && reason.retryable; }
function abortError(): Error { const error = new Error("Request aborted"); error.name = "AbortError"; return error; }
function errorDetail(payload: unknown): string | null { if (typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string") return payload.detail; return null; }

async function fetchJson<T>(url: string, options: FetchJsonOptions): Promise<T> {
  const controller = new AbortController(); let timedOut = false;
  const cancel = () => controller.abort();
  const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, options.timeoutMs);
  if (options.signal?.aborted) controller.abort(); else options.signal?.addEventListener("abort", cancel, { once: true });
  let response: Response;
  try { response = await fetch(url, { cache: "no-store", signal: controller.signal }); }
  catch { if (options.signal?.aborted) throw abortError(); if (timedOut) throw new RequestError(options.timeoutError, true); throw new RequestError(options.networkError, true); }
  finally { window.clearTimeout(timeout); options.signal?.removeEventListener("abort", cancel); }
  if (!response.ok) { const payload: unknown = await response.json().catch(() => null); throw new RequestError(errorDetail(payload) ?? `${options.fallbackError}（${response.status}）`, response.status === 429 || response.status >= 500); }
  try { return (await response.json()) as T; } catch { throw new RequestError("分析服務回傳格式錯誤，請稍後再試。", true); }
}

export async function fetchHealth(options: RequestOptions = {}): Promise<HealthResponse> { return fetchJson<HealthResponse>(`${API_BASE_URL}/api/health`, { ...options, timeoutMs: 8_000, timeoutError: "分析服務健康檢查逾時。", networkError: "目前無法檢查分析服務狀態。", fallbackError: "分析服務狀態異常" }); }
export async function fetchAnalysis(stockCode: string, positionStatus: PositionStatus = "not_holding", options: RequestOptions = {}): Promise<AnalysisResponse> { const query = new URLSearchParams({ position_status: positionStatus }); return fetchJson<AnalysisResponse>(`${API_BASE_URL}/api/stocks/${encodeURIComponent(stockCode)}/analysis?${query.toString()}`, { ...options, timeoutMs: 65_000, timeoutError: "分析時間過長，請稍後重試。", networkError: "目前無法連接分析服務，請稍後再試。", fallbackError: "分析服務錯誤" }); }
export async function fetchBacktest(stockCode: string, initialCapital: number, options: RequestOptions = {}): Promise<BacktestResponse> { const query = new URLSearchParams({ initial_capital: String(initialCapital) }); return fetchJson<BacktestResponse>(`${API_BASE_URL}/api/stocks/${encodeURIComponent(stockCode)}/backtest?${query.toString()}`, { ...options, timeoutMs: 115_000, timeoutError: "回測時間過長，請縮短期間或稍後重試。", networkError: "目前無法連接回測服務，請稍後再試。", fallbackError: "回測服務錯誤" }); }
export async function fetchDailyScanner(options: RequestOptions = {}): Promise<ScannerResponse> { return fetchJson<ScannerResponse>(`${API_BASE_URL}/api/stocks/scanner/daily`, { ...options, timeoutMs: 20_000, timeoutError: "每日選股池更新逾時，請稍後再試。", networkError: "目前無法連接每日選股服務。", fallbackError: "每日選股服務錯誤" }); }
export async function fetchCompetition(initialCapital = 100_000, options: RequestOptions = {}): Promise<CompetitionResponse> { const query = new URLSearchParams({ initial_capital: String(initialCapital) }); return fetchJson<CompetitionResponse>(`${API_BASE_URL}/api/competition/run?${query.toString()}`, { ...options, timeoutMs: 180_000, timeoutError: "長期機器人競賽執行時間過長，請稍後再試。", networkError: "目前無法連接機器人競賽服務。", fallbackError: "機器人競賽執行失敗" }); }

export async function fetchCompetitionPbo(
  initialCapital = 100_000,
  options: RequestOptions = {},
): Promise<CompetitionPboResponse> {
  const query = new URLSearchParams({
    initial_capital: String(initialCapital),
    slice_months: "1",
    max_slices: "60",
  });
  return fetchJson<CompetitionPboResponse>(`${API_BASE_URL}/api/competition/pbo?${query.toString()}`, {
    ...options,
    timeoutMs: 300_000,
    timeoutError: "5 年跨時間穩定性檢驗時間過長，請稍後再試。",
    networkError: "目前無法連接 CSCV/PBO 分析服務。",
    fallbackError: "跨時間穩定性檢驗失敗",
  });
}