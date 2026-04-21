"use client";

import React, { useState, useMemo, useRef } from 'react';
import axios from 'axios';
import {
  Box, Container, Typography, TextField, Button, Card, CardContent,
  Grid, Divider, CircularProgress, Alert, ThemeProvider, createTheme,
  CssBaseline, Paper, Chip, Stack, MenuItem, Select, Avatar, Link,
  Skeleton, ToggleButton, ToggleButtonGroup, IconButton, Autocomplete, Collapse,
} from '@mui/material';
import {
  Search, BrainCircuit, Newspaper, BarChart2, Sun, Moon,
  Info, ChevronDown, ChevronUp, Scale,
} from 'lucide-react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, ComposedChart, Area, Legend,
  BarChart, Bar, Cell,
} from 'recharts';
import dynamic from 'next/dynamic';
// ssr:false prevents Next.js from evaluating lightweight-charts on the server
// (the library calls document/window at module level, which fails in Node.js).
const AdvancedChart = dynamic(() => import('../components/AdvancedChart'), { ssr: false });
import VolumeProfile    from '../components/VolumeProfile';
import ModelWeightBar   from '../components/ModelWeightBar';
import TrendingSparklines from '../components/TrendingSparklines';

// ── Types ────────────────────────────────────────────────────────────────────

interface ForecastDay {
  date:           string;
  predicted:      number;
  high:           number;
  low:            number;
  confidence_pct: number;
}

interface ModelStats {
  ann_volatility_pct: number;
  trend_slope:        number;
  sma_20:             number;
  price_vs_sma20_pct: number;
}

interface HistoryPoint {
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

interface AnalystJuror {
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

interface PredictionData {
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
  lastUpdated: string;
}

type ChartEntry = Record<string, string | number | undefined>;

// ── Theme factory ─────────────────────────────────────────────────────────────

function buildTheme(mode: 'dark' | 'light') {
  return createTheme({
    palette: {
      mode,
      primary:   { main: mode === 'dark' ? '#00f2ff' : '#0077ff' },
      secondary: { main: mode === 'dark' ? '#bc13fe' : '#7c3aed' },
      success:   { main: mode === 'dark' ? '#00ffa3' : '#16a34a' },
      error:     { main: mode === 'dark' ? '#ff0055' : '#dc2626' },
      background: {
        default: mode === 'dark' ? '#050a10' : '#f0f4f8',
        paper:   mode === 'dark' ? '#0d1520' : '#ffffff',
      },
    },
    typography: {
      fontFamily: '"Inter", "Roboto", sans-serif',
      h1: { fontWeight: 900, letterSpacing: '-0.05em' },
      h2: { fontWeight: 800, letterSpacing: '-0.03em' },
      h4: { fontWeight: 700 },
    },
    shape: { borderRadius: 12 },
    components: {
      MuiCard: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            border: mode === 'dark'
              ? '1px solid rgba(0, 242, 255, 0.1)'
              : '1px solid rgba(0, 119, 255, 0.15)',
            transition: 'all 0.3s ease',
            '&:hover': {
              border: mode === 'dark'
                ? '1px solid rgba(0, 242, 255, 0.3)'
                : '1px solid rgba(0, 119, 255, 0.4)',
            },
          },
        },
      },
    },
  });
}

// ── Constants ─────────────────────────────────────────────────────────────────

const EXCHANGES = [
  { value: '',       label: 'Auto'         },
  { value: 'NASDAQ', label: 'NASDAQ'       },
  { value: 'NYSE',   label: 'NYSE'         },
  { value: 'LSE',    label: 'London (LSE)' },
  { value: 'FRA',    label: 'Frankfurt'    },
];

const POPULAR_TICKERS = [
  'AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK.B','JPM','V',
  'UNH','MA','XOM','LLY','JNJ','PG','HD','MRK','AVGO','CVX',
  'KO','PEP','ABBV','COST','MCD','CSCO','TMO','WMT','ACN','ABT',
  'SPY','QQQ','DIA','IWM','GLD','SLV','TLT','BTC-USD','ETH-USD',
];

type IndicatorKey = 'bb' | 'sma' | 'macd' | 'rsi' | 'volume';

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfidenceBadge({ pct }: { pct: number }) {
  const color = pct >= 70 ? '#00ffa3' : pct >= 50 ? '#00f2ff' : '#f59e0b';
  return (
    <Box sx={{
      display: 'inline-flex', alignItems: 'center', gap: 0.5,
      px: 1, py: 0.25, borderRadius: 1,
      border: `1px solid ${color}44`, background: `${color}11`,
    }}>
      <Box sx={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color }}>{pct}%</Typography>
    </Box>
  );
}

// ── Rating colour map ─────────────────────────────────────────────────────────

const RATING_COLORS: Record<string, { bg: string; text: string }> = {
  // Standard equity ratings
  'Strong Buy':  { bg: '#00ffa322', text: '#00ffa3' },
  'Buy':         { bg: '#00f2ff22', text: '#00f2ff' },
  'Accumulate':  { bg: '#00f2ff18', text: '#00d4e0' },
  'Hold':        { bg: '#f59e0b22', text: '#f59e0b' },
  'Distribute':  { bg: '#f9731618', text: '#fb923c' },
  'Sell':        { bg: '#f9731622', text: '#f97316' },
  'Strong Sell': { bg: '#ff005522', text: '#ff0055' },
  // Risk ratings (xAI Grok macro lens)
  'Low Risk':    { bg: '#00ffa322', text: '#00ffa3' },
  'Medium Risk': { bg: '#f59e0b22', text: '#f59e0b' },
  'High Risk':   { bg: '#ff005522', text: '#ff0055' },
};

// ── Analyst Jury Panel ────────────────────────────────────────────────────────

// Ordered most-bullish → most-bearish across all 3 persona rating vocabularies
const RATING_ORDER = [
  'Strong Buy', 'Buy', 'Accumulate', 'Low Risk',
  'Hold', 'Medium Risk',
  'Distribute', 'Sell', 'High Risk', 'Strong Sell',
];

function AnalystJuryPanel({ analysts }: { analysts: AnalystJuror[] }) {
  const ratingColor = (r: string) => RATING_COLORS[r] ?? { bg: '#64748b22', text: '#94a3b8' };

  // Consensus: first rating in RATING_ORDER that any analyst gave (majority-weighted)
  const ratingCounts = analysts.reduce((acc, a) => {
    acc[a.rating] = (acc[a.rating] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
  const consensus = RATING_ORDER.find(r => ratingCounts[r]) ?? analysts[0]?.rating ?? 'Hold';
  const avgConf   = Math.round(analysts.reduce((s, a) => s + a.confidence, 0) / Math.max(analysts.length, 1));
  const divergent = new Set(analysts.map(a => a.rating)).size > 1;

  return (
    <Stack spacing={1.5}>
      {/* Panel header — title left, consensus pill right */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 0.5 }}>
        <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1, fontSize: '1rem' }}>
          <Scale size={18} /> Analyst Jury
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          {divergent && (
            <Typography sx={{ fontSize: '0.58rem', opacity: 0.3, letterSpacing: '0.07em' }}>SPLIT</Typography>
          )}
          <Box sx={{
            px: 1.2, py: 0.3, borderRadius: 1,
            background: ratingColor(consensus).bg,
            border: `1px solid ${ratingColor(consensus).text}44`,
            display: 'flex', alignItems: 'center', gap: 0.6,
          }}>
            <Typography sx={{ fontSize: '0.62rem', fontWeight: 900, color: ratingColor(consensus).text, letterSpacing: '0.07em' }}>
              {consensus.toUpperCase()}
            </Typography>
            <Typography sx={{ fontSize: '0.56rem', opacity: 0.55, color: ratingColor(consensus).text }}>
              {avgConf}%
            </Typography>
          </Box>
        </Box>
      </Box>

      {/* Analyst cards */}
      <Grid container spacing={1.5}>
        {analysts.map((analyst) => {
          const rc = ratingColor(analyst.rating);
          return (
            <Grid size={{ xs: 12, sm: 4 }} key={analyst.id}>
              <Card sx={{
                height: '100%',
                borderLeft: `3px solid ${analyst.color}66`,
                background: `linear-gradient(135deg, ${analyst.color}06 0%, transparent 55%)`,
              }}>
                <CardContent sx={{ p: '14px !important', display: 'flex', flexDirection: 'column', gap: 1.2 }}>

                  {/* Single-row header: avatar | id+model | rating+conf */}
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                    {/* Avatar */}
                    <Box sx={{
                      width: 34, height: 34, borderRadius: '8px', flexShrink: 0,
                      background: `${analyst.color}14`,
                      border: `1.5px solid ${analyst.color}40`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Typography sx={{
                        fontSize: '0.52rem', fontWeight: 900, color: analyst.color,
                        letterSpacing: '0.03em', lineHeight: 1, fontFamily: 'monospace',
                      }}>
                        {analyst.avatar}
                      </Typography>
                    </Box>

                    {/* ID + lens + model label */}
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{
                        fontSize: '0.78rem', fontWeight: 900, lineHeight: 1.15,
                        fontFamily: 'monospace', color: analyst.color,
                      }}>
                        {analyst.id}
                      </Typography>
                      <Typography sx={{ fontSize: '0.56rem', opacity: 0.5, lineHeight: 1.2 }}>
                        {analyst.title}
                      </Typography>
                      <Typography sx={{ fontSize: '0.5rem', opacity: 0.28, lineHeight: 1.2, fontFamily: 'monospace' }}>
                        {analyst.model_label}
                      </Typography>
                    </Box>

                    {/* Rating chip + confidence — stacked right */}
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.4, flexShrink: 0 }}>
                      <Box sx={{
                        px: 1, py: 0.25, borderRadius: 0.75,
                        background: rc.bg, border: `1px solid ${rc.text}55`,
                      }}>
                        <Typography sx={{ fontSize: '0.6rem', fontWeight: 900, color: rc.text, letterSpacing: '0.07em', whiteSpace: 'nowrap' }}>
                          {analyst.rating.toUpperCase()}
                        </Typography>
                      </Box>
                      <Typography sx={{ fontSize: '0.54rem', opacity: 0.35, fontFamily: 'monospace' }}>
                        {analyst.confidence}% conf
                      </Typography>
                    </Box>
                  </Box>

                  {/* Subtle divider */}
                  <Box sx={{ height: '1px', background: `${analyst.color}18` }} />

                  {/* Advisory note */}
                  <Typography sx={{ fontSize: '0.8rem', lineHeight: 1.65, opacity: 0.85, flex: 1 }}>
                    {analyst.note}
                  </Typography>

                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    </Stack>
  );
}

// ── Loading skeleton card ─────────────────────────────────────────────────────

function ChartSkeleton() {
  return (
    <Card>
      <CardContent sx={{ p: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
          <Box>
            <Skeleton variant="text" width={120} height={48} />
            <Skeleton variant="text" width={180} height={24} />
          </Box>
          <Box sx={{ textAlign: 'right' }}>
            <Skeleton variant="text" width={100} height={48} />
            <Skeleton variant="text" width={80} height={20} />
          </Box>
        </Box>
        <Stack direction="row" spacing={3} sx={{ mb: 3 }}>
          {[1,2,3,4,5,6].map(i => (
            <Box key={i}><Skeleton variant="text" width={60} height={14} /><Skeleton variant="text" width={70} height={22} /></Box>
          ))}
        </Stack>
        <Skeleton variant="rectangular" height={420} sx={{ borderRadius: 2 }} />
      </CardContent>
    </Card>
  );
}

function SidebarSkeleton() {
  return (
    <Stack spacing={3}>
      <Card><CardContent>
        <Skeleton variant="text" width="60%" height={20} />
        <Skeleton variant="rectangular" height={140} sx={{ mt: 2, borderRadius: 2 }} />
        <Skeleton variant="text" width="90%" height={16} sx={{ mt: 2 }} />
        <Skeleton variant="text" width="80%" height={16} />
      </CardContent></Card>
      <Card><CardContent>
        <Skeleton variant="text" width="50%" height={20} />
        <Grid container spacing={2} sx={{ mt: 1 }}>
          {[1,2,3,4,5,6,7,8].map(i => (
            <Grid size={6} key={i}>
              <Skeleton variant="text" width="80%" height={14} />
              <Skeleton variant="text" width="60%" height={22} />
            </Grid>
          ))}
        </Grid>
      </CardContent></Card>
    </Stack>
  );
}

// Chart layout constants — must match ComposedChart margin + YAxis width
const CHART_HEIGHT   = 380;

// ── Main dashboard ────────────────────────────────────────────────────────────

export default function QuantumDashboard() {
  const [themeMode,   setThemeMode]   = useState<'dark' | 'light'>('dark');
  const [ticker,      setTicker]      = useState('NVDA');
  const [exchange,    setExchange]    = useState('');
  const [prediction,  setPrediction]  = useState<PredictionData | null>(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState<string | null>(null);
  const [indicators,  setIndicators]  = useState<IndicatorKey[]>(['bb', 'sma']);
  const [chartMode,   setChartMode]   = useState<'line' | 'candle'>('line');
  const [chartEngine, setChartEngine] = useState<'classic' | 'pro'>('classic');
  const [legendOpen,  setLegendOpen]  = useState(false);
  const chartBoxRef = useRef<HTMLDivElement>(null);

  const theme = useMemo(() => buildTheme(themeMode), [themeMode]);
  const isDark = themeMode === 'dark';

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      const fullSymbol = exchange ? `${ticker}:${exchange}` : ticker;
      const response   = await axios.post('/api/predict', { data: fullSymbol });
      setPrediction(response.data);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Quantum analysis failed.');
    } finally {
      setLoading(false);
    }
  };

  const rsiInfo = useMemo(() => {
    if (!prediction) return null;
    const val = parseFloat(prediction.rsi);
    if (val >= 70) return { label: 'Overbought', color: 'error'   as const };
    if (val <= 30) return { label: 'Oversold',   color: 'success' as const };
    return            { label: 'Neutral',     color: 'primary' as const };
  }, [prediction]);

  const chartData = useMemo(() => {
    if (!prediction) return [];
    const hist = prediction.history.map(h => ({
      date:       h.date,
      price:      h.price,
      bb_upper:   h.bb_upper   ?? undefined,
      bb_middle:  h.bb_middle  ?? undefined,
      bb_lower:   h.bb_lower   ?? undefined,
      sma50:      h.sma50      ?? undefined,
      sma200:     h.sma200     ?? undefined,
      predicted:  undefined as number | undefined,
      foreHigh:   undefined as number | undefined,
      foreLow:    undefined as number | undefined,
    }));
    const fore = (prediction.forecastDays || []).map(f => ({
      date:      f.date,
      price:     undefined as number | undefined,
      bb_upper:  undefined, bb_middle: undefined, bb_lower: undefined,
      sma50:     undefined, sma200:    undefined,
      predicted: f.predicted,
      foreHigh:  f.high,
      foreLow:   f.low,
    }));
    return [...hist, ...fore];
  }, [prediction]);

  const macdData = useMemo(() => {
    if (!prediction) return [];
    return prediction.history.map(h => ({
      date:   h.date,
      macd:   h.macd   ?? null,
      signal: h.macd_signal ?? null,
      hist:   h.macd_hist   ?? null,
    }));
  }, [prediction]);

  const rsiData = useMemo(() => {
    if (!prediction) return [];
    const rsiSeries = prediction.indicators?.rsi_series ?? [];
    return prediction.history.map((h, i) => ({
      date: h.date,
      rsi:  rsiSeries[i] ?? null,
    }));
  }, [prediction]);

  const volumeData = useMemo(() => {
    if (!prediction) return [];
    return prediction.history.map(h => ({
      date:   h.date,
      volume: h.volume ?? 0,
    }));
  }, [prediction]);

  const candleChartData = useMemo(() => {
    if (!prediction) return [];
    const hist = prediction.history.map(h => ({
      date:       h.date,
      open:       h.open  ?? h.price,
      high:       h.high  ?? h.price,
      low:        h.low   ?? h.price,
      close:      h.price,
      bb_upper:   h.bb_upper  ?? undefined,
      bb_middle:  h.bb_middle ?? undefined,
      bb_lower:   h.bb_lower  ?? undefined,
      sma50:      h.sma50     ?? undefined,
      sma200:     h.sma200    ?? undefined,
      predicted:  undefined as number | undefined,
      foreHigh:   undefined as number | undefined,
      foreLow:    undefined as number | undefined,
    }));
    const fore = (prediction.forecastDays || []).map(f => ({
      date: f.date, open: undefined as number | undefined,
      high: undefined as number | undefined, low: undefined as number | undefined,
      close: undefined as number | undefined,
      bb_upper: undefined, bb_middle: undefined, bb_lower: undefined,
      sma50: undefined, sma200: undefined,
      predicted: f.predicted, foreHigh: f.high, foreLow: f.low,
    }));
    return [...hist, ...fore];
  }, [prediction]);

  const chartDomain = useMemo((): [number, number] | ['auto', 'auto'] => {
    const data = chartMode === 'line' ? chartData : candleChartData;
    if (!data.length) return ['auto', 'auto'];
    const allVals = data.flatMap(d => [
      (d as any).price,  (d as any).predicted, (d as any).foreHigh, (d as any).foreLow,
      (d as any).open,   (d as any).high,       (d as any).low,      (d as any).close,
      indicators.includes('bb') ? (d as any).bb_upper : undefined,
      indicators.includes('bb') ? (d as any).bb_lower : undefined,
    ].filter((v): v is number => v !== undefined && v !== null));
    if (!allVals.length) return ['auto', 'auto'];
    const min = Math.min(...allVals);
    const max = Math.max(...allVals);
    const pad = (max - min) * 0.12 || max * 0.02;
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [chartData, candleChartData, chartMode, indicators]);

  const chartStats = useMemo(() => {
    if (!prediction?.history?.length) return null;
    const prices = prediction.history.map(h => h.price);
    const first  = prices[0];
    const last   = prices[prices.length - 1];
    const change    = last - first;
    const changePct = first > 0 ? (change / first) * 100 : 0;
    const isUp      = change >= 0;
    return {
      open: first, change, changePct,
      high: Math.max(...prices),
      low:  Math.min(...prices),
      isUp,
      color: isUp ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626'),
    };
  }, [prediction?.history, isDark]);

  const trendColor   = chartStats?.color ?? (isDark ? '#00f2ff' : '#0077ff');
  const primaryColor = isDark ? '#00f2ff' : '#0077ff';

  /** Live signal texts derived from the most-recent data point */
  const indicatorSignals = useMemo(() => {
    if (!prediction) return {} as Record<string, { text: string; color: string } | null>;
    const last    = prediction.history[prediction.history.length - 1];
    const price   = last?.price ?? 0;
    const rsiVal  = parseFloat(prediction.rsi);
    const supports    = prediction.indicators?.support    ?? [];
    const resistances = prediction.indicators?.resistance ?? [];
    const sma20       = prediction.modelStats?.sma_20;
    const vsPct       = prediction.modelStats?.price_vs_sma20_pct;

    const green = isDark ? '#00ffa3' : '#16a34a';
    const red   = isDark ? '#ff0055' : '#dc2626';
    const amber = '#f59e0b';
    const blue  = isDark ? '#00f2ff' : '#0077ff';

    const bbUpper  = last?.bb_upper  ?? null;
    const bbLower  = last?.bb_lower  ?? null;
    const bbMiddle = last?.bb_middle ?? null;

    const sma50  = last?.sma50  ?? null;
    const sma200 = last?.sma200 ?? null;

    // Find MACD cross on last 2 points
    const h = prediction.history;
    const macdPrev  = h.length >= 2 ? (h[h.length - 2]?.macd   ?? null) : null;
    const sigPrev   = h.length >= 2 ? (h[h.length - 2]?.macd_signal ?? null) : null;
    const macdNow   = last?.macd        ?? null;
    const sigNow    = last?.macd_signal ?? null;
    const histNow   = last?.macd_hist   ?? null;

    // Volume vs 20-period avg
    const vols = prediction.history.slice(-21, -1).map(p => p.volume ?? 0);
    const avgVol  = vols.length ? vols.reduce((a, b) => a + b, 0) / vols.length : 0;
    const lastVol = last?.volume ?? 0;

    return {
      bb: (() => {
        if (!bbUpper || !bbLower) return null;
        if (price >= bbUpper * 0.99) return { text: 'Price touching upper band → overbought risk', color: red };
        if (price <= bbLower * 1.01) return { text: 'Price touching lower band → oversold opportunity', color: green };
        if (bbMiddle && price > bbMiddle) return { text: 'Price above midline → mild bullish bias', color: green };
        return { text: 'Price below midline → mild bearish bias', color: amber };
      })(),
      sma: (() => {
        if (!sma50 || !sma200) return null;
        const cross = sma50 > sma200;
        const priceAbove50  = price > sma50;
        const priceAbove200 = price > sma200;
        if (cross && priceAbove50) return { text: `Golden cross active (SMA50 > SMA200). Price above both → strong uptrend`, color: green };
        if (!cross && !priceAbove200) return { text: `Death cross active (SMA50 < SMA200). Price below both → strong downtrend`, color: red };
        if (priceAbove50 && !cross) return { text: `Price above SMA50 but SMA50 < SMA200 → short-term recovery in downtrend`, color: amber };
        return { text: `Price below SMA50 but above SMA200 → near-term weakness in uptrend`, color: amber };
      })(),
      macd: (() => {
        if (macdNow == null || sigNow == null) return null;
        const justCrossedUp   = macdPrev != null && sigPrev != null && macdPrev < sigPrev && macdNow >= sigNow;
        const justCrossedDown = macdPrev != null && sigPrev != null && macdPrev > sigPrev && macdNow <= sigNow;
        if (justCrossedUp)   return { text: 'Bullish crossover — MACD just crossed above signal line', color: green };
        if (justCrossedDown) return { text: 'Bearish crossover — MACD just crossed below signal line', color: red };
        if (macdNow > sigNow && (histNow ?? 0) > 0) return { text: 'MACD above signal & histogram growing → bullish momentum', color: green };
        if (macdNow < sigNow && (histNow ?? 0) < 0) return { text: 'MACD below signal & histogram shrinking → bearish momentum', color: red };
        return { text: 'Consolidating — no strong directional signal', color: amber };
      })(),
      rsi: (() => {
        if (isNaN(rsiVal)) return null;
        if (rsiVal >= 80) return { text: `RSI ${rsiVal.toFixed(1)} — severely overbought, reversal likely`, color: red };
        if (rsiVal >= 70) return { text: `RSI ${rsiVal.toFixed(1)} — overbought zone, caution on longs`, color: red };
        if (rsiVal <= 20) return { text: `RSI ${rsiVal.toFixed(1)} — severely oversold, potential bounce`, color: green };
        if (rsiVal <= 30) return { text: `RSI ${rsiVal.toFixed(1)} — oversold zone, watch for reversal up`, color: green };
        if (rsiVal >= 50) return { text: `RSI ${rsiVal.toFixed(1)} — above midline, bullish bias`, color: green };
        return { text: `RSI ${rsiVal.toFixed(1)} — below midline, bearish bias`, color: amber };
      })(),
      volume: (() => {
        if (!avgVol || !lastVol) return null;
        const ratio = lastVol / avgVol;
        const priceTrend = chartStats?.isUp;
        if (ratio >= 1.5 && priceTrend)  return { text: `Vol ${ratio.toFixed(1)}× above avg on up-day → strong bullish conviction`, color: green };
        if (ratio >= 1.5 && !priceTrend) return { text: `Vol ${ratio.toFixed(1)}× above avg on down-day → strong bearish distribution`, color: red };
        if (ratio < 0.6) return { text: `Vol ${ratio.toFixed(1)}× below avg → low conviction move, may reverse`, color: amber };
        return { text: `Volume near average — normal trading conditions`, color: blue };
      })(),
      sma20: (() => {
        if (!sma20 || vsPct == null) return null;
        if (vsPct > 5)  return { text: `Price ${vsPct.toFixed(1)}% above SMA20 → extended, watch for pullback`, color: amber };
        if (vsPct > 0)  return { text: `Price ${vsPct.toFixed(1)}% above SMA20 → near-term uptrend`, color: green };
        if (vsPct < -5) return { text: `Price ${Math.abs(vsPct).toFixed(1)}% below SMA20 → extended weakness`, color: red };
        return { text: `Price ${Math.abs(vsPct).toFixed(1)}% below SMA20 → near-term downtrend`, color: red };
      })(),
      support: (() => {
        if (!supports.length) return null;
        const nearest = supports.reduce((a, b) => Math.abs(a - price) < Math.abs(b - price) ? a : b);
        const distPct = ((price - nearest) / nearest * 100).toFixed(1);
        return { text: `Nearest support $${nearest} — price is ${distPct}% above. Bounce zone if tested.`, color: green };
      })(),
      resistance: (() => {
        if (!resistances.length) return null;
        const nearest = resistances.reduce((a, b) => Math.abs(a - price) < Math.abs(b - price) ? a : b);
        const distPct = ((nearest - price) / price * 100).toFixed(1);
        return { text: `Nearest resistance $${nearest} — ${distPct}% above current price. Sell pressure zone.`, color: red };
      })(),
    };
  }, [prediction, isDark, chartStats]);

  const bgGradient = isDark
    ? 'radial-gradient(circle at 50% -20%, #1a237e 0%, #050a10 60%)'
    : 'radial-gradient(circle at 50% -20%, #dbeafe 0%, #f0f4f8 60%)';

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', py: 4, px: 2, background: bgGradient }}>
        <Container maxWidth="xl">

          {/* ── Header ──────────────────────────────────────────────────── */}
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2} sx={{ mb: 6 }}>
            <Box>
              <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <BrainCircuit size={32} color={primaryColor} />
                FiForesight <Box component="span" sx={{ color: 'secondary.main' }}>QUANTUM</Box>
              </Typography>
              <Typography variant="caption" sx={{ letterSpacing: 4, color: 'primary.main', opacity: 0.8 }}>
                AI-POWERED QUANTITATIVE ENGINE
              </Typography>
            </Box>

            <Stack direction="row" spacing={1} alignItems="center">
              {/* Portfolio Race link */}
              <Button
                component="a"
                href="/simulation"
                size="small"
                variant="outlined"
                sx={{
                  borderColor: `${primaryColor}55`,
                  color: primaryColor,
                  fontSize: 12,
                  fontWeight: 700,
                  px: 1.5,
                  py: 0.5,
                  borderRadius: 2,
                  whiteSpace: 'nowrap',
                  '&:hover': { borderColor: primaryColor, background: `${primaryColor}12` },
                }}
              >
                🏁 Portfolio Race
              </Button>

              {/* Theme toggle */}
              <IconButton
                onClick={() => setThemeMode(m => m === 'dark' ? 'light' : 'dark')}
                size="small"
                sx={{ border: `1px solid ${primaryColor}33`, borderRadius: 2 }}
              >
                {isDark ? <Sun size={18} color={primaryColor} /> : <Moon size={18} color={primaryColor} />}
              </IconButton>

              {/* Search bar */}
              <Paper sx={{
                p: 0.5, display: 'flex', gap: 1, alignItems: 'center',
                width: { xs: '100%', md: 520 },
                background: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)',
                backdropFilter: 'blur(20px)', borderRadius: 4,
              }}>
                <Autocomplete
                  freeSolo
                  options={POPULAR_TICKERS}
                  value={ticker}
                  onInputChange={(_, v) => setTicker(v.toUpperCase())}
                  onChange={(_, v) => v && setTicker(String(v).toUpperCase())}
                  sx={{ flexGrow: 1 }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      placeholder="Search Ticker…"
                      variant="standard"
                      onKeyDown={e => e.key === 'Enter' && handlePredict()}
                      InputProps={{ ...params.InputProps, disableUnderline: true, sx: { px: 2, fontWeight: 700 } }}
                    />
                  )}
                />
                <Select
                  value={exchange}
                  onChange={e => setExchange(e.target.value)}
                  variant="standard"
                  disableUnderline
                  sx={{ minWidth: 100, fontWeight: 600, fontSize: '0.8rem' }}
                >
                  {EXCHANGES.map(ex => <MenuItem key={ex.value} value={ex.value}>{ex.label}</MenuItem>)}
                </Select>
                <Button
                  variant="contained"
                  onClick={handlePredict}
                  disabled={loading}
                  sx={{ borderRadius: 3, minWidth: 50, py: 1, boxShadow: `0 0 20px ${primaryColor}4d` }}
                >
                  {loading ? <CircularProgress size={20} color="inherit" /> : <Search size={20} />}
                </Button>
              </Paper>
            </Stack>
          </Stack>

          {error && <Alert severity="error" sx={{ mb: 4, borderRadius: 3 }}>{error}</Alert>}

          <Grid container spacing={3}>

            {/* ── Left column ──────────────────────────────────────────── */}
            <Grid size={{ xs: 12, lg: 8 }}>
              {loading ? (
                <Stack spacing={3}>
                  <ChartSkeleton />
                  <Skeleton variant="rectangular" height={120} sx={{ borderRadius: 2 }} />
                </Stack>
              ) : prediction ? (
                <Stack spacing={3}>

                  {/* Price chart card */}
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
                      {chartStats && (
                        <Stack direction="row" spacing={3} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
                          {[
                            { label: 'CHANGE',      val: `${chartStats.isUp ? '+' : ''}${chartStats.change.toFixed(2)} (${chartStats.isUp ? '+' : ''}${chartStats.changePct.toFixed(2)}%)`, col: trendColor },
                            { label: 'PERIOD HIGH', val: `$${chartStats.high.toFixed(2)}`, col: isDark ? '#00ffa3' : '#16a34a' },
                            { label: 'PERIOD LOW',  val: `$${chartStats.low.toFixed(2)}`,  col: isDark ? '#ff0055' : '#dc2626' },
                            { label: 'SMA 20',      val: `$${prediction.modelStats?.sma_20 ?? '—'}`, col: '#f59e0b' },
                            { label: 'ANN. VOL',    val: `${prediction.modelStats?.ann_volatility_pct ?? '—'}%`, col: 'text.secondary' },
                          ].map(s => (
                            <Box key={s.label}>
                              <Typography variant="caption" sx={{ opacity: 0.4, display: 'block', letterSpacing: 1 }}>{s.label}</Typography>
                              <Typography variant="body2" sx={{ fontWeight: 800, color: s.col }}>{s.val}</Typography>
                            </Box>
                          ))}
                        </Stack>
                      )}

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
                          { key: 'macd',   label: 'MACD'            },
                          { key: 'rsi',    label: 'RSI'             },
                          { key: 'volume', label: 'Volume'          },
                        ] as { key: IndicatorKey; label: string }[]).map(({ key, label }) => (
                          <ToggleButton key={key} value={key} sx={{ fontSize: '0.65rem', py: 0.5, px: 1.5, borderRadius: '8px !important' }}>
                            {label}
                          </ToggleButton>
                        ))}
                      </ToggleButtonGroup>

                      {/* ── Chart mode + engine toggles ─────────── */}
                      <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap' }}>
                        <ToggleButtonGroup
                          exclusive
                          aria-label="chart-mode"
                          value={chartMode}
                          onChange={(_e, val) => val && setChartMode(val)}
                          size="small"
                          sx={{ '& .MuiToggleButton-root': { fontSize: '0.65rem', fontWeight: 800, letterSpacing: 1, py: 0.4, px: 1.5, borderRadius: '6px !important', border: '1px solid rgba(128,128,128,0.2) !important', '&.Mui-selected': { background: `${primaryColor}1a`, color: primaryColor }, '&:not(.Mui-selected)': { color: 'rgba(128,128,128,0.5)' }, '&:hover': { color: primaryColor, background: `${primaryColor}0d` } } }}
                        >
                          <ToggleButton value="line">LINE</ToggleButton>
                          <ToggleButton value="candle">CANDLE</ToggleButton>
                        </ToggleButtonGroup>
                        <ToggleButtonGroup
                          exclusive
                          aria-label="chart-engine"
                          value={chartEngine}
                          onChange={(_e, val) => val && setChartEngine(val)}
                          size="small"
                          sx={{ '& .MuiToggleButton-root': { fontSize: '0.65rem', fontWeight: 800, letterSpacing: 1, py: 0.4, px: 1.5, borderRadius: '6px !important', border: '1px solid rgba(128,128,128,0.2) !important', '&.Mui-selected': { background: `${primaryColor}1a`, color: primaryColor }, '&:not(.Mui-selected)': { color: 'rgba(128,128,128,0.5)' }, '&:hover': { color: primaryColor, background: `${primaryColor}0d` } } }}
                        >
                          <ToggleButton value="classic">CLASSIC</ToggleButton>
                          <ToggleButton value="pro">PRO (ZOOM)</ToggleButton>
                        </ToggleButtonGroup>
                      </Box>

                      {/* ── Indicators Guide (collapsible) ──────────── */}
                      <Box sx={{ mb: 1 }}>
                        <Button
                          size="small"
                          variant="text"
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
                                {
                                  key: 'bb', always: false,
                                  label: 'Bollinger Bands',
                                  color: primaryColor,
                                  description: 'Volatility envelope: upper/lower = ±2 std devs from the 20-day MA. Bands widen during high volatility, narrow during consolidation.',
                                },
                                {
                                  key: 'sma', always: false,
                                  label: 'SMA 50 / SMA 200',
                                  color: '#f97316',
                                  color2: '#a855f7',
                                  description: 'Trend-following averages. SMA50 (orange) tracks medium-term, SMA200 (purple) tracks long-term. Golden cross (50 > 200) = bullish; death cross (50 < 200) = bearish.',
                                },
                                {
                                  key: 'macd', always: false,
                                  label: 'MACD (12, 26, 9)',
                                  color: isDark ? '#00f2ff' : '#0077ff',
                                  description: 'Momentum oscillator. Line crossing above signal = bullish; below = bearish. Histogram bars show momentum strength — growing bars = accelerating trend.',
                                },
                                {
                                  key: 'rsi', always: false,
                                  label: 'RSI (14)',
                                  color: '#bc13fe',
                                  description: 'Relative Strength Index: 0–100 oscillator. Above 70 = overbought (potential reversal down). Below 30 = oversold (potential reversal up). 50 is the neutral midline.',
                                },
                                {
                                  key: 'volume', always: false,
                                  label: 'Volume',
                                  color: primaryColor,
                                  description: 'Number of shares traded. High volume on an up-move = strong buying conviction. High volume on a down-move = heavy selling distribution. Low volume = weak signal.',
                                },
                                {
                                  key: 'sma20', always: true,
                                  label: 'SMA 20 (ref)',
                                  color: '#f59e0b',
                                  description: 'Short-term 20-day moving average shown as a horizontal reference line at today\'s value. Price above = near-term uptrend; below = near-term weakness.',
                                },
                                {
                                  key: 'support', always: true,
                                  label: 'Support Levels (S)',
                                  color: isDark ? '#00ffa3' : '#16a34a',
                                  description: 'Price floors identified from the last 3 months using local price minima. Historically where buyers stepped in — expect potential bounce or consolidation when revisited.',
                                },
                                {
                                  key: 'resistance', always: true,
                                  label: 'Resistance Levels (R)',
                                  color: isDark ? '#ff0055' : '#dc2626',
                                  description: 'Price ceilings identified from the last 3 months using local price maxima. Historically where sellers emerged — expect potential rejection or slowdown on approach.',
                                },
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
                                      {/* Header row */}
                                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: item.color, flexShrink: 0 }} />
                                        {item.color2 && <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: item.color2, flexShrink: 0 }} />}
                                        <Typography sx={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: 0.5 }}>{item.label}</Typography>
                                      </Box>
                                      {/* Description */}
                                      <Typography sx={{ fontSize: '0.6rem', opacity: 0.55, lineHeight: 1.5 }}>
                                        {item.description}
                                      </Typography>
                                      {/* Live signal */}
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

                      {chartEngine === 'pro' ? (
                        <AdvancedChart
                          history={prediction.history}
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
                      {/* ── Main price + overlay chart ──────────────── */}
                      <Box sx={{ display: 'flex', gap: 1 }}>
                      <Box ref={chartBoxRef} sx={{ height: 380, position: 'relative', flex: 1 }}>
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
                              tickFormatter={(v: number) => v >= 1000 ? `$${(v/1000).toFixed(1)}k` : `$${v.toFixed(0)}`}
                            />
                            <Tooltip
                              contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}4d`, borderRadius: 10, fontSize: 12 }}
                              formatter={(value: any, name: string) => {
                                const v = Number(value);
                                const map: Record<string, string> = {
                                  price: 'Close', close: 'Close (OHLC)', predicted: 'Forecast', foreHigh: 'Fore. High', foreLow: 'Fore. Low',
                                  bb_upper: 'BB Upper', bb_middle: 'BB Mid', bb_lower: 'BB Lower',
                                  sma50: 'SMA 50', sma200: 'SMA 200',
                                };
                                return [`$${v.toFixed(2)}`, map[name] ?? name];
                              }}
                              labelStyle={{ opacity: 0.5, fontSize: 11 }}
                            />
                            <Legend wrapperStyle={{ fontSize: '0.65rem', opacity: 0.6, paddingTop: 8 }}
                              formatter={(value) => {
                                const map: Record<string, string> = {
                                  price: 'Close', close: 'Close (OHLC)', predicted: 'Forecast', foreHigh: 'Fore. High', foreLow: 'Fore. Low',
                                  bb_upper: 'BB Upper', bb_middle: 'BB Mid', bb_lower: 'BB Lower',
                                  sma50: 'SMA 50', sma200: 'SMA 200',
                                };
                                return map[value] ?? value;
                              }}
                            />

                            {/* SMA 20 ref */}
                            {prediction.modelStats?.sma_20 > 0 && (
                              <ReferenceLine y={prediction.modelStats.sma_20} stroke="#f59e0b" strokeDasharray="4 4" strokeOpacity={0.5}
                                label={{ value: `SMA20 $${prediction.modelStats.sma_20}`, fill: '#f59e0b', fontSize: 9, position: 'insideTopRight' }}
                              />
                            )}

                            {/* Support levels — green dashed horizontal lines */}
                            {(prediction.indicators?.support ?? []).map((lvl, i) => (
                              <ReferenceLine key={`sup-${i}`} y={lvl} stroke="#00ffa3" strokeDasharray="6 3" strokeOpacity={0.7} strokeWidth={1.2}
                                label={{ value: `S $${lvl}`, fill: '#00ffa3', fontSize: 9, position: 'insideBottomRight' }}
                              />
                            ))}

                            {/* Resistance levels — red dashed horizontal lines */}
                            {(prediction.indicators?.resistance ?? []).map((lvl, i) => (
                              <ReferenceLine key={`res-${i}`} y={lvl} stroke="#ff0055" strokeDasharray="6 3" strokeOpacity={0.7} strokeWidth={1.2}
                                label={{ value: `R $${lvl}`, fill: '#ff0055', fontSize: 9, position: 'insideTopRight' }}
                              />
                            ))}

                            {/* Bollinger Bands */}
                            {indicators.includes('bb') && <>
                              <Area type="monotone" dataKey="bb_upper"  stroke={primaryColor} strokeWidth={1} strokeDasharray="3 2" strokeOpacity={0.5} fill="url(#bbGrad)" dot={false} connectNulls isAnimationActive={false} />
                              <Line  type="monotone" dataKey="bb_middle" stroke={primaryColor} strokeWidth={1} strokeDasharray="5 3" strokeOpacity={0.4} dot={false} connectNulls isAnimationActive={false} />
                              <Area type="monotone" dataKey="bb_lower"  stroke={primaryColor} strokeWidth={1} strokeDasharray="3 2" strokeOpacity={0.5} fill="transparent" dot={false} connectNulls isAnimationActive={false} />
                            </>}

                            {/* SMA 50 / 200 */}
                            {indicators.includes('sma') && <>
                              <Line type="monotone" dataKey="sma50"  stroke="#f97316" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                              <Line type="monotone" dataKey="sma200" stroke="#a855f7" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                            </>}

                            {/* Historical price — line mode only; candles rendered via SVG overlay */}
                            {chartMode === 'line' && (
                              <Area type="monotone" dataKey="price" stroke={trendColor} strokeWidth={2.5} fill="url(#histGrad)" dot={false} connectNulls={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
                            )}

                            {/* Forecast bands */}
                            <Area type="monotone" dataKey="foreHigh" stroke="rgba(188,19,254,0.5)" strokeWidth={1.5} strokeDasharray="5 3" fill="url(#foreGrad)" dot={false} connectNulls={false} isAnimationActive={false} />
                            <Area type="monotone" dataKey="foreLow"  stroke="rgba(188,19,254,0.3)" strokeWidth={1}   strokeDasharray="5 3" fill="transparent"    dot={false} connectNulls={false} isAnimationActive={false} />
                            <Line type="monotone" dataKey="predicted" stroke="#bc13fe" strokeWidth={2} strokeDasharray="6 3"
                              dot={{ r: 4, fill: '#bc13fe', strokeWidth: 0 }} connectNulls={false} isAnimationActive={false} />
                          </ComposedChart>
                        </ResponsiveContainer>

                        {/* ── Candlestick SVG overlay ──────────────────
                            Drawn over the Recharts canvas using known
                            chart margins + chartDomain for positioning. */}
                        {chartMode === 'candle' && chartDomain[0] !== 'auto' && (() => {
                          // Read exact plot area from Recharts-generated clipPath rect
                          const clipRect = chartBoxRef.current?.querySelector('clipPath rect');
                          const plotL = clipRect ? +clipRect.getAttribute('x')! : 0;
                          const plotT = clipRect ? +clipRect.getAttribute('y')! : 0;
                          const plotW = clipRect ? +clipRect.getAttribute('width')! : 0;
                          const plotH = clipRect ? +clipRect.getAttribute('height')! : 0;
                          if (!plotW || !plotH) return null;
                          const [dMin, dMax] = chartDomain as [number, number];
                          const pRange   = dMax - dMin;
                          const total    = candleChartData.length;
                          const slotW    = plotW / total;
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
                      <VolumeProfile history={prediction.history.map(h => ({ price: h.price, high: h.high, low: h.low, volume: h.volume }))} isDark={isDark} height={380} />
                      </Box>{/* end flex row */}

                      {/* ── MACD sub-chart ──────────────────────────── */}
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
                                <Line type="monotone" dataKey="macd"   stroke={primaryColor}   strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                                <Line type="monotone" dataKey="signal" stroke="#f59e0b" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                              </ComposedChart>
                            </ResponsiveContainer>
                          </Box>
                        </Box>
                      )}

                      {/* ── RSI sub-chart ───────────────────────────── */}
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

                      {/* ── Volume sub-chart ────────────────────────── */}
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

                  {/* ── 5-Day forecast table ──────────────────────────── */}
                  {prediction.forecastDays?.length > 0 && (
                    <Card>
                      <CardContent>
                        <Typography variant="overline" sx={{ opacity: 0.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                          <BarChart2 size={14} /> 5-Day Forecast Breakdown
                        </Typography>
                        <Box sx={{ mt: 2, display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 1.5 }}>
                          {prediction.forecastDays.map((day, i) => {
                            const isUp = day.predicted >= parseFloat(prediction.currentPrice);
                            const col  = isUp ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626');
                            return (
                              <Box key={i} sx={{
                                textAlign: 'center', p: 1.5, borderRadius: 2,
                                border: `1px solid ${col}22`, background: `${col}08`,
                              }}>
                                <Typography sx={{ fontSize: '0.65rem', opacity: 0.5, letterSpacing: 1, display: 'block' }}>
                                  DAY {i + 1} · {day.date}
                                </Typography>
                                <Typography sx={{ fontSize: '1rem', fontWeight: 800, color: col, my: 0.5 }}>
                                  ${day.predicted}
                                </Typography>
                                <Typography sx={{ fontSize: '0.6rem', color: isDark ? '#00ffa3' : '#16a34a', display: 'block' }}>↑ ${day.high}</Typography>
                                <Typography sx={{ fontSize: '0.6rem', color: isDark ? '#ff0055' : '#dc2626', display: 'block', mb: 1 }}>↓ ${day.low}</Typography>
                                <ConfidenceBadge pct={day.confidence_pct} />
                              </Box>
                            );
                          })}
                        </Box>
                      </CardContent>
                    </Card>
                  )}

                  {/* ── Ensemble Model Weights ────────────────────────────── */}
                  {prediction.modelWeights && (
                    <ModelWeightBar weights={prediction.modelWeights} isDark={isDark} />
                  )}

                  {/* ── Analyst Jury ──────────────────────────────────────── */}
                  {prediction.juryAnalysts && prediction.juryAnalysts.length > 0 && (
                    <AnalystJuryPanel analysts={prediction.juryAnalysts} />
                  )}

                  {/* ── News ─────────────────────────────────────────────── */}
                  {prediction.news?.length > 0 && (
                    <>
                      <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1 }}>
                        <Newspaper size={20} /> Market Intelligence
                      </Typography>
                      <Grid container spacing={2}>
                        {prediction.news.map((item, i) => (
                          <Grid size={12} key={i}>
                            <Card sx={{ background: 'transparent' }}>
                              <CardContent sx={{ display: 'flex', gap: 2, p: '16px !important' }}>
                                {item.thumbnail && <Avatar src={item.thumbnail} variant="rounded" sx={{ width: 60, height: 60 }} />}
                                <Box>
                                  <Link href={item.link} target="_blank" underline="none" sx={{ '&:hover': { color: 'primary.main' } }}>
                                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{item.title}</Typography>
                                  </Link>
                                  <Typography variant="caption" sx={{ color: 'primary.main', mr: 2 }}>{item.source}</Typography>
                                  <Typography variant="caption" sx={{ opacity: 0.5 }}>{item.date}</Typography>
                                </Box>
                              </CardContent>
                            </Card>
                          </Grid>
                        ))}
                      </Grid>
                    </>
                  )}
                </Stack>
              ) : (
                <Box sx={{ height: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.15 }}>
                  <Typography variant="h4">QUANTUM SYSTEM READY</Typography>
                </Box>
              )}
            </Grid>

            {/* ── Right column ──────────────────────────────────────── */}
            <Grid size={{ xs: 12, lg: 4 }}>
              {loading ? <SidebarSkeleton /> : (
                <Stack spacing={3}>
                  {prediction && (
                    <>
                      {/* Forecast summary */}
                      <Card sx={{ background: isDark ? 'linear-gradient(135deg, #0d1520 0%, #1a237e 100%)' : 'linear-gradient(135deg, #ffffff 0%, #dbeafe 100%)' }}>
                        <CardContent>
                          <Typography variant="overline" color="primary.main">5-Day Ensemble Forecast</Typography>
                          <Stack spacing={2} sx={{ mt: 2 }}>
                            <Box>
                              <Typography variant="caption" sx={{ opacity: 0.4 }}>5-DAY HIGH TARGET</Typography>
                              <Typography variant="h4" color="success.main">${prediction.prediction.highRange}</Typography>
                            </Box>
                            <Box>
                              <Typography variant="caption" sx={{ opacity: 0.4 }}>5-DAY LOW TARGET</Typography>
                              <Typography variant="h4" color="error.main">${prediction.prediction.lowRange}</Typography>
                            </Box>
                          </Stack>
                          <Divider sx={{ my: 2, opacity: 0.1 }} />
                          <Typography variant="body2" sx={{ fontStyle: 'italic', opacity: 0.85, lineHeight: 1.6 }}>
                            {prediction.analystNote}
                          </Typography>
                          <Chip
                            label={`${prediction.confidence.toUpperCase()} CONFIDENCE`}
                            size="small" color="secondary"
                            sx={{ mt: 2, fontWeight: 900, fontSize: '0.6rem' }}
                          />
                        </CardContent>
                      </Card>

                      {/* Fundamentals */}
                      <Card>
                        <CardContent>
                          <Typography variant="overline" sx={{ opacity: 0.5 }}>Fundamentals & Model Stats</Typography>
                          <Grid container spacing={2} sx={{ mt: 1 }}>
                            {[
                              { label: 'MARKET CAP', val: prediction.metrics.market_cap },
                              { label: 'P/E RATIO',  val: prediction.metrics.pe_ratio   },
                              { label: 'RSI', val: `${prediction.rsi} (${rsiInfo?.label})`,
                                color: rsiInfo?.color === 'error' ? (isDark ? '#ff0055' : '#dc2626') : rsiInfo?.color === 'success' ? (isDark ? '#00ffa3' : '#16a34a') : primaryColor },
                              { label: '52W RANGE',  val: prediction.metrics.range_52w  },
                              { label: 'ANN. VOL',   val: `${prediction.modelStats?.ann_volatility_pct ?? '—'}%` },
                              {
                                label: 'TREND SLOPE',
                                val: prediction.modelStats?.trend_slope
                                  ? `${prediction.modelStats.trend_slope > 0 ? '▲' : '▼'} ${Math.abs(prediction.modelStats.trend_slope).toFixed(3)}/day`
                                  : '—',
                                color: prediction.modelStats?.trend_slope > 0 ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626'),
                              },
                              {
                                label: 'VS SMA20',
                                val: prediction.modelStats?.price_vs_sma20_pct !== undefined
                                  ? `${prediction.modelStats.price_vs_sma20_pct > 0 ? '+' : ''}${prediction.modelStats.price_vs_sma20_pct.toFixed(2)}%`
                                  : '—',
                                color: prediction.modelStats?.price_vs_sma20_pct > 0 ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626'),
                              },
                              { label: 'DIVIDEND', val: prediction.metrics.yield },
                            ].map(item => (
                              <Grid size={6} key={item.label}>
                                <Typography variant="caption" sx={{ opacity: 0.4 }}>{item.label}</Typography>
                                <Typography variant="body2" sx={{ fontWeight: 700, color: item.color ?? 'inherit' }}>
                                  {item.val}
                                </Typography>
                              </Grid>
                            ))}
                          </Grid>
                        </CardContent>
                      </Card>
                    </>
                  )}

                  {/* ── Trending Sparklines (real 5-day) ─────────────────── */}
                  {prediction?.trending?.length > 0 && (
                    <TrendingSparklines tickers={prediction.trending} isDark={isDark} />
                  )}

                </Stack>
              )}
            </Grid>

          </Grid>
        </Container>
      </Box>
    </ThemeProvider>
  );
}
