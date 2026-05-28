'use client';

import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Box, Card, CardContent, Chip, Collapse, CircularProgress, Stack, Typography,
  ToggleButton, ToggleButtonGroup, Button,
} from '@mui/material';
import { Info, ChevronDown, ChevronUp } from 'lucide-react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Line, ReferenceLine, ComposedChart, Area, Legend,
  BarChart, Bar, Cell,
} from 'recharts';
import dynamic from 'next/dynamic';
import VolumeProfile from './VolumeProfile';
import type { PredictionData, IndicatorKey, ChartEntry, ChartStats, IndicatorSignals, IntervalHistoryData } from '../types';

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

const CHART_HEIGHT = 380;

interface Props {
  prediction:      PredictionData;
  symbol:          string;
  indicators:      IndicatorKey[];
  setIndicators:   (v: IndicatorKey[]) => void;
  chartMode:       'line' | 'candle';
  setChartMode:    (v: 'line' | 'candle') => void;
  chartEngine:     'classic' | 'pro';
  setChartEngine:  (v: 'classic' | 'pro') => void;
  isDark:          boolean;
  primaryColor:    string;
  trendColor:      string;
  chartStats:      ChartStats | null;
  indicatorSignals: IndicatorSignals;
}

export default function PriceChartCard({
  prediction, symbol, indicators, setIndicators,
  chartMode, setChartMode, chartEngine, setChartEngine,
  isDark, primaryColor, trendColor, chartStats, indicatorSignals,
}: Props) {
  const [legendOpen,       setLegendOpen]       = useState(false);
  const [selectedInterval, setSelectedInterval] = useState<string>('2y');
  const [intervalData,     setIntervalData]     = useState<IntervalHistoryData | null>(null);
  const [historyLoading,   setHistoryLoading]   = useState(false);
  // Track the last symbol we rendered for — reset interval when it changes
  const [lastSymbol, setLastSymbol] = useState(prediction.symbol);
  if (lastSymbol !== prediction.symbol) {
    setLastSymbol(prediction.symbol);
    setSelectedInterval('2y');
    setIntervalData(null);
  }
  const chartBoxRef = useRef<HTMLDivElement>(null);
  const [clipBox, setClipBox] = useState<{ l: number; t: number; w: number; h: number } | null>(null);

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

  useEffect(() => {
    if (chartMode !== 'candle') return;
    const el = chartBoxRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.querySelector('clipPath rect');
      if (!rect) return;
      setClipBox({
        l: +rect.getAttribute('x')!,
        t: +rect.getAttribute('y')!,
        w: +rect.getAttribute('width')!,
        h: +rect.getAttribute('height')!,
      });
    };
    measure();
    const id = setTimeout(measure, 50);
    return () => clearTimeout(id);
  }, [chartMode, prediction, chartEngine]);

  const chartData = useMemo(() => {
    const hist = activeHistory.map(h => {
      const bbU = h.bb_upper ?? undefined;
      const bbL = h.bb_lower ?? undefined;
      return {
        date:      h.date,
        price:     h.price,
        bb_upper:  bbU,
        bb_middle: h.bb_middle ?? undefined,
        bb_lower:  bbL,
        bb_band:   bbU != null && bbL != null ? bbU - bbL : undefined,
        sma50:     h.sma50  ?? undefined,
        sma200:    h.sma200 ?? undefined,
        ema20:     h.ema20  ?? undefined,
        ema50:     h.ema50  ?? undefined,
        vwap:      (h as any).vwap ?? undefined,
        predicted: undefined as number | undefined,
        foreHigh:  undefined as number | undefined,
        foreLow:   undefined as number | undefined,
        fore_band: undefined as number | undefined,
      };
    });
    // Forecast days only shown on 2Y (they come from prediction, not interval fetch)
    const fore = selectedInterval === '2y'
      ? (prediction.forecastDays || []).map(f => ({
          date:      f.date,
          price:     undefined as number | undefined,
          bb_upper:  undefined, bb_middle: undefined, bb_lower: undefined, bb_band: undefined,
          sma50:     undefined, sma200:    undefined, ema20: undefined, ema50: undefined,
          vwap:      undefined,
          predicted: f.predicted,
          foreHigh:  f.high,
          foreLow:   f.low,
          fore_band: f.high != null && f.low != null ? f.high - f.low : undefined,
        }))
      : [];
    return [...hist, ...fore];
  }, [activeHistory, prediction.forecastDays, selectedInterval]);

  const candleChartData = useMemo(() => {
    const hist = activeHistory.map(h => {
      const bbU = h.bb_upper ?? undefined;
      const bbL = h.bb_lower ?? undefined;
      return {
        date:      h.date,
        open:      h.open  ?? h.price,
        high:      h.high  ?? h.price,
        low:       h.low   ?? h.price,
        close:     h.price,
        bb_upper:  bbU,
        bb_middle: h.bb_middle ?? undefined,
        bb_lower:  bbL,
        bb_band:   bbU != null && bbL != null ? bbU - bbL : undefined,
        sma50:     h.sma50  ?? undefined,
        sma200:    h.sma200 ?? undefined,
        ema20:     h.ema20  ?? undefined,
        ema50:     h.ema50  ?? undefined,
        vwap:      (h as any).vwap ?? undefined,
        predicted: undefined as number | undefined,
        foreHigh:  undefined as number | undefined,
        foreLow:   undefined as number | undefined,
        fore_band: undefined as number | undefined,
      };
    });
    const fore = selectedInterval === '2y'
      ? (prediction.forecastDays || []).map(f => ({
          date: f.date, open: undefined as number | undefined,
          high: undefined as number | undefined, low: undefined as number | undefined,
          close: undefined as number | undefined,
          bb_upper: undefined, bb_middle: undefined, bb_lower: undefined, bb_band: undefined,
          sma50: undefined, sma200: undefined, ema20: undefined, ema50: undefined,
          vwap: undefined,
          predicted: f.predicted, foreHigh: f.high, foreLow: f.low,
          fore_band: f.high != null && f.low != null ? f.high - f.low : undefined,
        }))
      : [];
    return [...hist, ...fore];
  }, [activeHistory, prediction.forecastDays, selectedInterval]);

  const macdData = useMemo(() =>
    activeHistory.map(h => ({
      date:   h.date,
      macd:   h.macd        ?? null,
      signal: h.macd_signal ?? null,
      hist:   h.macd_hist   ?? null,
    }))
  , [activeHistory]);

  const rsiData = useMemo(() => {
    if (intervalData && selectedInterval !== '2y') {
      return activeHistory.map((h, i) => ({
        date: h.date,
        rsi:  intervalData.rsi_series[i] ?? (h as any).rsi ?? null,
      }));
    }
    const rsiSeries = prediction.indicators?.rsi_series ?? [];
    return activeHistory.map((h, i) => ({
      date: h.date,
      rsi:  rsiSeries[i] ?? null,
    }));
  }, [activeHistory, intervalData, selectedInterval, prediction.indicators]);

  const volumeData = useMemo(() =>
    activeHistory.map(h => ({
      date:   h.date,
      volume: h.volume ?? 0,
    }))
  , [activeHistory]);

  const chartDomain = useMemo((): [number, number] | ['auto', 'auto'] => {
    const data = chartMode === 'line' ? chartData : candleChartData;
    if (!data.length) return ['auto', 'auto'];
    const allVals = data.flatMap(d => [
      (d as any).price,    (d as any).predicted, (d as any).foreHigh, (d as any).foreLow,
      (d as any).open,     (d as any).high,       (d as any).low,      (d as any).close,
      indicators.includes('bb')  ? (d as any).bb_upper  : undefined,
      indicators.includes('bb')  ? (d as any).bb_lower  : undefined,
      indicators.includes('sma') ? (d as any).sma50     : undefined,
      indicators.includes('sma') ? (d as any).sma200    : undefined,
      indicators.includes('ema') ? (d as any).ema20     : undefined,
      indicators.includes('ema') ? (d as any).ema50     : undefined,
    ].filter((v): v is number => v !== undefined && v !== null));
    if (!allVals.length) return ['auto', 'auto'];
    const min = Math.min(...allVals);
    const max = Math.max(...allVals);
    const pad = (max - min) * 0.12 || max * 0.02;
    return [min - pad, max + pad];
  }, [chartData, candleChartData, chartMode, indicators]);

  // Detect notable trading days: large price moves (>1.5σ) or volume spikes (>2× median)
  const eventMarkers = useMemo(() => {
    const hist = activeHistory;
    if (hist.length < 10) return [];

    const returns = hist.slice(1).map((h, i) => (h.price - hist[i].price) / hist[i].price);
    const mu  = returns.reduce((s, r) => s + r, 0) / returns.length;
    const sig = Math.sqrt(returns.reduce((s, r) => s + (r - mu) ** 2, 0) / returns.length);

    const vols = hist.map(h => h.volume ?? 0).filter(v => v > 0);
    const medVol = vols.length ? [...vols].sort((a, b) => a - b)[Math.floor(vols.length / 2)] : 0;

    const events: { date: string; type: 'up' | 'down' | 'volume'; label: string; pct: number; z: number }[] = [];
    returns.forEach((ret, i) => {
      const h      = hist[i + 1];
      const zScore = sig > 0 ? Math.abs(ret - mu) / sig : 0;
      const volMult = medVol > 0 ? (h.volume ?? 0) / medVol : 0;
      const volSpike = volMult > 2.2;
      if (zScore >= 1.5 || volSpike) {
        const isUp   = ret > 0;
        const pctVal = ret * 100;
        // Short label: "▲+7.9%" or "◆vol×3.1" to avoid overflow
        const label  = zScore >= 1.5
          ? `${isUp ? '+' : ''}${pctVal.toFixed(1)}%`
          : `vol×${volMult.toFixed(1)}`;
        events.push({ date: h.date, type: volSpike && zScore < 1.5 ? 'volume' : isUp ? 'up' : 'down', label, pct: pctVal, z: zScore });
      }
    });

    // Sort by significance, deduplicate events closer than 5 trading days, keep top 5
    const sorted = events.sort((a, b) => Math.abs(b.z) - Math.abs(a.z));
    const kept: typeof events = [];
    for (const ev of sorted) {
      const tooClose = kept.some(k => Math.abs(hist.findIndex(h => h.date === ev.date) - hist.findIndex(h => h.date === k.date)) < 5);
      if (!tooClose) kept.push(ev);
      if (kept.length >= 5) break;
    }
    return kept;
  }, [activeHistory]);

  const SERIES_LABEL_MAP: Record<string, string> = {
    price: 'Close', close: 'Close (OHLC)', predicted: 'Forecast',
    foreHigh: 'Fore. High', foreLow: 'Fore. Low',
    bb_upper: 'BB Upper', bb_middle: 'BB Mid', bb_lower: 'BB Lower',
    sma50: 'SMA 50', sma200: 'SMA 200', ema20: 'EMA 20', ema50: 'EMA 50',
    vwap: 'VWAP',
  };

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
      <CardContent sx={{ p: 4 }}>
        {/* Symbol header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
          <Box>
            <Typography variant="h2">{prediction.symbol}</Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
              <Chip
                label={`${prediction.prediction.trend} Trend`}
                color={prediction.prediction.trend === 'Bullish' ? 'success' : 'error'}
                size="small"
                sx={{ fontWeight: 900, fontSize: '0.7rem' }}
              />
              {prediction.metrics.sector && prediction.metrics.sector !== 'N/A' && (
                <Chip label={prediction.metrics.sector} size="small" variant="outlined" sx={{ fontSize: '0.65rem', opacity: 0.6 }} />
              )}
            </Stack>
          </Box>
          <Box sx={{ textAlign: 'right' }}>
            <Typography variant="h3" color="primary.main">${prediction.currentPrice}</Typography>
            <Typography variant="caption" sx={{ opacity: 0.4 }}>
              {prediction.metrics.currency ?? 'USD'} · LIVE FEED
            </Typography>
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
              { label: 'PERIOD HIGH', val: activeStats.high != null && activeStats.high > 0 ? `$${Number(activeStats.high).toFixed(2)}` : '—', col: isDark ? '#00ffa3' : '#16a34a' },
              { label: 'PERIOD LOW',  val: activeStats.low  != null && activeStats.low  > 0 ? `$${Number(activeStats.low).toFixed(2)}`  : '—', col: isDark ? '#ff0055' : '#dc2626' },
              { label: 'SMA 20',      val: activeStats.sma20 != null ? `$${Number(activeStats.sma20).toFixed(2)}` : '—', col: '#f59e0b' },
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

        {/* Indicator toggles */}
        <ToggleButtonGroup
          value={indicators}
          onChange={(_, v) => setIndicators(v)}
          size="small"
          sx={{ mb: 2, flexWrap: 'wrap', gap: 0.5 }}
        >
          {([
            { key: 'bb',     label: 'Bollinger Bands' },
            { key: 'sma',    label: 'SMA 50/200'      },
            { key: 'ema',    label: 'EMA 20/50'       },
            { key: 'macd',   label: 'MACD'            },
            { key: 'rsi',    label: 'RSI'             },
            { key: 'volume', label: 'Volume'          },
          ] as { key: IndicatorKey; label: string }[]).map(({ key, label }) => (
            <ToggleButton key={key} value={key} sx={{ fontSize: '0.65rem', py: 0.5, px: 1.5, borderRadius: '8px !important' }}>
              {label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        {/* Chart mode + engine toggles */}
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap' }}>
          <ToggleButtonGroup exclusive aria-label="chart-mode" value={chartMode}
            onChange={(_e, val) => val && setChartMode(val)} size="small" sx={toggleSx}
          >
            <ToggleButton value="line">LINE</ToggleButton>
            <ToggleButton value="candle">CANDLE</ToggleButton>
          </ToggleButtonGroup>
          <ToggleButtonGroup exclusive aria-label="chart-engine" value={chartEngine}
            onChange={(_e, val) => val && setChartEngine(val)} size="small" sx={toggleSx}
          >
            <ToggleButton value="classic">CLASSIC</ToggleButton>
            <ToggleButton value="pro">PRO (ZOOM)</ToggleButton>
          </ToggleButtonGroup>
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
                  { key: 'bb', always: false, label: 'Bollinger Bands', color: primaryColor,
                    description: 'Volatility envelope: upper/lower = ±2 std devs from the 20-day MA. Bands widen during high volatility, narrow during consolidation.' },
                  { key: 'sma', always: false, label: 'SMA 50 / SMA 200', color: '#f97316', color2: '#a855f7',
                    description: 'Trend-following averages. SMA50 (orange) tracks medium-term, SMA200 (purple) tracks long-term. Golden cross (50 > 200) = bullish; death cross (50 < 200) = bearish.' },
                  { key: 'ema', always: false, label: 'EMA 20 / EMA 50', color: '#06b6d4', color2: '#f43f5e',
                    description: 'Exponential Moving Averages weight recent prices more heavily than SMA, reacting faster to momentum shifts. EMA20 (cyan) for short-term momentum, EMA50 (rose) confirms trend direction. EMA20 crossing EMA50 is a faster golden/death cross signal.' },
                  { key: 'macd', always: false, label: 'MACD (12, 26, 9)', color: isDark ? '#00f2ff' : '#0077ff',
                    description: 'Momentum oscillator. Line crossing above signal = bullish; below = bearish. Histogram bars show momentum strength — growing bars = accelerating trend.' },
                  { key: 'rsi', always: false, label: 'RSI (14)', color: '#bc13fe',
                    description: 'Relative Strength Index: 0–100 oscillator. Above 70 = overbought (potential reversal down). Below 30 = oversold (potential reversal up). 50 is the neutral midline.' },
                  { key: 'volume', always: false, label: 'Volume', color: primaryColor,
                    description: 'Number of shares traded. High volume on an up-move = strong buying conviction. High volume on a down-move = heavy selling distribution. Low volume = weak signal.' },
                  { key: 'sma20', always: true, label: 'SMA 20 (ref)', color: '#f59e0b',
                    description: "Short-term 20-day moving average shown as a horizontal reference line at today's value. Price above = near-term uptrend; below = near-term weakness." },
                  { key: 'support', always: true, label: 'Support Levels (S)', color: isDark ? '#00ffa3' : '#16a34a',
                    description: 'Price floors identified from the last 3 months using local price minima. Historically where buyers stepped in — expect potential bounce or consolidation when revisited.' },
                  { key: 'resistance', always: true, label: 'Resistance Levels (R)', color: isDark ? '#ff0055' : '#dc2626',
                    description: 'Price ceilings identified from the last 3 months using local price maxima. Historically where sellers emerged — expect potential rejection or slowdown on approach.' },
                ] as { key: string; always: boolean; label: string; color: string; color2?: string; description: string }[])
                  .filter(item => item.always || indicators.includes(item.key as IndicatorKey))
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
            </Box>
          </Collapse>
        </Box>

        {/* AdvancedChart (PRO) only works for 2Y — its buildTimestamps parses MM/DD strings
            which is the format prediction.history uses. Interval bars use different formats. */}
        {chartEngine === 'pro' && selectedInterval === '2y' ? (
          <AdvancedChart
            history={activeHistory}
            forecast={prediction.forecastDays}
            rsiSeries={prediction.indicators?.rsi_series ?? []}
            indicators={indicators}
            mode={chartMode}
            isDark={isDark}
            primaryColor={primaryColor}
            trendColor={trendColor}
            support={prediction.indicators?.support ?? []}
            resistance={prediction.indicators?.resistance ?? []}
          />
        ) : (<>
          {/* Main price + overlay chart */}
          <Box sx={{ display: 'flex', gap: 1, minWidth: 0, position: 'relative' }}>
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
            <Box ref={chartBoxRef} sx={{ height: 380, position: 'relative', flex: 1, minWidth: 0 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={(chartMode === 'line' ? chartData : candleChartData) as ChartEntry[]} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                  <defs>
                    <linearGradient id="histGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={trendColor} stopOpacity={0.35} />
                      <stop offset="95%" stopColor={trendColor} stopOpacity={0}    />
                    </linearGradient>
                    <linearGradient id="foreGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#bc13fe" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#bc13fe" stopOpacity={0}    />
                    </linearGradient>
                    <linearGradient id="bbGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={primaryColor} stopOpacity={0.08} />
                      <stop offset="95%" stopColor={primaryColor} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>

                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.1)" vertical={false} />
                  <XAxis dataKey="date" stroke="rgba(128,128,128,0.2)" tick={{ fill: 'rgba(128,128,128,0.5)', fontSize: 10 }} tickLine={false} axisLine={false} />
                  <YAxis domain={chartDomain} stroke="rgba(128,128,128,0.2)" tick={{ fill: 'rgba(128,128,128,0.5)', fontSize: 10 }} tickLine={false} axisLine={false} width={65}
                    tickFormatter={(v: number) => v >= 1000 ? `$${(v/1000).toFixed(1)}k` : v >= 1 ? `$${v.toFixed(1)}` : `$${v.toFixed(4)}`}
                  />
                  <Tooltip
                    contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}4d`, borderRadius: 10, fontSize: 12 }}
                    formatter={(value: any, name: string) => {
                      if (name === 'bb_band' || name === 'fore_band') return null;
                      const v = Number(value);
                      const fmt = v >= 1000 ? `$${(v / 1000).toFixed(1)}k`
                                : v >= 1    ? `$${v.toFixed(2)}`
                                :             `$${v.toFixed(4)}`;
                      return [fmt, SERIES_LABEL_MAP[name] ?? name];
                    }}
                    labelStyle={{ opacity: 0.5, fontSize: 11 }}
                  />
                  <Legend wrapperStyle={{ fontSize: '0.65rem', opacity: 0.6, paddingTop: 8 }}
                    formatter={(value) => SERIES_LABEL_MAP[value] ?? value}
                  />

                  {activeStats?.sma20 != null && Number.isFinite(activeStats.sma20) && (
                    <ReferenceLine y={activeStats.sma20} stroke="#f59e0b" strokeDasharray="4 4" strokeOpacity={0.5}
                      label={{ value: `SMA20 $${Number(activeStats.sma20).toFixed(2)}`, fill: '#f59e0b', fontSize: 9, position: 'insideTopRight' }}
                    />
                  )}

                  {(prediction.indicators?.support ?? []).map((lvl, i) => (
                    <ReferenceLine key={`sup-${i}`} y={lvl} stroke="#00ffa3" strokeDasharray="6 3" strokeOpacity={0.7} strokeWidth={1.2}
                      label={{ value: `S $${lvl}`, fill: '#00ffa3', fontSize: 9, position: 'insideBottomRight' }}
                    />
                  ))}

                  {(prediction.indicators?.resistance ?? []).map((lvl, i) => (
                    <ReferenceLine key={`res-${i}`} y={lvl} stroke="#ff0055" strokeDasharray="6 3" strokeOpacity={0.7} strokeWidth={1.2}
                      label={{ value: `R $${lvl}`, fill: '#ff0055', fontSize: 9, position: 'insideTopRight' }}
                    />
                  ))}

                  {/* Event markers — large moves / volume spikes */}
                  {eventMarkers.map((ev, i) => {
                    const color  = ev.type === 'up' ? '#00ffa3' : ev.type === 'down' ? '#ff0055' : '#f59e0b';
                    const symbol = ev.type === 'up' ? '▲' : ev.type === 'down' ? '▼' : '◆';
                    // Stagger label y so clustered markers don't collide
                    const yOffset = 8 + (i % 3) * 14;
                    return (
                      <ReferenceLine
                        key={`ev-${i}`}
                        x={ev.date}
                        stroke={color}
                        strokeWidth={1}
                        strokeOpacity={0.4}
                        strokeDasharray="2 4"
                        label={({ viewBox }: any) => {
                          const { x, y } = viewBox;
                          return (
                            <text
                              x={x + 3}
                              y={(y ?? 0) + yOffset}
                              fill={color}
                              fontSize={8}
                              opacity={0.9}
                              style={{ pointerEvents: 'none', userSelect: 'none' }}
                            >
                              {symbol}{ev.label}
                            </text>
                          );
                        }}
                      />
                    );
                  })}

                  {/* Earnings date markers */}
                  {(prediction.earningsDates ?? []).map((d, i) => (
                    <ReferenceLine
                      key={`earn-${i}`}
                      x={d}
                      stroke="#facc15"
                      strokeWidth={1.5}
                      strokeDasharray="3 3"
                      strokeOpacity={0.8}
                      label={({ viewBox }: any) => {
                        const { x, y } = viewBox;
                        return (
                          <text x={x + 3} y={(y ?? 0) + 10} fill="#facc15" fontSize={8} opacity={0.9}
                            style={{ pointerEvents: 'none', userSelect: 'none' }}>
                            📅E
                          </text>
                        );
                      }}
                    />
                  ))}

                  {indicators.includes('bb') && <>
                    <Line  type="monotone" dataKey="bb_lower"  stroke={primaryColor} strokeWidth={1} strokeDasharray="3 2" strokeOpacity={0.5} dot={false} connectNulls isAnimationActive={false} />
                    <Line  type="monotone" dataKey="bb_upper"  stroke={primaryColor} strokeWidth={1} strokeDasharray="3 2" strokeOpacity={0.5} dot={false} connectNulls isAnimationActive={false} />
                    <Line  type="monotone" dataKey="bb_middle" stroke={primaryColor} strokeWidth={1} strokeDasharray="5 3" strokeOpacity={0.4} dot={false} connectNulls isAnimationActive={false} />
                  </>}

                  {indicators.includes('sma') && <>
                    <Line type="monotone" dataKey="sma50"  stroke="#f97316" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="sma200" stroke="#a855f7" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                  </>}

                  {indicators.includes('ema') && <>
                    <Line type="monotone" dataKey="ema20" stroke="#06b6d4" strokeWidth={1.5} strokeDasharray="4 2" dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="ema50" stroke="#f43f5e" strokeWidth={1.5} strokeDasharray="4 2" dot={false} connectNulls isAnimationActive={false} />
                  </>}

                  {/* VWAP — present for all intraday intervals (1d/5d/1m) */}
                  {(selectedInterval === '1d' || selectedInterval === '5d' || selectedInterval === '1m') && intervalData && (
                    <Line type="monotone" dataKey="vwap" stroke="#facc15" strokeWidth={1.5} strokeDasharray="6 2" dot={false} connectNulls isAnimationActive={false} />
                  )}

                  {chartMode === 'line' && (
                    <Area type="monotone" dataKey="price" stroke={trendColor} strokeWidth={2.5} fill="url(#histGrad)" dot={false} connectNulls={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
                  )}

                  <Line type="monotone" dataKey="foreLow"  stroke="rgba(188,19,254,0.4)" strokeWidth={1}   strokeDasharray="5 3" dot={false} connectNulls={false} isAnimationActive={false} legendType="none" />
                  <Line type="monotone" dataKey="foreHigh" stroke="rgba(188,19,254,0.5)" strokeWidth={1.5} strokeDasharray="5 3" dot={false} connectNulls={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="predicted" stroke="#bc13fe" strokeWidth={2} strokeDasharray="6 3"
                    dot={{ r: 4, fill: '#bc13fe', strokeWidth: 0 }} connectNulls={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>

              {/* Candlestick SVG overlay */}
              {chartMode === 'candle' && chartDomain[0] !== 'auto' && (() => {
                const plotL = clipBox?.l ?? 0;
                const plotT = clipBox?.t ?? 0;
                const plotW = clipBox?.w ?? 0;
                const plotH = clipBox?.h ?? 0;
                if (!plotW || !plotH) return null;
                const [dMin, dMax] = chartDomain as [number, number];
                const pRange  = dMax - dMin;
                const total   = candleChartData.length;
                const slotW   = plotW / total;
                const toY = (p: number) => plotT + (1 - (p - dMin) / pRange) * plotH;
                const toX = (i: number) => plotL + (i + 0.5) * slotW;
                return (
                  <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: CHART_HEIGHT, pointerEvents: 'none' }}>
                    {candleChartData.map((d: any, i: number) => {
                      if (d.close == null || d.open == null) return null;
                      const isUp  = d.close >= d.open;
                      const color = isUp ? '#00ffa3' : '#ff0055';
                      const cx    = toX(i);
                      const hw    = Math.max(slotW * 0.38, 1);
                      const yO    = toY(d.open);
                      const yC    = toY(d.close);
                      return (
                        <g key={i}>
                          <line x1={cx} y1={toY(d.high)} x2={cx} y2={toY(d.low)} stroke={color} strokeWidth={1} opacity={0.75} />
                          <rect x={cx - hw} y={Math.min(yO, yC)} width={hw * 2} height={Math.max(Math.abs(yC - yO), 1)}
                            fill={isUp ? 'transparent' : color} stroke={color} strokeWidth={1.2} />
                        </g>
                      );
                    })}
                  </svg>
                );
              })()}
            </Box>
            <VolumeProfile history={activeHistory.map(h => ({ price: h.price, high: h.high, low: h.low, volume: h.volume }))} isDark={isDark} height={380} />
          </Box>

          {/* MACD sub-chart */}
          {indicators.includes('macd') && macdData.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" sx={{ opacity: 0.4, letterSpacing: 2, display: 'block', mb: 1 }}>MACD (12, 26, 9)</Typography>
              <Box sx={{ height: 120 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={macdData} margin={{ top: 0, right: 10, bottom: 0, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.08)" vertical={false} />
                    <XAxis dataKey="date" hide />
                    <YAxis width={45} tick={{ fill: 'rgba(128,128,128,0.4)', fontSize: 9 }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}33`, borderRadius: 8, fontSize: 11 }}
                      formatter={(v: any, name: string) => [Number(v).toFixed(3), name === 'hist' ? 'Histogram' : name === 'macd' ? 'MACD' : 'Signal']} />
                    <Bar dataKey="hist" isAnimationActive={false}>
                      {macdData.map((entry, i) => (
                        <Cell key={i} fill={(entry.hist ?? 0) >= 0 ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626')} fillOpacity={0.7} />
                      ))}
                    </Bar>
                    <Line type="monotone" dataKey="macd"   stroke={primaryColor} strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="signal" stroke="#f59e0b"      strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </Box>
            </Box>
          )}

          {/* RSI sub-chart */}
          {indicators.includes('rsi') && rsiData.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" sx={{ opacity: 0.4, letterSpacing: 2, display: 'block', mb: 1 }}>RSI (14)</Typography>
              <Box sx={{ height: 100 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={rsiData} margin={{ top: 0, right: 10, bottom: 0, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.08)" vertical={false} />
                    <XAxis dataKey="date" hide />
                    <YAxis domain={[0, 100]} width={30} tick={{ fill: 'rgba(128,128,128,0.4)', fontSize: 9 }} tickLine={false} axisLine={false} ticks={[30, 50, 70]} />
                    <Tooltip contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}33`, borderRadius: 8, fontSize: 11 }}
                      formatter={(v: any) => [Number(v).toFixed(1), 'RSI']} />
                    <ReferenceLine y={70} stroke={isDark ? '#ff0055' : '#dc2626'} strokeDasharray="4 3" strokeOpacity={0.5} />
                    <ReferenceLine y={30} stroke={isDark ? '#00ffa3' : '#16a34a'} strokeDasharray="4 3" strokeOpacity={0.5} />
                    <ReferenceLine y={50} stroke="rgba(128,128,128,0.2)" />
                    <Area type="monotone" dataKey="rsi" stroke="#bc13fe" strokeWidth={2} fill="#bc13fe" fillOpacity={0.1} dot={false} connectNulls isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </Box>
            </Box>
          )}

          {/* Volume sub-chart */}
          {indicators.includes('volume') && volumeData.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" sx={{ opacity: 0.4, letterSpacing: 2, display: 'block', mb: 1 }}>VOLUME</Typography>
              <Box sx={{ height: 80 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={volumeData} margin={{ top: 0, right: 10, bottom: 0, left: 10 }}>
                    <XAxis dataKey="date" hide />
                    <YAxis width={45} tick={{ fill: 'rgba(128,128,128,0.4)', fontSize: 9 }} tickLine={false} axisLine={false}
                      tickFormatter={(v: number) => v >= 1e9 ? `${(v/1e9).toFixed(1)}B` : v >= 1e6 ? `${(v/1e6).toFixed(0)}M` : `${v}`}
                    />
                    <Tooltip contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}33`, borderRadius: 8, fontSize: 11 }}
                      formatter={(v: any) => [Number(v).toLocaleString(), 'Volume']} />
                    <Bar dataKey="volume" fill={primaryColor} fillOpacity={0.4} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </Box>
          )}
        </>)}
      </CardContent>
    </Card>
  );
}
