"use client";

import React, { useState, useMemo } from 'react';
import axios from 'axios';
import { 
  Box, Container, Typography, TextField, Button, Card, CardContent, 
  Grid, Divider, CircularProgress, Alert, ThemeProvider, createTheme, 
  CssBaseline, Paper, Chip, Stack, MenuItem, Select, FormControl,
  Avatar, Link
} from '@mui/material';
import { 
  TrendingUp, TrendingDown, Search, BrainCircuit, Activity, Clock, 
  Globe, BarChart, Info, Newspaper, Zap
} from 'lucide-react';
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area,
  LineChart, Line, ReferenceLine
} from 'recharts';

interface PredictionData {
  symbol: string;
  currentPrice: string;
  rsi: string;
  prediction: {
    highRange: string;
    lowRange: string;
    trend: 'Bullish' | 'Bearish';
  };
  analystNote: string;
  confidence: string;
  history: { date: string; price: number }[];
  metrics: {
    market_cap: string;
    pe_ratio: string;
    yield: string;
    prev_close: string;
    range_52w: string;
  };
  news: {
    title: string;
    link: string;
    source: string;
    thumbnail: string;
    date: string;
  }[];
  trending: {
    symbol: string;
    name?: string;
    price: string | number;
    change: string;
    category?: string;
  }[];
  lastUpdated: string;
}

const quantumTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#00f2ff' },
    secondary: { main: '#bc13fe' },
    success: { main: '#00ffa3' },
    error: { main: '#ff0055' },
    background: { default: '#050a10', paper: '#0d1520' },
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
          border: '1px solid rgba(0, 242, 255, 0.1)',
          transition: 'all 0.3s ease',
          '&:hover': { border: '1px solid rgba(0, 242, 255, 0.3)' }
        }
      }
    }
  }
});

const EXCHANGES = [
  { value: '', label: 'Auto' },
  { value: 'NASDAQ', label: 'NASDAQ' },
  { value: 'NYSE', label: 'NYSE' },
  { value: 'LSE', label: 'London (LSE)' },
  { value: 'FRA', label: 'Frankfurt' },
];

const CATEGORY_META: Record<string, { label: string; color: string }> = {
  us:         { label: 'US',  color: '#3b82f6' },
  europe:     { label: 'EU',  color: '#8b5cf6' },
  asia:       { label: 'AS',  color: '#f59e0b' },
  currencies: { label: 'FX',  color: '#10b981' },
  crypto:     { label: 'DFI', color: '#f97316' },
};

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

export default function QuantumDashboard() {
  const [ticker, setTicker] = useState('NVDA');
  const [exchange, setExchange] = useState('');
  const [prediction, setPrediction] = useState<PredictionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      const fullSymbol = exchange ? `${ticker}:${exchange}` : ticker;
      const response = await axios.post('/api/predict', { data: fullSymbol });
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
    if (val >= 70) return { label: 'Overbought', color: 'error' as const };
    if (val <= 30) return { label: 'Oversold', color: 'success' as const };
    return { label: 'Neutral', color: 'primary' as const };
  }, [prediction]);

  const chartDomain = React.useMemo((): [number, number] | ['auto', 'auto'] => {
    if (!prediction?.history?.length) return ['auto', 'auto'];
    const prices = prediction.history.map(h => h.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const pad = (max - min) * 0.12 || max * 0.02;
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [prediction?.history]);

  const chartStats = React.useMemo(() => {
    if (!prediction?.history?.length) return null;
    const prices = prediction.history.map(h => h.price);
    const first = prices[0];
    const last = prices[prices.length - 1];
    const change = last - first;
    const changePct = first > 0 ? (change / first) * 100 : 0;
    const isUp = change >= 0;
    return {
      open: first,
      change,
      changePct,
      high: Math.max(...prices),
      low: Math.min(...prices),
      isUp,
      color: isUp ? '#00ffa3' : '#ff0055',
    };
  }, [prediction?.history]);

  const trendingSparklines = React.useMemo(() => {
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

  return (
    <ThemeProvider theme={quantumTheme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', py: 4, px: 2, background: 'radial-gradient(circle at 50% -20%, #1a237e 0%, #050a10 60%)' }}>
        <Container maxWidth="xl">
          
          {/* Header */}
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2} sx={{ mb: 6 }}>
            <Box>
              <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, color: '#fff' }}>
                <BrainCircuit size={32} color="#00f2ff" />
                FiForesight <Box component="span" sx={{ color: 'secondary.main' }}>QUANTUM</Box>
              </Typography>
              <Typography variant="caption" sx={{ letterSpacing: 4, color: 'primary.main', opacity: 0.8 }}>
                AI-POWERED QUANTITATIVE ENGINE
              </Typography>
            </Box>

            <Paper sx={{ p: 0.5, display: 'flex', gap: 1, alignItems: 'center', width: { xs: '100%', md: 500 }, background: 'rgba(255,255,255,0.03)', backdropFilter: 'blur(20px)', borderRadius: 4 }}>
              <TextField
                sx={{ flexGrow: 1, input: { px: 2, fontWeight: 700 } }}
                placeholder="Search Ticker..."
                variant="standard"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                InputProps={{ disableUnderline: true }}
              />
              <Select
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                disableUnderline
                sx={{ minWidth: 100, fontWeight: 600, fontSize: '0.8rem' }}
              >
                {EXCHANGES.map(ex => <MenuItem key={ex.value} value={ex.value}>{ex.label}</MenuItem>)}
              </Select>
              <Button 
                variant="contained" 
                onClick={handlePredict} 
                disabled={loading}
                sx={{ borderRadius: 3, minWidth: 50, py: 1, boxShadow: '0 0 20px rgba(0, 242, 255, 0.3)' }}
              >
                {loading ? <CircularProgress size={20} color="inherit" /> : <Search size={20} />}
              </Button>
            </Paper>
          </Stack>

          {error && <Alert severity="error" sx={{ mb: 4, borderRadius: 3 }}>{error}</Alert>}

          <Grid container spacing={3}>
            {/* Left Column: Chart & News */}
            <Grid item xs={12} lg={8}>
              {prediction ? (
                <Stack spacing={3}>
                  <Card>
                    <CardContent sx={{ p: 4 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 4 }}>
                        <Box>
                          <Typography variant="h2" color="#fff">{prediction.symbol}</Typography>
                          <Chip 
                            label={`${prediction.prediction.trend} Trend`} 
                            color={prediction.prediction.trend === 'Bullish' ? 'success' : 'error'}
                            sx={{ fontWeight: 900, fontSize: '0.7rem' }}
                            size="small"
                          />
                        </Box>
                        <Box sx={{ textAlign: 'right' }}>
                          <Typography variant="h3" color="primary.main">${prediction.currentPrice}</Typography>
                          <Typography variant="caption" sx={{ opacity: 0.5 }}>REAL-TIME FEED</Typography>
                        </Box>
                      </Box>

                      {/* Chart stats bar */}
                      {chartStats && (
                        <Stack direction="row" spacing={3} sx={{ mb: 3, flexWrap: 'wrap', gap: 1 }}>
                          <Box>
                            <Typography variant="caption" sx={{ opacity: 0.4, display: 'block', letterSpacing: 1 }}>CHANGE</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 800, color: chartStats.color }}>
                              {chartStats.isUp ? '+' : ''}{chartStats.change.toFixed(2)} ({chartStats.isUp ? '+' : ''}{chartStats.changePct.toFixed(2)}%)
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" sx={{ opacity: 0.4, display: 'block', letterSpacing: 1 }}>PERIOD HIGH</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 800, color: 'success.main' }}>${chartStats.high.toFixed(2)}</Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" sx={{ opacity: 0.4, display: 'block', letterSpacing: 1 }}>PERIOD LOW</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 800, color: 'error.main' }}>${chartStats.low.toFixed(2)}</Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" sx={{ opacity: 0.4, display: 'block', letterSpacing: 1 }}>DATA POINTS</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 800, opacity: 0.6 }}>{prediction.history.length}D</Typography>
                          </Box>
                        </Stack>
                      )}

                      <Box sx={{ height: 380 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={prediction.history} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                            <defs>
                              <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={chartStats?.color ?? '#00f2ff'} stopOpacity={0.4} />
                                <stop offset="95%" stopColor={chartStats?.color ?? '#00f2ff'} stopOpacity={0} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                            <XAxis
                              dataKey="date"
                              stroke="rgba(255,255,255,0.1)"
                              tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 10 }}
                              tickLine={false}
                              axisLine={false}
                            />
                            <YAxis
                              domain={chartDomain}
                              stroke="rgba(255,255,255,0.1)"
                              tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 10 }}
                              tickLine={false}
                              axisLine={false}
                              width={65}
                              tickFormatter={(v: number) =>
                                v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`
                              }
                            />
                            <Tooltip
                              contentStyle={{
                                background: '#0d1520',
                                border: `1px solid ${chartStats?.color ?? '#00f2ff'}`,
                                borderRadius: 10,
                                boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                              }}
                              formatter={(value: any) => {
                                const v = Number(value);
                                const open = chartStats?.open ?? v;
                                const diff = v - open;
                                const pct = open > 0 ? ((diff / open) * 100).toFixed(2) : '0.00';
                                return [`$${v.toFixed(2)}  (${diff >= 0 ? '+' : ''}${pct}%)`, 'Price'];
                              }}
                              labelStyle={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, marginBottom: 4 }}
                            />
                            {chartStats && (
                              <ReferenceLine
                                y={chartStats.open}
                                stroke="rgba(255,255,255,0.15)"
                                strokeDasharray="6 3"
                                label={`Open $${chartStats.open.toFixed(2)}`}
                              />
                            )}
                            <Area
                              type="monotone"
                              dataKey="price"
                              stroke={chartStats?.color ?? '#00f2ff'}
                              strokeWidth={2.5}
                              fill="url(#priceGradient)"
                              dot={false}
                              activeDot={{ r: 5, strokeWidth: 0, fill: chartStats?.color ?? '#00f2ff' }}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </Box>
                    </CardContent>
                  </Card>

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
                </Stack>
              ) : (
                <Box sx={{ height: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.2 }}>
                  <Typography variant="h4">QUANTUM SYSTEM READY</Typography>
                </Box>
              )}
            </Grid>

            {/* Right Column: Forecast & Stats */}
            <Grid item xs={12} lg={4}>
              <Stack spacing={3}>
                {prediction && (
                  <>
                    <Card sx={{ background: 'linear-gradient(135deg, #0d1520 0%, #1a237e 100%)' }}>
                      <CardContent>
                        <Typography variant="overline" color="primary.main">Quantum Forecast</Typography>
                        <Stack spacing={2} sx={{ mt: 2 }}>
                          <Box>
                            <Typography variant="h4" color="success.main">${prediction.prediction.highRange}</Typography>
                            <Typography variant="caption">EXPECTED HIGH (48H)</Typography>
                          </Box>
                          <Box>
                            <Typography variant="h4" color="error.main">${prediction.prediction.lowRange}</Typography>
                            <Typography variant="caption">EXPECTED LOW (48H)</Typography>
                          </Box>
                        </Stack>
                        <Divider sx={{ my: 2, opacity: 0.1 }} />
                        <Typography variant="body2" sx={{ fontStyle: 'italic', color: '#fff', opacity: 0.9 }}>
                          "{prediction.analystNote}"
                        </Typography>
                        <Chip label={prediction.confidence.toUpperCase()} size="small" color="secondary" sx={{ mt: 2, fontWeight: 900, fontSize: '0.6rem' }} />
                      </CardContent>
                    </Card>

                    <Card>
                      <CardContent>
                        <Typography variant="overline" sx={{ opacity: 0.5 }}>Fundamentals</Typography>
                        <Grid container spacing={2} sx={{ mt: 1 }}>
                          <Grid item xs={6}>
                            <Typography variant="caption" sx={{ opacity: 0.5 }}>MARKET CAP</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>{prediction.metrics.market_cap}</Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="caption" sx={{ opacity: 0.5 }}>P/E RATIO</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>{prediction.metrics.pe_ratio}</Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="caption" sx={{ opacity: 0.5 }}>RSI (DAILY)</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 700, color: `${rsiInfo?.color}.main` }}>{prediction.rsi}</Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="caption" sx={{ opacity: 0.5 }}>52W RANGE</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>{prediction.metrics.range_52w}</Typography>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </>
                )}

                <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1 }}>
                  <Zap size={20} color="#00ffa3" /> Active Markets
                </Typography>
                <Stack spacing={1}>
                  {(prediction?.trending || []).map((t, i) => {
                    const meta = CATEGORY_META[(t as any).category as string] ?? { label: '??', color: '#64748b' };
                    const isUp = String(t.change ?? '').startsWith('+');
                    const sparkColor = isUp ? '#00ffa3' : '#ff0055';
                    const sparkData = trendingSparklines[i] ?? [];
                    const rawPrice = parseFloat(String(t.price).replace(/[^\d.]/g, ''));
                    const priceStr = isNaN(rawPrice)
                      ? String(t.price)
                      : rawPrice >= 10000
                      ? rawPrice.toLocaleString('en-US', { maximumFractionDigits: 0 })
                      : rawPrice >= 1
                      ? rawPrice.toFixed(2)
                      : rawPrice.toFixed(5);
                    return (
                      <Paper
                        key={i}
                        sx={{
                          px: 1.5, py: 1.2,
                          background: 'rgba(255,255,255,0.02)',
                          display: 'flex', alignItems: 'center', gap: 1,
                          overflow: 'hidden',
                          border: '1px solid transparent',
                          '&:hover': { border: `1px solid ${sparkColor}44`, background: 'rgba(255,255,255,0.04)' },
                          transition: 'all 0.2s ease',
                        }}
                      >
                        {/* Category badge */}
                        <Box sx={{
                          width: 26, height: 26, borderRadius: '6px',
                          background: `${meta.color}20`, border: `1px solid ${meta.color}50`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                        }}>
                          <Typography sx={{ fontSize: '0.5rem', fontWeight: 900, color: meta.color, lineHeight: 1 }}>
                            {meta.label}
                          </Typography>
                        </Box>

                        {/* Name & ticker */}
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography sx={{
                            fontSize: '0.7rem', fontWeight: 700, display: 'block',
                            lineHeight: 1.3, color: '#fff',
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {(t as any).name || t.symbol}
                          </Typography>
                          {(t as any).name && t.symbol && (
                            <Typography sx={{ fontSize: '0.55rem', opacity: 0.3, lineHeight: 1 }}>
                              {t.symbol}
                            </Typography>
                          )}
                        </Box>

                        {/* Mini sparkline */}
                        {sparkData.length > 0 && <MiniSparkline data={sparkData} color={sparkColor} />}

                        {/* Price & change */}
                        <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                          <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, display: 'block', color: '#fff' }}>
                            {priceStr}
                          </Typography>
                          <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, color: sparkColor }}>
                            {String(t.change ?? '0%')}
                          </Typography>
                        </Box>
                      </Paper>
                    );
                  })}
                </Stack>
              </Stack>
            </Grid>
          </Grid>

          {/* Footer */}
          <Box sx={{ mt: 8, textAlign: 'center', opacity: 0.3 }}>
            <Typography variant="caption" sx={{ letterSpacing: 2 }}>
              QUANTUM ENGINE • DATA REFRESHED: {prediction ? new Date(prediction.lastUpdated).toLocaleTimeString() : 'N/A'}
            </Typography>
          </Box>

        </Container>
      </Box>
    </ThemeProvider>
  );
}
