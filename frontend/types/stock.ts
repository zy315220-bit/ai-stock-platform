export type Candle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type LinePoint = {
  time: string;
  value: number;
};

export type WatchItem = {
  code: string;
  name: string;
  price: number;
  change_percent: number;
  score: number;
};

export type PositionStatus = "not_holding" | "holding";

export type NewsArticle = {
  title: string;
  url: string;
  source: string;
  published_at: string;
};

export type AnalysisPerspectives = {
  technical: {
    available: boolean;
    score: number;
    label: string;
    summary: string;
  };
  fundamental: {
    available: boolean;
    score: number | null;
    label: string;
    summary: string;
    pe_ratio: number | null;
    pb_ratio: number | null;
    dividend_yield: number | null;
    as_of: string | null;
    source: string;
  };
  news: {
    available: boolean;
    score: number | null;
    label: string;
    summary: string;
    positive_hits: number;
    negative_hits: number;
    articles: NewsArticle[];
    source: string;
  };
  composite: {
    score: number;
    available_axes: number;
    method: string;
  };
};

export type AnalysisResponse = {
  stock: {
    code: string;
    name: string;
    market: string;
    price: number;
    change: number;
    change_percent: number;
    open: number | null;
    high: number | null;
    low: number | null;
    volume: number;
    updated_at: string;
    price_source: string;
  };
  analysis: {
    technical_score: number;
    /** @deprecated Use technical_score. Retained for API compatibility. */
    total_score: number;
    score_level: string;
    direction: string;
    stage: string;
    market_regime: string;
    confidence: string;
    trade_eligible: boolean;
    subscores: {
      trend: number;
      location: number;
      trigger: number;
      risk: number;
      market: number;
    };
    plan: {
      trigger_price: number | null;
      stop_price: number | null;
      risk_percent: number | null;
      reward_risk_ratio: number | null;
    };
    reasons: string[];
    veto_reasons: string[];
    indicators: {
      ema20: number | null;
      ema60: number | null;
      rsi: number | null;
      macd: number | null;
      macd_signal: number | null;
      macd_histogram: number | null;
      k: number | null;
      d: number | null;
      atr: number | null;
      atr_percent: number | null;
      adx: number | null;
      volume_ratio: number | null;
    };
    recommendation: {
      position_status: PositionStatus;
      position_label: string;
      action: string;
      title: string;
      summary: string;
      tone: "positive" | "neutral" | "risk";
      disclaimer: string;
    };
    perspectives?: AnalysisPerspectives;
  };
  chart: {
    candles: Candle[];
    ma20: LinePoint[];
    ma60: LinePoint[];
  };
  watchlist: WatchItem[];
  meta: {
    daily_rows: number;
    hourly_rows: number;
    hourly_available: boolean;
    analysis_engine: string;
    daily_source?: string;
  };
  demo: boolean;
};

export type ScannerCandidate = {
  code: string;
  name: string;
  market: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  screening_score: number;
  reasons: string[];
  full_analysis_required: boolean;
};

export type ScannerResponse = {
  updated_at: string;
  market_scope: string;
  universe_size: number;
  candidate_count: number;
  method: string;
  candidates: ScannerCandidate[];
};

export type BacktestResponse = {
  stock_code: string;
  data_source: string;
  actual_start_date: string;
  actual_end_date: string;
  initial_capital: number;
  final_capital: number;
  total_profit: number;
  total_return_percent: number;
  trade_count: number;
  win_rate_percent: number;
  max_drawdown_percent: number;
  alpha_percent: number;
  buy_and_hold: {
    return_percent: number;
  };
};
