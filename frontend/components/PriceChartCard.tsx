'use client';

import { useState, useMemo, useCallback } from 'react';
import axios from 'axios';
import {
  Box, Card, CardContent, Chip, Collapse, CircularProgress, Stack, Typography,
  ToggleButton, ToggleButtonGroup, Button, useMediaQuery, useTheme,
} from '@mui/material';
import { Info, ChevronDown, ChevronUp, Eraser, RotateCcw } from 'lucide-react';
import dynamic from 'next/dynamic';
import type { PredictionData, IndicatorKey, ChartOverlayKey, ChartOverlayState, ChartStats, IndicatorSignals, IntervalHistoryData } from '../types';
import { formatPrice, usdRateCaption } from '../lib/currency';
import SignalPanels from './SignalPanels';

const AdvancedChart = dynamic(() => import('./AdvancedChart'), { ssr: false });

// UI label → { period, interval } for the /history endpoint
const INTERVAL_MAP: Record<string, { period: string; interval: string }> = {
  '1d': { period: '1d',  interval: '5m'  },
  '5d': { period: '5d',  interval: '15m' },
  '1m': { period: '1mo', interval: '1h'  },
  '3m': { period: '3mo', interval: '1d'  },
  '6m': { period: '6mo', interval: '1d'  },
  '1y': { period: '1y',  interval: '1d'  },
  '2y': { period: '2y',  interval: '1d'  },
} as const;

// Ranges whose bars are intraday (5m/15m/1h) — show HH:MM on the time axis.
const INTRADAY_RANGES = new Set(['1d', '5d', '1m']);

// Single localStorage key holding the full chart-overlay visibility model (F29).
const OVERLAYS_LS_KEY = 'fiforesight:chart:overlays';
// Legacy single-purpose key (FIB only) — migrated into OVERLAYS_LS_KEY on read.
const LEGACY_FIB_LS_KEY = 'fiforesight:overlay:fib';

// Default overlay visibility — S/R + the forecast projection are on (they're the
// classic chart context); VWAP + Fibonacci start off (opt-in overlays).
const DEFAULT_OVERLAYS: ChartOverlayState = {
  support: true, resistance: true, projection: true, vwap: false, fib: false,
};
const ALL_OVERLAYS_OFF: ChartOverlayState = {
  support: false, resistance: false, projection: false, vwap: false, fib: false,
};
// Default indicator set (mirrors the analysis page's initial state).
const DEFAULT_INDICATORS: IndicatorKey[] = ['bb', 'sma'];

// Read the persisted overlay state, merging the legacy FIB-only key if present.
function loadOverlays(): ChartOverlayState {
  if (typeof window === 'undefined') return DEFAULT_OVERLAYS;
  try {
    const raw = localStorage.getItem(OVERLAYS_LS_KEY);
    if (raw) return { ...DEFAULT_OVERLAYS, ...(JSON.parse(raw) as Partial<ChartOverlayState>) };
    const legacyFib = localStorage.getItem(LEGACY_FIB_LS_KEY);
    if (legacyFib != null) return { ...DEFAULT_OVERLAYS, fib: legacyFib === '1' };
  } catch { /* ignore */ }
  return DEFAULT_OVERLAYS;
}

function saveOverlays(state: ChartOverlayState): void {
  try {
    localStorage.setItem(OVERLAYS_LS_KEY, JSON.stringify(state));
    localStorage.removeItem(LEGACY_FIB_LS_KEY); // migrated — drop the old key
  } catch { /* ignore */ }
}

interface Props {
  prediction:      PredictionData;
  symbol:          string;
  indicators:      IndicatorKey[];
  setIndicators:   (v: IndicatorKey[]) => void;
  chartMode:       'line' | 'candle';
  setChartMode:    (v: 'line' | 'candle') => void;
  isDark:          boolean;
  primaryColor:    string;
  trendColor:      string;
  chartStats:      ChartStats | null;
  indicatorSignals: IndicatorSignals;
  // Currency-aware display (F35). `currency`/`fx` are the ACTIVE display pair
  // (already 'USD' + the rate when the toggle is on); the native* props drive
  // the toggle itself, which only renders for non-USD names with a live rate.
  currency?:       string | null;
  fx?:             number | null;
  nativeCurrency?: string | null;
  fxToUsd?:        number | null;
  showUsd?:        boolean;
  onToggleUsd?:    (v: boolean) => void;
}

export default function PriceChartCard({
  prediction, symbol, indicators, setIndicators,
  chartMode, setChartMode,
  isDark, primaryColor, trendColor, chartStats, indicatorSignals,
  currency = 'USD', fx, nativeCurrency, fxToUsd, showUsd = false, onToggleUsd,
}: Props) {
  const fxRate   = fx ?? 1;   // display-time multiplier (1 = native currency)
  const theme    = useTheme();
  const isXs     = useMediaQuery(theme.breakpoints.down('sm'));
  const isSm     = useMediaQuery(theme.breakpoints.between('sm', 'md'));
  const chartH   = isXs ? 220 : isSm ? 300 : 400;

  const [legendOpen,       setLegendOpen]       = useState(false);
  const [selectedInterval, setSelectedInterval] = useState<string>('2y');
  const [intervalData,     setIntervalData]     = useState<IntervalHistoryData | null>(null);
  const [historyLoading,   setHistoryLoading]   = useState(false);

  // Unified overlay-visibility model (F29) — covers VWAP, Fibonacci, S/R and the
  // forecast projection in one persisted object. Lazy initialiser restores it
  // (and migrates the legacy FIB-only key) without an effect. Persisted across
  // symbol switches by design. The indicator set (bb/sma/…) stays parent-owned
  // via `indicators`/`setIndicators`; the toggle UI below presents both together.
  const [overlays, setOverlays] = useState<ChartOverlayState>(loadOverlays);
  const toggleOverlay = useCallback((key: ChartOverlayKey) => {
    setOverlays(prev => {
      const next = { ...prev, [key]: !prev[key] };
      saveOverlays(next);
      return next;
    });
  }, []);
  const toggleIndicator = useCallback((key: IndicatorKey) => {
    setIndicators(
      indicators.includes(key) ? indicators.filter(k => k !== key) : [...indicators, key],
    );
  }, [indicators, setIndicators]);
  // "Clean view" — strip every overlay + indicator for a bare price chart (#284).
  const cleanView = useCallback(() => {
    setIndicators([]);
    setOverlays(ALL_OVERLAYS_OFF);
    saveOverlays(ALL_OVERLAYS_OFF);
  }, [setIndicators]);
  // "Reset" — restore the default indicator set + overlay visibility.
  const resetView = useCallback(() => {
    setIndicators(DEFAULT_INDICATORS);
    setOverlays(DEFAULT_OVERLAYS);
    saveOverlays(DEFAULT_OVERLAYS);
  }, [setIndicators]);

  // Track the last symbol we rendered for — reset interval when it changes.
  // (Derived-state-during-render is React's recommended pattern for resetting
  // state on a prop change — see "You Might Not Need an Effect".)
  const [lastSymbol, setLastSymbol] = useState(prediction.symbol);
  if (lastSymbol !== prediction.symbol) {
    setLastSymbol(prediction.symbol);
    setSelectedInterval('2y');
    setIntervalData(null);
  }
  const fetchIntervalHistory = useCallback((iv: string) => {
    if (iv === '2y') {
      setIntervalData(null);
      return;
    }
    const { period, interval } = INTERVAL_MAP[iv];
    setHistoryLoading(true);
    axios
      .get(`/api/history?symbol=${encodeURIComponent(symbol)}&period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}`)
      .then(r => setIntervalData(r.data))
      .catch(() => setIntervalData(null))
      .finally(() => setHistoryLoading(false));
  }, [symbol]);

  const handleIntervalChange = useCallback((iv: string) => {
    setSelectedInterval(iv);
    // Overlay visibility persists across ranges; each overlay self-gates on
    // applicability (VWAP only renders intraday, S/R + projection only on 2Y).
    fetchIntervalHistory(iv);
  }, [fetchIntervalHistory]);

  // Active history — interval fetch takes precedence over prediction.history
  const activeHistory = useMemo(() => {
    if (intervalData && selectedInterval !== '2y') return intervalData.history;
    return prediction.history;
  }, [intervalData, selectedInterval, prediction.history]);

  // Stats for the active interval
  const activeStats = useMemo(() => {
    if (intervalData && selectedInterval !== '2y') {
      const s = intervalData.stats;
      const isUp  = s.change_pct >= 0;
      return {
        changePct:   s.change_pct,
        isUp,
        high:        s.period_high,
        low:         s.period_low,
        sma20:       s.sma20,
        annVol:      s.ann_vol,
        color:       isUp ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626'),
      };
    }
    if (!chartStats) return null;
    return {
      changePct: chartStats.changePct,
      isUp:      chartStats.isUp,
      high:      chartStats.high,
      low:       chartStats.low,
      sma20:     prediction.modelStats?.sma_20   ?? null,
      annVol:    prediction.modelStats?.ann_volatility_pct ?? null,
      color:     chartStats.color,
    };
  }, [intervalData, selectedInterval, chartStats, prediction.modelStats, isDark]);

  // Range-aware data for the always-on AdvancedChart (lightweight-charts).
  // Forecast / support / resistance only apply to the native 2Y view.
  const isTwoYear = selectedInterval === '2y';
  const intraday  = INTRADAY_RANGES.has(selectedInterval);

  // Fibonacci retracement levels (F25) — only on the native 2Y view, where the
  // indicator payload's swing high/low applies. Ordered by ratio (0.0 → 1.0).
  const fib = prediction.indicators?.fibonacci ?? null;

  // True when at least one overlay/indicator is actually drawn on the current
  // range — drives the legend empty-state (a "Clean view" shows nothing). The
  // fib branch uses the same `!!fib` guard as the toggle row + legend, so a
  // saved overlays.fib=true on a ticker with no Fibonacci data doesn't wrongly
  // suppress the empty-state.
  const anyOverlayVisible =
    indicators.length > 0 ||
    (isTwoYear && (overlays.support || overlays.resistance || overlays.projection || (overlays.fib && !!fib))) ||
    (intraday && overlays.vwap);
  const rsiSeries = isTwoYear
    ? (prediction.indicators?.rsi_series ?? [])
    : (intervalData?.rsi_series ?? []);

  const fibLevels = useMemo(
    () => (fib
      ? Object.entries(fib.levels)
          .map(([ratio, price]) => ({ ratio, price }))
          .sort((a, b) => Number(a.ratio) - Number(b.ratio))
      : []),
    [fib],
  );

  const toggleSx = {
    '& .MuiToggleButton-root': {
      fontSize: '0.65rem', fontWeight: 800, letterSpacing: 1,
      py: 0.4, px: 1.5, borderRadius: '6px !important',
      border: '1px solid rgba(128,128,128,0.2) !important',
      '&.Mui-selected': { background: `${primaryColor}1a`, color: primaryColor },
      '&:not(.Mui-selected)': { color: 'rgba(128,128,128,0.5)' },
      '&:hover': { color: primaryColor, background: `${primaryColor}0d` },
    },
  };

  return (
    <Card>
      <CardContent sx={{ p: { xs: 2, sm: 3, md: 4 } }}>
        {/* Symbol header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
          <Box>
            <Typography sx={{ fontWeight: 800, fontSize: { xs: '1.75rem', sm: '2.5rem', md: '3.75rem' }, lineHeight: 1.1 }}>
              {prediction.symbol}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
              <Chip
                label={`${prediction.prediction.trend} Trend`}
                color={prediction.prediction.trend === 'Bullish' ? 'success'
                  : prediction.prediction.trend === 'Bearish' ? 'error' : 'default'}
                size="small"
                sx={{ fontWeight: 900, fontSize: '0.7rem' }}
              />
              {prediction.metrics.sector && prediction.metrics.sector !== 'N/A' && (
                <Chip label={prediction.metrics.sector} size="small" variant="outlined" sx={{ fontSize: '0.65rem', opacity: 0.6 }} />
              )}
            </Stack>
          </Box>
          <Box sx={{ textAlign: 'right' }}>
            <Typography color="primary.main" sx={{ fontWeight: 700, fontSize: { xs: '1.5rem', sm: '2rem', md: '3rem' }, lineHeight: 1.1 }}>
              {formatPrice(parseFloat(prediction.currentPrice) * fxRate, currency)}
            </Typography>
            <Typography variant="caption" sx={{ opacity: 0.4, display: 'block' }}>
              {currency || 'USD'} · LIVE FEED
            </Typography>
            {/* "Show in USD" toggle — only for non-USD names with a live FX rate */}
            {nativeCurrency && nativeCurrency !== 'USD' && fxToUsd != null && onToggleUsd && (
              <Box sx={{ mt: 0.75, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.25 }}>
                <ToggleButtonGroup
                  exclusive size="small" aria-label="display currency"
                  value={showUsd ? 'usd' : 'native'}
                  onChange={(_e, val) => val && onToggleUsd(val === 'usd')}
                  sx={toggleSx}
                >
                  <ToggleButton value="native">{nativeCurrency}</ToggleButton>
                  <ToggleButton value="usd">USD</ToggleButton>
                </ToggleButtonGroup>
                <Typography variant="caption" sx={{ opacity: 0.35, fontSize: '0.6rem' }}>
                  {usdRateCaption(nativeCurrency, fxToUsd)}
                </Typography>
              </Box>
            )}
          </Box>
        </Box>

        {/* Stats bar */}
        {activeStats && (
          <Stack direction="row" spacing={3} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
            {[
              {
                label: 'CHANGE',
                val: `${activeStats.isUp ? '+' : ''}${activeStats.changePct.toFixed(2)}%`,
                col: activeStats.color,
              },
              { label: 'PERIOD HIGH', val: activeStats.high != null && activeStats.high > 0 ? formatPrice(Number(activeStats.high) * fxRate, currency) : '—', col: isDark ? '#00ffa3' : '#16a34a' },
              { label: 'PERIOD LOW',  val: activeStats.low  != null && activeStats.low  > 0 ? formatPrice(Number(activeStats.low) * fxRate, currency)  : '—', col: isDark ? '#ff0055' : '#dc2626' },
              { label: 'SMA 20',      val: activeStats.sma20 != null ? formatPrice(Number(activeStats.sma20) * fxRate, currency) : '—', col: '#f59e0b' },
              { label: 'ANN. VOL',    val: activeStats.annVol != null ? `${Number(activeStats.annVol).toFixed(2)}%` : '—', col: 'text.secondary' },
            ].map(s => (
              <Box key={s.label}>
                <Typography variant="caption" sx={{ opacity: 0.4, display: 'block', letterSpacing: 1 }}>{s.label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 800, color: s.col }}>{s.val}</Typography>
              </Box>
            ))}
          </Stack>
        )}

        {/* Time interval selector */}
        <ToggleButtonGroup
          exclusive
          value={selectedInterval}
          onChange={(_e, val) => val && handleIntervalChange(val)}
          size="small"
          sx={{ mb: 2, ...toggleSx }}
        >
          {(['1d', '5d', '1m', '3m', '6m', '1y', '2y'] as const).map(iv => (
            <ToggleButton key={iv} value={iv}>
              {iv.toUpperCase()}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        {/* Chart mode (line/candle) — not an overlay, kept on its own row */}
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap' }}>
          <ToggleButtonGroup exclusive aria-label="chart-mode" value={chartMode}
            onChange={(_e, val) => val && setChartMode(val)} size="small" sx={toggleSx}
          >
            <ToggleButton value="line">LINE</ToggleButton>
            <ToggleButton value="candle">CANDLE</ToggleButton>
          </ToggleButtonGroup>
        </Box>

        {/* Unified overlay controls (F29) — every chart line toggles independently
            (#284/#287a). Indicators (parent-owned set) + chart overlays (VWAP, S/R,
            forecast projection, Fibonacci) live in one wrapping/scrollable row, with
            "Clean view" (clear all) and "Reset" (restore defaults). Overlays self-gate
            on the active range so only applicable toggles render. */}
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1, mb: 1 }}>
            <Typography variant="caption" sx={{ opacity: 0.4, letterSpacing: 1.5, fontWeight: 800 }}>
              OVERLAYS
            </Typography>
            <Stack direction="row" spacing={0.5}>
              <Button size="small" variant="text" onClick={cleanView} startIcon={<Eraser size={12} />}
                sx={{ fontSize: '0.6rem', letterSpacing: 1, py: 0.2, px: 1, opacity: 0.7, '&:hover': { opacity: 1 } }}>
                Clean view
              </Button>
              <Button size="small" variant="text" onClick={resetView} startIcon={<RotateCcw size={12} />}
                sx={{ fontSize: '0.6rem', letterSpacing: 1, py: 0.2, px: 1, opacity: 0.7, '&:hover': { opacity: 1 } }}>
                Reset
              </Button>
            </Stack>
          </Box>
          <Box
            sx={{
              display: 'flex', flexWrap: 'wrap', gap: 0.5,
              overflowX: 'auto', pb: 0.5,
              '&::-webkit-scrollbar': { height: 4 },
              '& .MuiToggleButton-root': {
                fontSize: '0.65rem', fontWeight: 700, py: 0.5, px: 1.5,
                borderRadius: '8px !important', whiteSpace: 'nowrap',
                border: '1px solid rgba(128,128,128,0.2) !important',
                '&.Mui-selected': { background: `${primaryColor}1a`, color: primaryColor },
                '&:not(.Mui-selected)': { color: 'rgba(128,128,128,0.6)' },
                '&:hover': { color: primaryColor, background: `${primaryColor}0d` },
              },
            }}
          >
            {/* Technical indicators (parent-owned multi-select set) */}
            {([
              { key: 'bb',     label: 'Bollinger Bands' },
              { key: 'sma',    label: 'SMA 50/200'      },
              { key: 'ema',    label: 'EMA 20/50'       },
              { key: 'macd',   label: 'MACD'            },
              { key: 'rsi',    label: 'RSI'             },
              { key: 'volume', label: 'Volume'          },
            ] as { key: IndicatorKey; label: string }[]).map(({ key, label }) => (
              <ToggleButton
                key={key} value={key}
                selected={indicators.includes(key)}
                onChange={() => toggleIndicator(key)}
              >
                {label}
              </ToggleButton>
            ))}

            {/* Chart overlays — each self-gates on the active range */}
            {([
              { key: 'support',    label: 'Support',    show: isTwoYear },
              { key: 'resistance', label: 'Resistance', show: isTwoYear },
              { key: 'projection', label: 'Forecast',   show: isTwoYear },
              { key: 'fib',        label: 'Fibonacci',  show: isTwoYear && !!fib },
              { key: 'vwap',       label: 'VWAP',       show: intraday },
            ] as { key: ChartOverlayKey; label: string; show: boolean }[])
              .filter(o => o.show)
              .map(({ key, label }) => (
                <ToggleButton
                  key={key} value={key}
                  selected={overlays[key]}
                  onChange={() => toggleOverlay(key)}
                >
                  {label}
                </ToggleButton>
              ))}
          </Box>
        </Box>

        {/* Indicators Guide (collapsible) */}
        <Box sx={{ mb: 1 }}>
          <Button
            size="small" variant="text"
            onClick={() => setLegendOpen(o => !o)}
            startIcon={<Info size={12} />}
            endIcon={legendOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            sx={{
              fontSize: '0.6rem', letterSpacing: 1.5, textTransform: 'uppercase',
              py: 0.3, px: 1, opacity: 0.45, transition: 'opacity 0.2s',
              '&:hover': { opacity: 1 },
            }}
          >
            Indicators Guide
          </Button>
          <Collapse in={legendOpen}>
            <Box sx={{
              mt: 1, p: 2, borderRadius: 2,
              background: isDark ? 'rgba(255,255,255,0.015)' : 'rgba(0,0,0,0.025)',
              border: `1px solid ${primaryColor}1a`,
            }}>
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 1.5 }}>
                {([
                  { key: 'bb', visible: indicators.includes('bb'), label: 'Bollinger Bands', color: primaryColor,
                    description: 'Dashed envelope: upper/lower = ±2 std devs from the 20-day MA. Bands widen during high volatility, narrow during consolidation.' },
                  { key: 'sma', visible: indicators.includes('sma'), label: 'SMA 50 / SMA 200', color: '#f97316', color2: '#a855f7',
                    description: 'Trend-following averages. SMA50 (orange) tracks medium-term, SMA200 (purple) tracks long-term. Golden cross (50 > 200) = bullish; death cross (50 < 200) = bearish.' },
                  { key: 'ema', visible: indicators.includes('ema'), label: 'EMA 20 / EMA 50', color: '#06b6d4', color2: '#f43f5e',
                    description: 'Exponential Moving Averages weight recent prices more heavily than SMA, reacting faster to momentum shifts. EMA20 (cyan dashed) for short-term momentum, EMA50 (rose dashed) confirms trend direction.' },
                  { key: 'macd', visible: indicators.includes('macd'), label: 'MACD (12, 26, 9)', color: isDark ? '#00f2ff' : '#0077ff',
                    description: 'Momentum oscillator (own sub-pane). Line crossing above signal = bullish; below = bearish. Histogram bars show momentum strength — growing bars = accelerating trend.' },
                  { key: 'rsi', visible: indicators.includes('rsi'), label: 'RSI (14)', color: '#bc13fe',
                    description: 'Relative Strength Index (own sub-pane): 0–100 oscillator. Above 70 = overbought (potential reversal down). Below 30 = oversold (potential reversal up). 50 is the neutral midline.' },
                  { key: 'volume', visible: indicators.includes('volume'), label: 'Volume', color: primaryColor,
                    description: 'Number of shares traded (own sub-pane). High volume on an up-move = strong buying conviction. High volume on a down-move = heavy selling distribution. Low volume = weak signal.' },
                  { key: 'support', visible: isTwoYear && overlays.support, label: 'Support Levels (S)', color: isDark ? '#00ffa3' : '#16a34a',
                    description: 'Green dashed price lines — floors from the last 3 months (local price minima). Historically where buyers stepped in: expect a potential bounce or consolidation when revisited.' },
                  { key: 'resistance', visible: isTwoYear && overlays.resistance, label: 'Resistance Levels (R)', color: isDark ? '#ff0055' : '#dc2626',
                    description: 'Red dashed price lines — ceilings from the last 3 months (local price maxima). Historically where sellers emerged: expect potential rejection or slowdown on approach.' },
                  { key: 'projection', visible: isTwoYear && overlays.projection, label: 'Forecast Projection', color: '#bc13fe',
                    description: 'Purple dashed line + lighter band = the ensemble 48h price forecast (predicted path with its high/low range). Wider band = lower model confidence.' },
                  { key: 'fib', visible: isTwoYear && overlays.fib && !!fib, label: 'Fibonacci Levels', color: theme.palette.warning.main,
                    description: 'Amber dashed price lines at 23.6 / 38.2 / 50 / 61.8% retracements between the recent swing high and low — common support/resistance zones during pullbacks.' },
                  { key: 'vwap', visible: intraday && overlays.vwap, label: 'VWAP', color: '#ff9800',
                    description: 'Orange dashed line — volume-weighted average price, reset each session. Price above VWAP = intraday buyers in control; below = sellers in control.' },
                ] as { key: string; visible: boolean; label: string; color: string; color2?: string; description: string }[])
                  .filter(item => item.visible)
                  .map(item => {
                    const sig = indicatorSignals[item.key];
                    return (
                      <Box key={item.key} sx={{
                        p: 1.5, borderRadius: 1.5,
                        background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)',
                        border: `1px solid ${item.color}22`,
                        display: 'flex', flexDirection: 'column', gap: 0.5,
                      }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                          <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: item.color, flexShrink: 0 }} />
                          {item.color2 && <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: item.color2, flexShrink: 0 }} />}
                          <Typography sx={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: 0.5 }}>{item.label}</Typography>
                        </Box>
                        <Typography sx={{ fontSize: '0.6rem', opacity: 0.55, lineHeight: 1.5 }}>
                          {item.description}
                        </Typography>
                        {sig && (
                          <Box sx={{
                            mt: 0.5, px: 1, py: 0.4, borderRadius: 1,
                            background: `${sig.color}14`,
                            border: `1px solid ${sig.color}33`,
                          }}>
                            <Typography sx={{ fontSize: '0.58rem', color: sig.color, fontWeight: 700, lineHeight: 1.4 }}>
                              ▶ {sig.text}
                            </Typography>
                          </Box>
                        )}
                      </Box>
                    );
                  })}
              </Box>
              {!anyOverlayVisible && (
                <Typography sx={{ fontSize: '0.62rem', opacity: 0.5, fontStyle: 'italic' }}>
                  Clean view — no overlays active. Toggle overlays above to plot them and see what each colour means here.
                </Typography>
              )}
            </Box>
          </Collapse>
        </Box>

        {/* Unified interactive chart (lightweight-charts) for EVERY range.
            The backend now supplies a real epoch `time` per bar, so zoom/pan
            works on intraday and daily ranges alike — no MM/DD reconstruction. */}
        <Box sx={{ position: 'relative' }}>
          {historyLoading && (
            <Box sx={{
              position: 'absolute', inset: 0, zIndex: 10, borderRadius: 2,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: isDark ? 'rgba(13,21,32,0.75)' : 'rgba(255,255,255,0.75)',
              backdropFilter: 'blur(4px)',
            }}>
              <CircularProgress size={36} sx={{ color: primaryColor }} />
            </Box>
          )}
          <AdvancedChart
            history={activeHistory}
            forecast={isTwoYear && overlays.projection ? prediction.forecastDays : []}
            rsiSeries={rsiSeries}
            indicators={indicators}
            mode={chartMode}
            isDark={isDark}
            primaryColor={primaryColor}
            trendColor={trendColor}
            support={isTwoYear && overlays.support ? (prediction.indicators?.support ?? []) : []}
            resistance={isTwoYear && overlays.resistance ? (prediction.indicators?.resistance ?? []) : []}
            intraday={intraday}
            showVwap={intraday && overlays.vwap}
            fibLevels={isTwoYear ? fibLevels : []}
            showFib={isTwoYear && overlays.fib}
            fibColor={theme.palette.warning.main}
            priceHeight={chartH}
          />
        </Box>

        {/* Advanced signal sub-panels (Feature 14) — Stoch / ADX / OBV +
            RSI/MACD divergence badges. Only on the native 2Y view, where the
            indicator payload (latest scalars + OBV history) applies. */}
        {isTwoYear && (
          <SignalPanels
            stochK={prediction.indicators?.stoch_k}
            stochD={prediction.indicators?.stoch_d}
            adx={prediction.indicators?.adx_14}
            plusDi={prediction.indicators?.plus_di}
            minusDi={prediction.indicators?.minus_di}
            obvHistory={prediction.indicators?.obv_history}
            divergences={prediction.indicators?.divergences}
            isDark={isDark}
            primaryColor={primaryColor}
          />
        )}
      </CardContent>
    </Card>
  );
}
