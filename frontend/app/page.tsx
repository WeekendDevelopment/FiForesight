"use client";

import React, { useState, useMemo } from 'react';
import axios from 'axios';
import {
  Box, Container, Typography, TextField, Button, Card, CardContent,
  Grid, Divider, CircularProgress, Alert, ThemeProvider, createTheme,
  CssBaseline, Paper, Chip, Stack, MenuItem, Select, Avatar, Link, Tooltip as MuiTooltip,
} from '@mui/material';
import {
  TrendingUp, TrendingDown, Search, BrainCircuit, Activity,
  Newspaper, Zap, BarChart2,
} from 'lucide-react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, ComposedChart, Area, Legend,
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
  history:      { date: string; price: number; open?: number; high?: number; low?: number; volume?: number }[];
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
  news: { title: string; link: string; source: string; thumbnail: string; date: string }[];
  trending: { symbol: string; name?: string; price: string | number; change: string; category?: string }[];
  lastUpdated: string;
}

// ── Theme ─────────────────────────────────────────────────────────────────────

const quantumTheme = createTheme({
  palette: {
    mode: 'dark',
    primary:    { main: '#00f2ff' },
    secondary:  { main: '#bc13fe' },
    success:    { main: '#00ffa3' },
    error:      { main: '#ff0055' },
    background: { default: '#050a10', paper: '#0d1520' },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontWeight: 900 },
    h2: { fontWeight: 800 },
    h4: { fontWeight: 700 },
  },
  shape: { borderRadius: 12 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid rgba(0, 242, 255, 0.1)',
          transition: 'all 0.3s ease',
          '&:hover': { border: '1px solid rgba(0, 242, 255, 0.3)' },
        },
      },
    },
  },
});

// ── Constants ─────────────────────────────────────────────────────────────────

const EXCHANGES = [
  { value: '',       label: 'Auto'          },
  { value: 'NASDAQ', label: 'NASDAQ'        },
  { value: 'NYSE',   label: 'NYSE'          },
  { value: 'LSE',    label: 'London (LSE)'  },
  { value: 'FRA',    label: 'Frankfurt'     },
];

const CATEGORY_META: Record<string, { label: string; color: string }> = {
  us:         { label: 'US',  color: '#3b82f6' },
  europe:     { label: 'EU',  color: '#8b5cf6' },
  asia:       { label: 'AS',  color: '#f59e0b' },
  currencies: { label: 'FX',  color: '#10b981' },
  crypto:     { label: 'DFI', color: '#f97316' },
};

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

// ── Main dashboard ────────────────────────────────────────────────────────────

export default function QuantumDashboard() {
  const [ticker,     setTicker]     = useState('NVDA');
  const [exchange,   setExchange]   = useState('');
  const [prediction, setPrediction] = useState<PredictionData | null>(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      const fullSymbol = exchange ? `${ticker}:${exchange}` : ticker;
      const response   = await axios.post('/api/predict', { data: fullSymbol });
      setPrediction(response.data);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Market analysis failed.');
    } finally {
      setLoading(false);
    }
  };

  // ── RSI label ──────────────────────────────────────────────────────────────
  const rsiInfo = useMemo(() => {
    if (!prediction) return null;
    const val = parseFloat(prediction.rsi);
    if (val >= 70) return { label: 'Overbought', color: 'error'   as const };
    if (val <= 30) return { label: 'Oversold',   color: 'success' as const };
    return            { label: 'Neutral',     color: 'primary' as const };
  }, [prediction]);

  // ── Merge history + forecast into a single chart dataset ──────────────────
  // History points have { date, price }, forecast points add { predicted, high, low }
  const chartData = useMemo(() => {
    if (!prediction) return [];
    const hist = prediction.history.map(h => ({
      date:      h.date,
      price:     h.price,
      predicted: undefined as number | undefined,
      foreHigh:  undefined as number | undefined,
      foreLow:   undefined as number | undefined,
    }));
    const fore = (prediction.forecastDays || []).map(f => ({
      date:      f.date,
      price:     undefined as number | undefined,
      predicted: f.predicted,
      foreHigh:  f.high,
      foreLow:   f.low,
    }));
    return [...hist, ...fore];
  }, [prediction]);

  // ── Y-axis domain covering both history and forecast ──────────────────────
  const chartDomain = useMemo((): [number, number] | ['auto', 'auto'] => {
    if (!chartData.length) return ['auto', 'auto'];
    const allVals = chartData.flatMap(d => [
      d.price, d.predicted, d.foreHigh, d.foreLow,
    ].filter((v): v is number => v !== undefined));
    if (!allVals.length) return ['auto', 'auto'];
    const min = Math.min(...allVals);
    const max = Math.max(...allVals);
    const pad = (max - min) * 0.12 || max * 0.02;
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [chartData]);

  // ── Historical performance stats ───────────────────────────────────────────
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
      color: isUp ? '#00ffa3' : '#ff0055',
    };
  }, [prediction?.history]);

  // ── Trending sparklines ────────────────────────────────────────────────────
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

  const trendColor = chartStats?.isUp ? '#00ffa3' : '#ff0055';

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', py: 4, px: 2, background: 'radial-gradient(circle at 50% -20%, #1a237e 0%, #050a10 60%)' }}>
        <Container maxWidth="xl">

          {/* ── Header ─────────────────────────────────────────────────── */}
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2} sx={{ mb: 6 }}>
            <Box>
              <Typography variant="h4" component="h1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <BrainCircuit size={40} className="text-primary" />
                FiForesight <Box component="span" sx={{ color: 'primary.main' }}>AI</Box>
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.6, letterSpacing: 1 }}>
                NEXT-GEN QUANTITATIVE FORECASTING
              </Typography>
            </Box>

            <Paper sx={{ p: 1, display: 'flex', alignItems: 'center', width: { xs: '100%', md: 400 }, background: 'rgba(255,255,255,0.05)', backdropFilter: 'blur(10px)' }}>
              <TextField
                sx={{ flexGrow: 1, input: { px: 2, fontWeight: 700 } }}
                placeholder="Search Ticker…"
                variant="standard"
                value={ticker}
                onChange={e => setTicker(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && handlePredict()}
                InputProps={{ disableUnderline: true }}
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
                sx={{ borderRadius: 3, minWidth: 50, py: 1, boxShadow: '0 0 20px rgba(0,242,255,0.3)' }}
              >
                {loading ? <CircularProgress size={24} /> : <Search size={20} />}
              </Button>
            </Paper>
          </Stack>

          {error && <Alert severity="error" sx={{ mb: 4, borderRadius: 3 }}>{error}</Alert>}

          <Grid container spacing={3}>

            {/* ── Left column: Chart + News ─────────────────────────────── */}
            <Grid item xs={12} lg={8}>
              {prediction ? (
                <Stack spacing={3}>

                  {/* Price chart card */}
                  <Card>
                    <CardContent sx={{ p: 4 }}>
                      {/* Symbol header */}
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
                        <Box>
                          <Typography variant="h2" color="#fff">{prediction.symbol}</Typography>
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
                        <Stack direction="row" spacing={3} sx={{ mb: 3, flexWrap: 'wrap', gap: 1 }}>
                          {[
                            { label: 'CHANGE',      val: `${chartStats.isUp ? '+' : ''}${chartStats.change.toFixed(2)} (${chartStats.isUp ? '+' : ''}${chartStats.changePct.toFixed(2)}%)`, col: trendColor },
                            { label: 'PERIOD HIGH', val: `$${chartStats.high.toFixed(2)}`,                col: '#00ffa3' },
                            { label: 'PERIOD LOW',  val: `$${chartStats.low.toFixed(2)}`,                col: '#ff0055' },
                            { label: 'SMA 20',      val: `$${prediction.modelStats?.sma_20 ?? '—'}`,     col: '#f59e0b' },
                            { label: 'ANN. VOL',    val: `${prediction.modelStats?.ann_volatility_pct ?? '—'}%`, col: 'rgba(255,255,255,0.5)' },
                            { label: 'DATA PTS',    val: `${prediction.history.length}D`,                 col: 'rgba(255,255,255,0.4)' },
                          ].map(s => (
                            <Box key={s.label}>
                              <Typography variant="caption" sx={{ opacity: 0.4, display: 'block', letterSpacing: 1 }}>{s.label}</Typography>
                              <Typography variant="body2" sx={{ fontWeight: 800, color: s.col }}>{s.val}</Typography>
                            </Box>
                          ))}
                        </Stack>
                      )}

                      {/* ── Combined history + forecast chart ──────────── */}
                      <Box sx={{ height: 420 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <ComposedChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                            <defs>
                              <linearGradient id="histGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%"  stopColor={trendColor} stopOpacity={0.35} />
                                <stop offset="95%" stopColor={trendColor} stopOpacity={0}    />
                              </linearGradient>
                              <linearGradient id="foreGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%"  stopColor="#bc13fe" stopOpacity={0.25} />
                                <stop offset="95%" stopColor="#bc13fe" stopOpacity={0}    />
                              </linearGradient>
                            </defs>

                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />

                            <XAxis
                              dataKey="date"
                              stroke="rgba(255,255,255,0.1)"
                              tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10 }}
                              tickLine={false} axisLine={false}
                            />
                            <YAxis
                              domain={chartDomain}
                              stroke="rgba(255,255,255,0.1)"
                              tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10 }}
                              tickLine={false} axisLine={false}
                              width={65}
                              tickFormatter={(v: number) =>
                                v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`
                              }
                            />

                            <Tooltip
                              contentStyle={{ background: '#0d1520', border: '1px solid rgba(0,242,255,0.3)', borderRadius: 10 }}
                              formatter={(value: any, name: string) => {
                                const v = Number(value);
                                if (name === 'price')     return [`$${v.toFixed(2)}`, 'Close'];
                                if (name === 'predicted') return [`$${v.toFixed(2)}`, 'Forecast'];
                                if (name === 'foreHigh')  return [`$${v.toFixed(2)}`, 'Forecast High'];
                                if (name === 'foreLow')   return [`$${v.toFixed(2)}`, 'Forecast Low'];
                                return [v, name];
                              }}
                              labelStyle={{ color: 'rgba(255,255,255,0.4)', fontSize: 11 }}
                            />

                            <Legend
                              wrapperStyle={{ fontSize: '0.7rem', opacity: 0.6, paddingTop: 8 }}
                              formatter={(value) => {
                                const map: Record<string, string> = {
                                  price: 'Historical Close', predicted: '5-Day Forecast',
                                  foreHigh: 'Forecast High', foreLow: 'Forecast Low',
                                };
                                return map[value] ?? value;
                              }}
                            />

                            {/* SMA 20 reference line */}
                            {prediction.modelStats?.sma_20 > 0 && (
                              <ReferenceLine
                                y={prediction.modelStats.sma_20}
                                stroke="#f59e0b"
                                strokeDasharray="4 4"
                                strokeOpacity={0.5}
                                label={{ value: `SMA20 $${prediction.modelStats.sma_20}`, fill: '#f59e0b', fontSize: 9, position: 'insideTopRight' }}
                              />
                            )}

                            {/* Open reference */}
                            {chartStats && (
                              <ReferenceLine
                                y={chartStats.open}
                                stroke="rgba(255,255,255,0.12)"
                                strokeDasharray="6 3"
                              />
                            )}

                            {/* Historical price area */}
                            <Area
                              type="monotone"
                              dataKey="price"
                              stroke={trendColor}
                              strokeWidth={2.5}
                              fill="url(#histGrad)"
                              dot={false}
                              connectNulls={false}
                              activeDot={{ r: 4, strokeWidth: 0, fill: trendColor }}
                              isAnimationActive={false}
                            />

                            {/* Forecast high band (upper boundary) */}
                            <Area
                              type="monotone"
                              dataKey="foreHigh"
                              stroke="rgba(188,19,254,0.5)"
                              strokeWidth={1.5}
                              strokeDasharray="5 3"
                              fill="url(#foreGrad)"
                              dot={false}
                              connectNulls={false}
                              isAnimationActive={false}
                            />

                            {/* Forecast low band (lower boundary) */}
                            <Area
                              type="monotone"
                              dataKey="foreLow"
                              stroke="rgba(188,19,254,0.3)"
                              strokeWidth={1}
                              strokeDasharray="5 3"
                              fill="transparent"
                              dot={false}
                              connectNulls={false}
                              isAnimationActive={false}
                            />

                            {/* Forecast predicted midline */}
                            <Line
                              type="monotone"
                              dataKey="predicted"
                              stroke="#bc13fe"
                              strokeWidth={2}
                              strokeDasharray="6 3"
                              dot={{ r: 4, fill: '#bc13fe', strokeWidth: 0 }}
                              connectNulls={false}
                              isAnimationActive={false}
                            />
                          </ComposedChart>
                        </ResponsiveContainer>
                      </Box>
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
                            const col  = isUp ? '#00ffa3' : '#ff0055';
                            return (
                              <Box key={i} sx={{
                                textAlign: 'center', p: 1.5, borderRadius: 2,
                                border: `1px solid ${col}22`,
                                background: `${col}08`,
                              }}>
                                <Typography sx={{ fontSize: '0.65rem', opacity: 0.5, letterSpacing: 1, display: 'block' }}>
                                  DAY {i + 1} · {day.date}
                                </Typography>
                                <Typography sx={{ fontSize: '1rem', fontWeight: 800, color: col, my: 0.5 }}>
                                  ${day.predicted}
                                </Typography>
                                <Typography sx={{ fontSize: '0.6rem', color: '#00ffa3', display: 'block' }}>
                                  ↑ ${day.high}
                                </Typography>
                                <Typography sx={{ fontSize: '0.6rem', color: '#ff0055', display: 'block', mb: 1 }}>
                                  ↓ ${day.low}
                                </Typography>
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
                                  <Link href={item.link} target="_blank" underline="none" sx={{ color: '#fff', '&:hover': { color: 'primary.main' } }}>
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
                <Box sx={{ height: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.2 }}>
                  <Typography variant="h4">QUANTUM SYSTEM READY</Typography>
                </Box>
              )}
            </Grid>

            {/* ── Right column: Forecast panel + fundamentals + markets ─ */}
            <Grid item xs={12} lg={4}>
              <Stack spacing={3}>
                {prediction && (
                  <>
                    {/* Forecast summary */}
                    <Card sx={{ background: 'linear-gradient(135deg, #0d1520 0%, #1a237e 100%)' }}>
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
                        <Typography variant="body2" sx={{ fontStyle: 'italic', color: '#fff', opacity: 0.85, lineHeight: 1.6 }}>
                          {prediction.analystNote}
                        </Typography>
                        <Chip
                          label={`${prediction.confidence.toUpperCase()} CONFIDENCE`}
                          size="small"
                          color="secondary"
                          sx={{ mt: 2, fontWeight: 900, fontSize: '0.6rem' }}
                        />
                      </CardContent>
                    </Card>

                    {/* Fundamentals + model stats */}
                    <Card>
                      <CardContent>
                        <Typography variant="overline" sx={{ opacity: 0.5 }}>Fundamentals & Model Stats</Typography>
                        <Grid container spacing={2} sx={{ mt: 1 }}>
                          {[
                            { label: 'MARKET CAP',    val: prediction.metrics.market_cap },
                            { label: 'P/E RATIO',     val: prediction.metrics.pe_ratio   },
                            {
                              label: 'RSI',
                              val: prediction.rsi,
                              color: rsiInfo?.color === 'error' ? '#ff0055' : rsiInfo?.color === 'success' ? '#00ffa3' : '#00f2ff',
                            },
                            { label: '52W RANGE',     val: prediction.metrics.range_52w  },
                            { label: 'ANN. VOL',      val: `${prediction.modelStats?.ann_volatility_pct ?? '—'}%` },
                            {
                              label: 'TREND SLOPE',
                              val: prediction.modelStats?.trend_slope
                                ? `${prediction.modelStats.trend_slope > 0 ? '▲' : '▼'} ${Math.abs(prediction.modelStats.trend_slope).toFixed(3)}/day`
                                : '—',
                              color: prediction.modelStats?.trend_slope > 0 ? '#00ffa3' : '#ff0055',
                            },
                            {
                              label: 'VS SMA20',
                              val: prediction.modelStats?.price_vs_sma20_pct !== undefined
                                ? `${prediction.modelStats.price_vs_sma20_pct > 0 ? '+' : ''}${prediction.modelStats.price_vs_sma20_pct.toFixed(2)}%`
                                : '—',
                              color: prediction.modelStats?.price_vs_sma20_pct > 0 ? '#00ffa3' : '#ff0055',
                            },
                            { label: 'DIVIDEND',      val: prediction.metrics.yield        },
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
                  <Zap size={20} color="#00ffa3" /> Active Markets
                </Typography>
                <Stack spacing={1}>
                  {(prediction?.trending || []).map((t, i) => {
                    const meta      = CATEGORY_META[(t as any).category ?? ''] ?? { label: '??', color: '#64748b' };
                    const isUp      = String(t.change ?? '').startsWith('+');
                    const sparkColor = isUp ? '#00ffa3' : '#ff0055';
                    const sparkData  = trendingSparklines[i] ?? [];
                    const rawPrice   = parseFloat(String(t.price).replace(/[^\d.]/g, ''));
                    const priceStr   = isNaN(rawPrice) ? String(t.price)
                      : rawPrice >= 10000 ? rawPrice.toLocaleString('en-US', { maximumFractionDigits: 0 })
                      : rawPrice >= 1     ? rawPrice.toFixed(2)
                      : rawPrice.toFixed(5);
                    return (
                      <Paper key={i} sx={{
                        px: 1.5, py: 1.2,
                        background: 'rgba(255,255,255,0.02)',
                        display: 'flex', alignItems: 'center', gap: 1,
                        border: '1px solid transparent',
                        '&:hover': { border: `1px solid ${sparkColor}44`, background: 'rgba(255,255,255,0.04)' },
                        transition: 'all 0.2s ease',
                      }}>
                        <Box sx={{
                          width: 26, height: 26, borderRadius: '6px',
                          background: `${meta.color}20`, border: `1px solid ${meta.color}50`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                        }}>
                          <Typography sx={{ fontSize: '0.5rem', fontWeight: 900, color: meta.color, lineHeight: 1 }}>
                            {meta.label}
                          </Typography>
                        </Box>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {(t as any).name || t.symbol}
                          </Typography>
                          {(t as any).name && t.symbol && (
                            <Typography sx={{ fontSize: '0.55rem', opacity: 0.3 }}>{t.symbol}</Typography>
                          )}
                        </Box>
                        {sparkData.length > 0 && <MiniSparkline data={sparkData} color={sparkColor} />}
                        <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                          <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#fff' }}>{priceStr}</Typography>
                          <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, color: sparkColor }}>
                            {String(t.change ?? '0%')}
                          </Typography>
                        </Box>
                      </Paper>
                    );
                  })}
                </Stack>
              </Grid>

            </Grid>
          </Grid>

          {/* Footer */}
          <Box sx={{ mt: 8, textAlign: 'center', opacity: 0.3 }}>
            <Typography variant="caption" sx={{ letterSpacing: 2 }}>
              QUANTUM ENGINE · PROPHET + SARIMA + RANDOM FOREST · REFRESHED: {prediction ? new Date(prediction.lastUpdated).toLocaleTimeString() : 'N/A'}
            </Typography>
          </Box>
        </Container>
      </Box>
    </ThemeProvider>
  );
}
