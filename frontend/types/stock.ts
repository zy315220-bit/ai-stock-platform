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
  };
  chart: {
    candles: Candle[];
    ma20: LinePoint[];
    ma60: LinePoint[];
  };
  watchlist: WatchItem[];
  demo: boolean;
};
