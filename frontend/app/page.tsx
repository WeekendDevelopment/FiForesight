"use client";

import React, { useState, useMemo, useRef } from 'react';
import axios from 'axios';
import {
  Box, Container, Typography, TextField, Button, Card, CardContent,
  Grid, Divider, CircularProgress, Alert, ThemeProvider, createTheme,
  CssBaseline, Paper, Chip, Stack, MenuItem, Select, Avatar, Link,
  Skeleton, ToggleButton, ToggleButtonGroup, IconButton, Autocomplete,
} from '@mui/material';
import {
  Search, BrainCircuit, Newspaper, Zap, BarChart2, Sun, Moon,
} from 'lucide-react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, ComposedChart, Area, Legend,
  BarChart, Bar, Cell,
} from 'recharts';

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
  indicators?: { rsi_series?: number[] };
  lastUpdated: string;
}

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

const CATEGORY_META: Record<string, { label: string; color: string }> = {
  us:         { label: 'US',  color: '#3b82f6' },
  europe:     { label: 'EU',  color: '#8b5cf6' },
  asia:       { label: 'AS',  color: '#f59e0b' },
  currencies: { label: 'FX',  color: '#10b981' },
  crypto:     { label: 'DFI', color: '#f97316' },
};

type IndicatorKey = 'bb' | 'sma' | 'macd' | 'rsi' | 'volume';

// ── Mini sparkline ────────────────────────────────────────────────────────────

function MiniSparkline({ data, color }: { data: { v: number }[]; color: string }) {
  return (
    <Box sx={{ width: 68, height: 30, flexShrink: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Box>
  );
}

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
            <Grid item xs={6} key={i}>
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
const CHART_MARGIN   = { top: 5, right: 10, bottom: 5, left: 10 };
const YAXIS_WIDTH    = 65;
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

  const trendingSparklines = useMemo(() => {
    if (!prediction?.trending) return {} as Record<number, { v: number }[]>;
    return prediction.trending.reduce((acc, t, i) => {
      const isUp = String(t.change ?? '').startsWith('+');
      const base = parseFloat(String(t.price).replace(/[^\d.]/g, '')) || 100;
      const seed = i * 3.7 + base * 0.01;
      acc[i] = Array.from({ length: 12 }, (_, j) => ({
        v: base * (1 + (isUp ? 1 : -1) * (j / 11) * 0.025 + Math.sin(seed + j * 0.9) * 0.007),
      }));
      return acc;
    }, {} as Record<number, { v: number }[]>);
  }, [prediction?.trending]);

  const trendColor   = chartStats?.color ?? (isDark ? '#00f2ff' : '#0077ff');
  const primaryColor = isDark ? '#00f2ff' : '#0077ff';

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
            <Grid item xs={12} lg={8}>
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

                      {/* ── Chart mode toggle ───────────────────── */}
                      <Box sx={{ display: 'flex', mb: 2 }}>
                        {(['line', 'candle'] as const).map((mode, idx) => (
                          <Box key={mode} onClick={() => setChartMode(mode)} sx={{
                            px: 1.5, py: 0.4, cursor: 'pointer',
                            fontSize: '0.65rem', fontWeight: 800, letterSpacing: 1,
                            border: '1px solid rgba(128,128,128,0.2)',
                            borderRadius: idx === 0 ? '6px 0 0 6px' : '0 6px 6px 0',
                            ml: idx === 1 ? '-1px' : 0,
                            background: chartMode === mode ? `${primaryColor}1a` : 'transparent',
                            color: chartMode === mode ? primaryColor : 'rgba(128,128,128,0.5)',
                            transition: 'all 0.15s',
                            '&:hover': { color: primaryColor, background: `${primaryColor}0d` },
                            userSelect: 'none',
                          }}>
                            {mode === 'line' ? 'LINE' : 'CANDLE'}
                          </Box>
                        ))}
                      </Box>

                      {/* ── Main price + overlay chart ──────────────── */}
                      <Box ref={chartBoxRef} sx={{ height: 380, position: 'relative' }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <ComposedChart data={chartMode === 'line' ? chartData : candleChartData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
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

                  {/* ── News ─────────────────────────────────────────────── */}
                  {prediction.news?.length > 0 && (
                    <>
                      <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1 }}>
                        <Newspaper size={20} /> Market Intelligence
                      </Typography>
                      <Grid container spacing={2}>
                        {prediction.news.map((item, i) => (
                          <Grid item xs={12} key={i}>
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
            <Grid item xs={12} lg={4}>
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
                              <Grid item xs={6} key={item.label}>
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

                  {/* Active markets */}
                  <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1 }}>
                    <Zap size={20} color={isDark ? '#00ffa3' : '#16a34a'} /> Active Markets
                  </Typography>
                  <Stack spacing={1}>
                    {(prediction?.trending || []).map((t, i) => {
                      const meta      = CATEGORY_META[(t as any).category ?? ''] ?? { label: '??', color: '#64748b' };
                      const isUp      = String(t.change ?? '').startsWith('+');
                      const sparkColor = isUp ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626');
                      const sparkData  = trendingSparklines[i] ?? [];
                      const rawPrice   = parseFloat(String(t.price).replace(/[^\d.]/g, ''));
                      const priceStr   = isNaN(rawPrice) ? String(t.price)
                        : rawPrice >= 10000 ? rawPrice.toLocaleString('en-US', { maximumFractionDigits: 0 })
                        : rawPrice >= 1     ? rawPrice.toFixed(2)
                        : rawPrice.toFixed(5);
                      return (
                        <Paper key={i} sx={{
                          px: 1.5, py: 1.2,
                          background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)',
                          display: 'flex', alignItems: 'center', gap: 1,
                          border: '1px solid transparent',
                          '&:hover': { border: `1px solid ${sparkColor}44`, background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)' },
                          transition: 'all 0.2s ease',
                        }}>
                          <Box sx={{ width: 26, height: 26, borderRadius: '6px', background: `${meta.color}20`, border: `1px solid ${meta.color}50`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                            <Typography sx={{ fontSize: '0.5rem', fontWeight: 900, color: meta.color, lineHeight: 1 }}>{meta.label}</Typography>
                          </Box>
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {(t as any).name || t.symbol}
                            </Typography>
                            {(t as any).name && t.symbol && (
                              <Typography sx={{ fontSize: '0.55rem', opacity: 0.3 }}>{t.symbol}</Typography>
                            )}
                          </Box>
                          {sparkData.length > 0 && <MiniSparkline data={sparkData} color={sparkColor} />}
                          <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                            <Typography sx={{ fontSize: '0.7rem', fontWeight: 700 }}>{priceStr}</Typography>
                            <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, color: sparkColor }}>{String(t.change ?? '0%')}</Typography>
                          </Box>
                        </Paper>
                      );
                    })}
                  </Stack>
                </Stack>
              )}
            </Grid>

          </Grid>
        </Container>
      </Box>
    </ThemeProvider>
  );
}
