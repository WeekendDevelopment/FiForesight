export interface ForecastDay {
  date:           string;
  predicted:      number;
  high:           number;
  low:            number;
  confidence_pct: number;
}

export interface ModelStats {
  ann_volatility_pct: number;
  trend_slope:        number;
  sma_20:             number;
  price_vs_sma20_pct: number;
}

export interface HistoryPoint {
  date:         string;
  price:        number;
  open?:        number;
  high?:        number;
  low?:         number;
  volume?:      number;
  bb_upper?:    number | null;
  bb_middle?:   number | null;
  bb_lower?:    number | null;
  sma50?:       number | null;
  sma200?:      number | null;
  macd?:        number | null;
  macd_signal?: number | null;
  macd_hist?:   number | null;
}

export interface AnalystJuror {
  id:          string;
  avatar:      string;
  title:       string;
  model_label: string;
  color:       string;
  rating:      string;
  note:        string;
  confidence:  number;
  model:       string;
}

export interface PredictionData {
  symbol:       string;
  currentPrice: string;
  rsi:          string;
  prediction: {
    highRange: string;
    lowRange:  string;
    trend:     'Bullish' | 'Bearish';
  };
  analystNote:  string;
  confidence:   string;
  history:      HistoryPoint[];
  forecastDays: ForecastDay[];
  modelStats:   ModelStats;
  metrics: {
    market_cap: string;
    pe_ratio:   string;
    yield:      string;
    prev_close: string;
    range_52w:  string;
    sector?:    string;
    currency?:  string;
  };
  news:      { title: string; link: string; source: string; thumbnail: string; date: string }[];
  trending:  { symbol: string; name?: string; price: string | number; change: string; category?: string }[];
  indicators?: { rsi_series?: number[]; support?: number[]; resistance?: number[] };
  juryAnalysts?: AnalystJuror[];
  modelWeights?: { prophet: number; sarima: number; rf: number };
  sentiment?:    { compound: number; label: string; headline_count: number };
  lastUpdated: string;
}

export type ChartEntry = Record<string, string | number | undefined>;

export type IndicatorKey = 'bb' | 'sma' | 'macd' | 'rsi' | 'volume';

export interface TradeSetupResponse {
  entry_low:    number;
  entry_high:   number;
  stop_loss:    number;
  target_1:     number;
  target_2:     number;
  target_3:     number;
  risk_reward:  string;
  setup_type:   string;
  rationale:    string;
}

export interface ChatMessage {
  role:    'user' | 'assistant';
  content: string;
}

export interface ChartStats {
  open:      number;
  change:    number;
  changePct: number;
  high:      number;
  low:       number;
  isUp:      boolean;
  color:     string;
}

export interface IndicatorSignal {
  text:  string;
  color: string;
}

export type IndicatorSignals = Record<string, IndicatorSignal | null>;
