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

/** Supported market-regime labels (backend/UI contract, Feature 16). */
export type MarketRegime = 'trending_up' | 'ranging' | 'trending_down' | 'unknown';

/** 3-state HMM market regime for a ticker (Feature 16). */
export interface RegimeInfo {
  regime:     MarketRegime;
  confidence: number;   // 0..1
  state_means?:            Record<string, number>;
  bars_in_current_regime?: number;
}

/** Minority view surfaced on a 2-1 analyst-jury split (Feature 16). */
export interface JuryDissent {
  analyst:   string;
  verdict:   string;
  rationale: string;
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
  indicators?: {
    rsi_series?: number[];
    support?:    number[];
    resistance?: number[];
    // ── Advanced technical signals (Feature 14) ──
    atr_14?:      number | null;
    stoch_k?:     number | null;
    stoch_d?:     number | null;
    adx_14?:      number | null;
    plus_di?:     number | null;
    minus_di?:    number | null;
    obv_history?: number[] | null;
    divergences?: Divergences;
    rf_feature_importance?: FeatureImportance[];
    earnings_surprise?:     EarningsSurprise[];
  };
  juryAnalysts?: AnalystJuror[];
  modelWeights?: { prophet: number; sarima: number; rf: number };
  sentiment?:    { compound: number; label: string; headline_count: number };
  stocktwits?:   { bullish: number; bearish: number; sentiment: number };
  monteCarlo?:      MonteCarloResult | null;
  earningsDates?:   string[];
  moveExplanation?: string | null;
  reversalRisk?:      ReversalRisk | null;
  directionForecast?: DirectionForecast | null;
  // Alternative data (Feature 15)
  insiderTransactions?: InsiderTransaction[];
  shortInterest?:       ShortInterest | null;
  // Market regime intelligence (Feature 16)
  regime?:      RegimeInfo | null;
  juryDissent?: JuryDissent | null;
  lastUpdated: string;
}

// ── Alternative data (Feature 15) ────────────────────────────────────────────

/** One FRED series value + its 30-day change. */
export interface MacroSeries {
  value:     number;
  delta_30d: number;
}

/** FRED macro snapshot returned by GET /api/macro/snapshot. */
export interface MacroSnapshot {
  dgs10?:    MacroSeries;   // 10Y Treasury yield
  cpiaucsl?: MacroSeries;   // CPI (all urban consumers)
  unrate?:   MacroSeries;   // Unemployment rate
  fedfunds?: MacroSeries;   // Effective federal funds rate
  t10y2y?:   MacroSeries;   // 10Y-2Y spread (negative = inverted)
  inverted?: boolean;       // true when t10y2y < 0
  t10y2y_trend?: { date: string; value: number }[];  // 31-point trend
  fetched_at?: string;
}

/** One SEC EDGAR Form 4 insider filing. */
export interface InsiderTransaction {
  filer:    string;
  type:     string;          // "Purchase" | "Sale" | "Award" | "Filing" | …
  shares:   number | null;
  price:    number | null;
  date:     string;
  sec_link: string;
}

/** FINRA short-interest metrics for a symbol. */
export interface ShortInterest {
  short_volume:  number;
  total_volume:  number;
  short_ratio:   number | null;
  days_to_cover: number | null;
  report_date:   string;
}

export interface DirectionForecast {
  /** "up" | "down" — predicted next-day direction. */
  direction:      'up' | 'down';
  /** 50-100 — predicted-class probability × 100. */
  confidence_pct: number;
  /** confidence_pct − 50; how much above coin-flip baseline. */
  edge_pct:       number;
  /** Top model-level signals (feature importances) with current-bar values. */
  top_features:   string[];
  /** Number of historical bars the classifier was trained on. */
  trained_on:     number;
}

export interface ReversalRisk {
  /** 0-100 probability of a ≥2% drop within 5 trading days. */
  risk_pct:     number;
  /** "low" (<35%) | "medium" (35-64%) | "high" (≥65%) */
  signal:       'low' | 'medium' | 'high';
  /** Top model-level signals (feature importances), shown with current-bar values. */
  top_features: string[];
  /** Number of historical bars the classifier was trained on. */
  trained_on:   number;
}

export type ChartEntry = Record<string, string | number | undefined>;

// ── Advanced technical signals (Feature 14) ──────────────────────────────────

export interface Divergences {
  rsi_bullish:  boolean;
  rsi_bearish:  boolean;
  macd_bullish: boolean;
  macd_bearish: boolean;
}

export interface FeatureImportance {
  feature:    string;
  importance: number;   // 0–1, top-5 normalised to sum 1.0
}

export interface EarningsSurprise {
  quarter:      string;
  estimate:     number | null;
  actual:       number | null;
  surprise_pct: number | null;
}

// Sub-panel indicators toggleable on the price chart (persisted in localStorage).
export type SubPanelKey = 'stoch' | 'adx' | 'obv';

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
  atr_14?:                 number | null;
  atr_multiplier?:         number | null;
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
  source:       'nasdaq' | 'edgar';
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

// ── Analytics / Insights ────────────────────────────────────────────────────

export interface EnsembleHorizonMAE {
  horizon: string;   // "d1" … "d5"
  mae:     number;
}

export interface ForecastVsActualPoint {
  date:     string;
  forecast: number;
  actual:   number;
}

export interface AccuracyAnalytics {
  symbol: string;
  /** Per-model day-1 MAE (lower = better). Keys: prophet | sarima | random_forest. */
  model_mae: Partial<Record<'prophet' | 'sarima' | 'random_forest', number>>;
  best_model: 'prophet' | 'sarima' | 'random_forest' | null;
  ensemble_mae_by_horizon: EnsembleHorizonMAE[];
  /** % of resolved forecasts whose predicted direction matched actual (0–1, or null when no samples). */
  directional_accuracy: Partial<Record<'prophet' | 'sarima' | 'random_forest' | 'ensemble', number | null>>;
  forecast_vs_actual: ForecastVsActualPoint[];
  samples: number;
  /** MAE of the naive persistence forecast (predict last_price → tomorrow). */
  naive_mae?: number | null;
  /** Per-model skill score: 1 − model_mae/naive_mae. >0 beats persistence, <0 is worse than a coin-flip baseline. */
  model_skill?: Partial<Record<'prophet' | 'sarima' | 'random_forest', number>>;
  generated_at: string;
}

export interface SentimentPoint {
  date:     string;
  compound: number;
  label:    string;   // Bullish | Bearish | Neutral
}

export interface SentimentAnalytics {
  symbol:       string;
  history:      SentimentPoint[];
  current:      SentimentPoint | null;
  generated_at: string;
}

// ── Portfolio Manager (Feature 10) ──────────────────────────────────────────
// The "My Portfolio" tab tracks a user's REAL holdings + live P&L. Distinct
// from the /simulation "Simulator" backtest-race tab.

/** A raw holding row as persisted in the Supabase `holdings` table. */
export interface Holding {
  id:         string;
  symbol:     string;
  shares:     number;
  cost_basis: number;
  currency?:  string;
  opened_at?: string;
}

/** A holding enriched with live price + P&L (from GET /portfolio/summary). */
export interface PortfolioHolding {
  id:             string;
  symbol:         string;
  name:           string;
  sector:         string;
  currency:       string;
  shares:         number;
  costBasis:      number;
  price:          number;
  marketValue:    number;
  costValue:      number;
  pnl:            number;
  pnlPct:         number;
  weightPct:      number;
  direction:      'Bullish' | 'Bearish' | 'Neutral';
  directionScore: number;
}

export interface SectorAllocation {
  sector:    string;
  weightPct: number;
  value:     number;
}

export interface PortfolioForecast {
  label: 'Bullish' | 'Bearish' | 'Neutral';
  score: number;
}

// ── Watchlist (Feature 13) ──────────────────────────────────────────────────

export interface WatchlistItem {
  id:       string;
  symbol:   string;
  added_at: string;
}

export interface SparklineBar {
  t: string;   // ISO timestamp (UTC, no tz suffix)
  c: number;   // close price
}

export interface SparklineTicker {
  symbol:     string;
  price:      number;
  change_pct: number;
  bars:       SparklineBar[];
}

export interface PortfolioSummary {
  holdings:             PortfolioHolding[];
  totalMarketValue:     number;
  totalCost:            number;
  totalPnl:             number;
  totalPnlPct:          number;
  sectorAllocation:     SectorAllocation[];
  /** Herfindahl-based 0–100; higher = more diversified. */
  diversificationScore: number;
  forecast:             PortfolioForecast;
  /** Symbols skipped because live data couldn't be resolved (degraded gracefully). */
  skipped:              string[];
}

// ── Alerts & Notifications (Feature 9) ───────────────────────────────────────
// Users define alert rules; a scheduled evaluator checks them against live data
// and notifies via Web Push (+ optional email).

export type AlertRuleType =
  | 'price_cross'
  | 'rsi_threshold'
  | 'pct_move'
  | 'earnings_soon'
  | 'forecast_breakout';

export type AlertOperator = 'above' | 'below';

/** A rule row from the Supabase `alert_rules` table (GET /alerts/rules). */
export interface AlertRule {
  id:          string;
  symbol:      string;
  type:        AlertRuleType;
  operator:    AlertOperator | null;
  threshold:   number | null;
  active:      boolean;
  last_fired:  string | null;
  created_at:  string;
}

/** A fire-history row (GET /alerts/fires). */
export interface AlertFire {
  id:       string;
  rule_id:  string;
  symbol:   string;
  type:     AlertRuleType;
  message:  string;
  value:    number | null;
  fired_at: string;
}
