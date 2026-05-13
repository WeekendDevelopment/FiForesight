"use client";

import React, { useState, useMemo } from 'react';
import axios from 'axios';
import {
  Box, Container, Typography, TextField, Button, Card, CardContent,
  Grid, CircularProgress, Alert, ThemeProvider,
  CssBaseline, Paper, Chip, Stack, MenuItem, Select, Avatar, Link,
  Skeleton, IconButton, Autocomplete, Fab,
} from '@mui/material';
import {
  Search, BrainCircuit, Newspaper, BarChart2, Sun, Moon, MessageCircle,
} from 'lucide-react';
import ModelWeightBar   from '../components/ModelWeightBar';
import TrendingSparklines from '../components/TrendingSparklines';
import MonteCarloFanChart from '../components/MonteCarloFanChart';
import MonteCarloProbabilitySurface from '../components/MonteCarloProbabilitySurface';
import { buildTheme }    from '../lib/theme';
import ConfidenceBadge   from '../components/ConfidenceBadge';
import { ChartSkeleton, SidebarSkeleton } from '../components/Skeletons';
import AnalystJuryPanel  from '../components/AnalystJuryPanel';
import PriceChartCard    from '../components/PriceChartCard';
import FundamentalsPanel      from '../components/FundamentalsPanel';
import PeerComparisonPanel    from '../components/PeerComparisonPanel';
import TradeSetupCard         from '../components/TradeSetupCard';
import StockChatPanel    from '../components/StockChatPanel';
import { useIndicatorSignals } from '../hooks/useIndicatorSignals';
import type { PredictionData, IndicatorKey, TradeSetupResponse } from '../types';

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

// ── Main dashboard ────────────────────────────────────────────────────────────

export default function QuantumDashboard() {
  const [themeMode,        setThemeMode]        = useState<'dark' | 'light'>('dark');
  const [ticker,           setTicker]           = useState('NVDA');
  const [exchange,         setExchange]         = useState('');
  const [prediction,       setPrediction]       = useState<PredictionData | null>(null);
  const [loading,          setLoading]          = useState(false);
  const [error,            setError]            = useState<string | null>(null);
  const [indicators,       setIndicators]       = useState<IndicatorKey[]>(['bb', 'sma']);
  const [chartMode,        setChartMode]        = useState<'line' | 'candle'>('line');
  const [chartEngine,      setChartEngine]      = useState<'classic' | 'pro'>('classic');
  const [tradeSetup,       setTradeSetup]       = useState<TradeSetupResponse | null>(null);
  const [tradeSetupLoading, setTradeSetupLoading] = useState(false);
  const [chatOpen,         setChatOpen]         = useState(false);

  const theme = useMemo(() => buildTheme(themeMode), [themeMode]);

  const isDark = themeMode === 'dark';

  const fetchTradeSetup = (data: PredictionData) => {
    setTradeSetup(null);
    setTradeSetupLoading(true);
    axios.post('/api/trade-setup', {
      symbol:          data.symbol,
      current_price:   parseFloat(data.currentPrice),
      high_range:      parseFloat(data.prediction.highRange),
      low_range:       parseFloat(data.prediction.lowRange),
      rsi:             parseFloat(data.rsi),
      support:         data.indicators?.support    ?? [],
      resistance:      data.indicators?.resistance ?? [],
      trend:           data.prediction.trend,
      sentiment_label: data.sentiment?.label ?? 'Neutral',
    })
      .then(r  => setTradeSetup(r.data))
      .catch(() => { /* non-fatal */ })
      .finally(() => setTradeSetupLoading(false));
  };

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    setTradeSetup(null);
    setChatOpen(false);
    try {
      const fullSymbol = exchange ? `${ticker}:${exchange}` : ticker;
      const response   = await axios.post('/api/predict', { data: fullSymbol });
      setPrediction(response.data);
      fetchTradeSetup(response.data);
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

  const indicatorSignals = useIndicatorSignals(prediction, isDark, chartStats);

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
                  <PriceChartCard
                    prediction={prediction}
                    indicators={indicators}
                    setIndicators={setIndicators}
                    chartMode={chartMode}
                    setChartMode={setChartMode}
                    chartEngine={chartEngine}
                    setChartEngine={setChartEngine}
                    isDark={isDark}
                    primaryColor={primaryColor}
                    trendColor={trendColor}
                    chartStats={chartStats}
                    indicatorSignals={indicatorSignals}
                  />

                  {/* ── Trade Setup ──────────────────────────────────── */}
                  <TradeSetupCard
                    setup={tradeSetup}
                    loading={tradeSetupLoading}
                    isDark={isDark}
                    primaryColor={primaryColor}
                  />

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

                  {/* ── Monte Carlo GBM ──────────────────────────────────── */}
                  {prediction.monteCarlo && (
                    <Card>
                      <CardContent>
                        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
                          <Typography variant="overline" sx={{ opacity: 0.5 }}>
                            Monte Carlo Simulation
                          </Typography>
                          <MonteCarloProbabilitySurface
                            priceRangeByDay={prediction.monteCarlo.price_range_by_day}
                            currentPrice={parseFloat(prediction.currentPrice)}
                            symbol={prediction.symbol}
                          />
                        </Stack>
                        <MonteCarloFanChart
                          monteCarlo={prediction.monteCarlo}
                          currentPrice={parseFloat(prediction.currentPrice)}
                          symbol={prediction.symbol}
                        />
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

            {/* ── Right column ──────────────────────────────────────────── */}
            <Grid size={{ xs: 12, lg: 4 }}>
              {loading ? <SidebarSkeleton /> : (
                <Stack spacing={3}>
                  {prediction && (
                    <FundamentalsPanel
                      prediction={prediction}
                      rsiInfo={rsiInfo}
                      isDark={isDark}
                      primaryColor={primaryColor}
                    />
                  )}

                  {/* ── Peer Comparison ──────────────────────────────────── */}
                  {prediction && (
                    <PeerComparisonPanel
                      baseSymbol={prediction.symbol}
                      isDark={isDark}
                      primaryColor={primaryColor}
                    />
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

        {/* ── Chat panel + FAB ───────────────────────────────────── */}
        {prediction && (
          <>
            <StockChatPanel
              key={prediction.symbol}
              prediction={prediction}
              isDark={isDark}
              primaryColor={primaryColor}
              open={chatOpen}
              onClose={() => setChatOpen(false)}
            />
            <Fab
              onClick={() => setChatOpen(o => !o)}
              size="medium"
              aria-label={chatOpen ? 'Close chat' : 'Open chat'}
              sx={{
                position: 'fixed', bottom: 24, right: 24,
                background: primaryColor,
                '&:hover': { background: primaryColor, filter: 'brightness(1.15)' },
                boxShadow: `0 0 20px ${primaryColor}66`,
              }}
            >
              <MessageCircle color="#000" size={22} />
            </Fab>
          </>
        )}
      </Box>
    </ThemeProvider>
  );
}
