import type { AnalysisResponse } from "@/types/stock";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function parseApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `API 錯誤：${response.status}`);
  }
  return response.json();
}

export async function fetchAnalysis(stockCode: string): Promise<AnalysisResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/stocks/${encodeURIComponent(stockCode)}/analysis`,
    { cache: "no-store" },
  );
  return parseApiResponse<AnalysisResponse>(response);
}

export type CompetitionRobotInput = {
  robot_id: string;
  robot_version: string;
  rule_fingerprint: string;
  initial_capital: number;
  period_start: string;
  period_end: string;
  cost_model_id: string;
  risk_model_id: string;
  market_universe_id: string;
  trade_count: number;
  winning_trade_count: number;
  total_return_percent: number;
  max_drawdown_percent: number;
};

export type RankedRobot = CompetitionRobotInput & {
  rank: number;
  raw_win_rate_percent: number;
  wilson_lower_percent: number;
  wilson_upper_percent: number;
};

export type CompetitionRankingResponse = {
  objective: string;
  primary_metric: string;
  robots: RankedRobot[];
};

export async function rankCompetitionRobots(
  robots: CompetitionRobotInput[],
  confidence = 0.95,
): Promise<CompetitionRankingResponse> {
  const response = await fetch(`${API_BASE_URL}/api/competition/rank`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({ robots, confidence }),
  });
  return parseApiResponse<CompetitionRankingResponse>(response);
}
