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

export type HistoryCoverage = {
  start: string | null;
  end: string | null;
  available_days: number;
  available_years: number;
  status: "preferred" | "acceptable" | "insufficient_for_long_horizon_claim" | "incomplete_months";
  long_horizon_qualified: boolean;
  complete_month_coverage: boolean;
  missing_months: string[];
  row_count: number;
};

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
    history_coverage?: HistoryCoverage;
    requested_history_months?: number;
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

export type MarketIndexSnapshot = {
  name: string;
  date: string;
  close: number | null;
  change: number | null;
  change_percent: number | null;
  source: string;
};

export type SectorSnapshot = {
  name: string;
  index_name: string;
  date: string;
  close: number | null;
  change_percent: number;
  direction: "上漲" | "下跌" | "持平";
  rank: number;
};

export type MarketOverviewResponse = {
  updated_at: string;
  source_dates: string[];
  dates_aligned: boolean;
  indices: {
    twse: MarketIndexSnapshot | null;
    tpex: MarketIndexSnapshot | null;
  };
  market: {
    turnover_billion: number;
    advancing: number;
    declining: number;
    unchanged: number;
    breadth_ratio: number | null;
    regime: "偏多" | "偏空" | "中性";
    regime_score: number;
    regime_reason: string;
  };
  sectors: SectorSnapshot[];
  method: string;
  sources: Array<{
    name: string;
    url: string;
  }>;
};

export type BacktestResponse = {
  stock_code: string;
  data_source: string;
  actual_start_date: string;
  actual_end_date: string;
  history_coverage: HistoryCoverage;
  requested_history_months: number;
  initial_capital: number;
  final_capital: number;
  total_profit: number;
  total_return_percent: number;
  trade_count: number;
  win_rate_percent: number;
  max_drawdown_percent: number;
  alpha_percent: number;
  total_dividends: number;
  corporate_actions: {
    price_basis: string | null;
    split_adjustments: Array<{
      effective_date: string;
      ratio: number;
      source: string;
    }>;
    dividend_source: string | null;
    dividend_event_count: number;
  };
  buy_and_hold: {
    return_percent: number;
    total_dividends: number;
    dividend_per_share: number;
    return_basis: string;
  };
};

export type CompetitionTrade = {
  robot_id: string;
  stock_code: string;
  segment: "backtest" | "forward";
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  shares: number;
  profit: number;
  return_percent: number;
  entry_reason: string;
  exit_reason: string;
  entry_commission: number;
  exit_commission: number;
  transaction_tax: number;
  dividends: number;
  stop_price: number;
  target_price: number;
};

export type CompetitionSegment = {
  initial_capital: number;
  final_capital: number;
  total_return_percent: number;
  trade_count: number;
  winning_trade_count: number;
  win_rate_percent: number;
  max_drawdown_percent: number;
  total_commission: number;
  total_transaction_tax: number;
  total_dividends: number;
  trades: CompetitionTrade[];
  equity_curve: Array<{ date: string; equity: number }>;
};

export type CompetitionRobot = {
  robot_id: string;
  name: string;
  family: string;
  rule_fingerprint: string;
  rank: number;
  wilson_lower_percent: number;
  wilson_upper_percent: number;
  backtest: CompetitionSegment;
  forward: CompetitionSegment;
};

export type CompetitionResponse = {
  run_id: string;
  status: "completed";
  executed_at: string;
  requested_history_months: number;
  data_sources: Record<string, string>;
  history_coverage: Record<string, {
    start: string | null;
    end: string | null;
    available_days: number;
    available_years: number;
    status: string;
    long_horizon_qualified: boolean;
    complete_month_coverage: boolean;
    required_start_month?: string;
    requested_span_complete?: boolean;
    missing_months: string[];
    row_count: number;
  }>;
  periods: {
    backtest: { start: string; end: string; purpose: string };
    forward: { start: string; end: string; purpose: string };
  };
  fairness: {
    initial_capital: number;
    capital_per_symbol: number;
    market_universe: string[];
    commission_rate: number;
    transaction_tax_rate: number;
    execution: string;
    stop_model: string;
    target_model: string;
    same_bar_stop_target_policy: string;
  };
  ranking: {
    primary_metric: string;
    objective: string;
    method: string;
    return_role: string;
    minimum_forward_trades_for_champion: number;
    leader_status: "qualified" | "provisional";
  };
  leader: {
    robot_id: string;
    name: string;
    rank: number;
    qualified: boolean;
    reason: string;
  };
  robots: CompetitionRobot[];
  disclosures: string[];
};
