import type { AnalysisResponse } from "@/types/stock";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchAnalysis(
  stockCode: string,
): Promise<AnalysisResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/stocks/${encodeURIComponent(stockCode)}/analysis`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `API 錯誤：${response.status}`);
  }

  return response.json();
}
