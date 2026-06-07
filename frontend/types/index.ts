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
  ema20?:       number | null;
  ema50?:       number | null;
  macd?:        number | null;
  macd_signal?: number | null;
  macd_hist?:   number | null;
  rsi?:         number | null;
  vwap?:        number | null;
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
  tools_used?: string[];
}

export interface MonteCarloPriceRangeDay {
  day:  number;
  p10:  number;
  p25:  number;
  p50:  number;
  p75:  number;
  p90:  number;
}

export interface MonteCarloResult {
  p10:               number;
  p50:               number;
  p90:               number;
  prob_gain:         number;
  var_95:            number;
  paths_sample:      number[][];
  price_range_by_day: MonteCarloPriceRangeDay[];
  n_sims:            number;
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
    market_cap:     string;
    pe_ratio:       string;
    yield:          string;
    prev_close:     string;
    range_52w:      string;
    sector?:        string;
    industry?:      string;
    currency?:      string;
    // Extended quant fundamentals
    beta?:          string;
    forward_pe?:    string;
    peg_ratio?:     string;
    price_to_book?: string;
    ev_to_ebitda?:  string;
    free_cash_flow?: string;
    revenue_growth?: string;
    total_debt?:    string;
  };
  news:      { title: string; link: string; source: string; thumbnail: string; date: string; source_label?: string }[];
  trending:  { symbol: string; name?: string; price: string | number; change: string; category?: string }[];
  indicators?: { rsi_series?: number[]; support?: number[]; resistance?: number[] };
  juryAnalysts?: AnalystJuror[];
  modelWeights?: { prophet: number; sarima: number; rf: number };
  sentiment?:    { compound: number; label: string; headline_count: number };
  stocktwits?:   { bullish: number; bearish: number; sentiment: number };
  monteCarlo?:      MonteCarloResult | null;
  earningsDates?:   string[];
  moveExplanation?: string | null;
  lastUpdated: string;
}

export type ChartEntry = Record<string, string | number | undefined>;

export type IndicatorKey = 'bb' | 'sma' | 'ema' | 'macd' | 'rsi' | 'volume';

export interface TradeSetupResponse {
  entry_low:               number;
  entry_high:              number;
  stop_loss:               number;
  target_1:                number;
  target_2:                number;
  target_3:                number;
  risk_reward:             string;
  setup_type:              string;
  rationale:               string;
  risk_per_share:          number;
  risk_pct:                number;
  suggested_position_pct:  number;
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

export interface OptionContract {
  strike:        number;
  last:          number;
  bid:           number;
  ask:           number;
  change:        number;
  change_pct:    number;
  volume:        number;
  open_interest: number;
  implied_vol:   number;
  delta:         number;
  theta:         number;
  in_the_money:  boolean;
  type:          'call' | 'put';
}

export interface OptionsStats {
  put_call_ratio: number;
  iv_avg_calls:   number;
  iv_avg_puts:    number;
  iv_skew:        number;
}

export interface OptionsChainResult {
  symbol:        string;
  expiry:        string;
  expirations:   string[];
  current_price: number;
  calls:         OptionContract[];
  puts:          OptionContract[];
  stats?:        OptionsStats;
}

export interface EarningsEntry {
  symbol:     string;
  name:       string;
  market_cap: number;
  date:       string;
}

export interface EarningsCalendarResult {
  calendar:     Record<string, EarningsEntry[]>;
  generated_at: string;
}

export interface IpoEntry {
  symbol:     string;
  company:    string;
  exchange:   string;
  date:       string;
  price_low:  number | null;
  price_high: number | null;
  shares:     number | null;
  market_cap: number | null;
  actions:    string;
  status:     'upcoming' | 'recent';
}

export interface IpoCalendarResult {
  upcoming:     IpoEntry[];
  recent:       IpoEntry[];
  source:       'fmp' | 'edgar';
  generated_at: string;
}

export interface IntervalStats {
  change_pct:  number;
  period_high: number;
  period_low:  number;
  sma20:       number | null;
  ann_vol:     number;
}

export interface IntervalHistoryData {
  symbol:     string;
  period:     string;
  interval:   string;
  history:    HistoryPoint[];
  rsi_series: Array<number | null>;
  stats:      IntervalStats;
}

export interface DCFScenario {
  wacc:            number;
  growth_rate:     number;
  intrinsic_value: number;
  upside_pct:      number;
}

export interface DCFResult {
  symbol:             string;
  current_price:      number;
  bear:               DCFScenario;
  base:               DCFScenario;
  bull:               DCFScenario;
  shares_outstanding: number;
  fcf_billions:       number;
  wacc_base:          number;
  growth_rate_base:   number;
  method:             string;
  fundamentals_complete?: boolean;
}
