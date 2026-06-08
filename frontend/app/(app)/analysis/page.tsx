"use client";

import React, { useState, useMemo, useEffect, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import axios from 'axios';
import {
  Box, Container, Typography, TextField, Button, Card, CardContent,
  Grid, CircularProgress, Alert, Paper, Chip, Stack, MenuItem, Select, Avatar, Link,
  Skeleton, IconButton, Autocomplete, Fab,
} from '@mui/material';
import {
  Search, BrainCircuit, Newspaper, BarChart2, MessageCircle,
  Star, StarOff,
} from 'lucide-react';
import AuthGate from '../../../components/AuthGate';
import { useWatchlist } from '../../../hooks/useWatchlist';
import { useAuth } from '../../../contexts/AuthContext';
import { useAppShell } from '../../../contexts/AppShellContext';
import AuthModal from '../../../components/AuthModal';
import ModelWeightBar   from '../../../components/ModelWeightBar';
import BacktestPanel    from '../../../components/BacktestPanel';
import TrendingSparklines from '../../../components/TrendingSparklines';
import MonteCarloFanChart from '../../../components/MonteCarloFanChart';
import MonteCarloProbabilitySurface from '../../../components/MonteCarloProbabilitySurface';
import ConfidenceBadge   from '../../../components/ConfidenceBadge';
import { ChartSkeleton, SidebarSkeleton } from '../../../components/Skeletons';
import AnalystJuryPanel  from '../../../components/AnalystJuryPanel';
import PriceChartCard    from '../../../components/PriceChartCard';
import FundamentalsPanel      from '../../../components/FundamentalsPanel';
import PeerComparisonPanel    from '../../../components/PeerComparisonPanel';
import TradeSetupCard         from '../../../components/TradeSetupCard';
import OrderBookPanel    from '../../../components/OrderBookPanel';
import StockChatPanel    from '../../../components/StockChatPanel';
import { useIndicatorSignals } from '../../../hooks/useIndicatorSignals';
import DCFCard               from '../../../components/DCFCard';
import WhyDidMoveCard        from '../../../components/WhyDidMoveCard';
import MorningBriefingPanel  from '../../../components/MorningBriefingPanel';
import type { PredictionData, IndicatorKey, TradeSetupResponse, DCFResult } from '../../../types';

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

// ── Analysis content ────────────────────────────────────────────────────────────

function AnalysisContent() {
  const { isDark, primaryColor } = useAppShell();
  const router        = useRouter();
  const searchParams  = useSearchParams();
  const symbolFromUrl = searchParams.get('symbol');
  // Base ticker (no exchange suffix) most recently fetched — guards the URL-sync
  // effect below so a programmatic router.replace doesn't re-trigger a fetch.
  const lastLoadedRef = useRef<string | null>(null);

  const [ticker,           setTicker]           = useState('NVDA');
  const [exchange,         setExchange]         = useState('');
  const [prediction,       setPrediction]       = useState<PredictionData | null>(null);
  const [loading,          setLoading]          = useState(false);
  const [error,            setError]            = useState<string | null>(null);
  const [indicators,       setIndicators]       = useState<IndicatorKey[]>(['bb', 'sma']);
  const [chartMode,        setChartMode]        = useState<'line' | 'candle'>('line');
  const [tradeSetup,       setTradeSetup]       = useState<TradeSetupResponse | null>(null);
  const [tradeSetupLoading, setTradeSetupLoading] = useState(false);
  const [dcfData,          setDcfData]          = useState<DCFResult | null>(null);
  const [chatOpen,         setChatOpen]         = useState(false);
  const [authOpen,         setAuthOpen]         = useState(false);

  const { user, session } = useAuth();
  const { watchlist, currentIsSaved, toggle: toggleWatchlist, toggling: watchlistToggling } = useWatchlist(prediction?.symbol ?? ticker);

  const authHeaders = session?.access_token
    ? { Authorization: `Bearer ${session.access_token}` }
    : {};

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
      var_95:          data.monteCarlo?.var_95 ?? null,
    }, { headers: authHeaders })
      .then(r  => setTradeSetup(r.data))
      .catch(() => { /* non-fatal */ })
      .finally(() => setTradeSetupLoading(false));
  };

  const handlePredict = async (overrideSymbol?: string) => {
    // Determine the full symbol (may carry an exchange suffix, e.g. "AAPL:NASDAQ").
    let fullSymbol: string;
    if (overrideSymbol) {
      const upper = overrideSymbol.toUpperCase();
      const [sym, exch] = upper.split(':');
      setTicker(sym);
      if (exch) setExchange(exch);
      fullSymbol = upper;
    } else {
      fullSymbol = exchange ? `${ticker}:${exchange}` : ticker;
    }
    const baseSymbol = fullSymbol.split(':')[0];
    // Record before fetching so the router.replace below (which changes the URL,
    // and therefore symbolFromUrl) doesn't bounce back into a duplicate fetch.
    lastLoadedRef.current = baseSymbol;

    setLoading(true);
    setError(null);
    setTradeSetup(null);
    setDcfData(null);
    setChatOpen(false);
    try {
      const response = await axios.post('/api/predict', { data: fullSymbol }, { headers: authHeaders });
      setPrediction(response.data);
      // Persist the ticker in the URL so the view is shareable, reload-safe, and
      // back/forward navigable. scroll:false keeps the current scroll position.
      router.replace(`/analysis?symbol=${encodeURIComponent(baseSymbol)}`, { scroll: false });
      if (user) {
        fetchTradeSetup(response.data);
      } else {
        setTradeSetup(null);
      }
      // Fire-and-forget DCF fetch (non-blocking)
      axios.get(`/api/dcf/${baseSymbol}`)
        .then(r => setDcfData(r.data))
        .catch(() => setDcfData(null));
    } catch (err: any) {
      setError(err.response?.data?.error || 'Analysis failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Auto-trigger analysis when the ?symbol= query changes — on first load (e.g.
  // from the landing search) and on browser back/forward. Skips the case where
  // the change came from our own router.replace after a fetch (guarded by ref).
  useEffect(() => {
    if (symbolFromUrl && symbolFromUrl.toUpperCase() !== lastLoadedRef.current) {
      handlePredict(symbolFromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbolFromUrl]);

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

  const trendColor   = chartStats?.color ?? (isDark ? '#2de2e6' : '#1e3a8a');

  const indicatorSignals = useIndicatorSignals(prediction, isDark, chartStats);

  const priceChangePct = useMemo(() => {
    if (!prediction) return 0;
    const cur  = parseFloat(prediction.currentPrice) || 0;
    const prev = parseFloat(prediction.metrics?.prev_close ?? '') || 0;
    return prev > 0 ? ((cur - prev) / prev) * 100 : 0;
  }, [prediction]);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <Box>
      <Container maxWidth="xl" disableGutters>

        {/* ── Search bar ──────────────────────────────────────────────── */}
        <Stack direction="row" justifyContent="flex-end" sx={{ mb: 4 }}>
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
              onClick={() => handlePredict()}
              disabled={loading}
              sx={{ borderRadius: 3, minWidth: 50, py: 1, boxShadow: `0 0 20px ${primaryColor}4d` }}
            >
              {loading ? <CircularProgress size={20} color="inherit" /> : <Search size={20} />}
            </Button>
            {user && prediction && (
              <IconButton
                size="small"
                onClick={() => void toggleWatchlist(prediction.symbol)}
                disabled={watchlistToggling}
                aria-label={currentIsSaved ? 'Remove from watchlist' : 'Save to watchlist'}
                title={currentIsSaved ? 'Remove from watchlist' : 'Save to watchlist'}
                sx={{ color: currentIsSaved ? '#f59e0b' : 'text.secondary' }}
              >
                {currentIsSaved ? <Star size={18} fill="#f59e0b" /> : <StarOff size={18} />}
              </IconButton>
            )}
          </Paper>
        </Stack>

        {/* ── Market Pulse (always visible) ───────────────────────── */}
        <MorningBriefingPanel isDark={isDark} primaryColor={primaryColor} />

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
                  symbol={prediction.symbol}
                  indicators={indicators}
                  setIndicators={setIndicators}
                  chartMode={chartMode}
                  setChartMode={setChartMode}
                  isDark={isDark}
                  primaryColor={primaryColor}
                  trendColor={trendColor}
                  chartStats={chartStats}
                  indicatorSignals={indicatorSignals}
                />

                {/* ── Why did this move? ───────────────────────────── */}
                {prediction.moveExplanation && (
                  <WhyDidMoveCard
                    symbol={prediction.symbol}
                    explanation={prediction.moveExplanation}
                    priceChange={priceChangePct}
                    isDark={isDark}
                    primaryColor={primaryColor}
                  />
                )}

                {/* ── Ensemble model weights ───────────────────────── */}
                {prediction.modelWeights && (
                  <ModelWeightBar weights={prediction.modelWeights} isDark={isDark} />
                )}

                {/* ── Walk-forward backtest (on-demand) ────────────── */}
                <BacktestPanel symbol={prediction.symbol} isDark={isDark} primaryColor={primaryColor} />

                {/* ── Analyst Jury ──────────────────────────────────── */}
                {prediction.juryAnalysts && prediction.juryAnalysts.length > 0 && (
                  <AnalystJuryPanel analysts={prediction.juryAnalysts} symbol={prediction.symbol} />
                )}

                {/* ── Trade Setup ──────────────────────────────────── */}
                {user ? (
                  <TradeSetupCard
                    setup={tradeSetup}
                    loading={tradeSetupLoading}
                    isDark={isDark}
                    primaryColor={primaryColor}
                  />
                ) : (
                  <AuthGate
                    title="Trade Setup"
                    message="Sign in to see entry zones, stop levels, and position sizing."
                    onSignIn={() => setAuthOpen(true)}
                    isDark={isDark}
                    primaryColor={primaryColor}
                  />
                )}

                {/* ── Price Forecast ────────────────────────────────── */}
                {prediction.forecastDays?.length > 0 && (
                  <Card>
                    <CardContent>
                      <Typography variant="overline" sx={{ opacity: 0.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <BarChart2 size={14} /> Price Forecast
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

                {/* ── DCF Intrinsic Value ───────────────────────────── */}
                {dcfData && (
                  <DCFCard
                    dcf={dcfData}
                    isDark={isDark}
                    primaryColor={primaryColor}
                  />
                )}

              </Stack>
            ) : (
              <Box sx={{ height: '60vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, opacity: 0.2 }}>
                <BrainCircuit size={52} color={primaryColor} />
                <Typography variant="h6" sx={{ fontWeight: 300, letterSpacing: 3 }}>Enter a ticker above to begin</Typography>
              </Box>
            )}
          </Grid>

          {/* ── Right column ──────────────────────────────────────────── */}
          <Grid size={{ xs: 12, lg: 4 }}>
            <Stack spacing={3}>
            {loading ? <SidebarSkeleton /> : (
              <>

                {/* ── Watchlist ─────────────────────────────────────── */}
                {user && watchlist.length > 0 && (
                  <Paper sx={{
                    p: 2,
                    border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'}`,
                  }}>
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                      <Star size={14} color="#f59e0b" fill="#f59e0b" />
                      <Typography variant="overline" sx={{ opacity: 0.6, lineHeight: 1 }}>
                        Watchlist
                      </Typography>
                    </Stack>
                    <Stack direction="row" flexWrap="wrap" gap={0.75}>
                      {watchlist.map(sym => (
                        <Chip
                          key={sym}
                          label={sym}
                          size="small"
                          onClick={() => handlePredict(sym)}
                          onDelete={() => void toggleWatchlist(sym)}
                          sx={{
                            cursor: 'pointer',
                            fontWeight: 700,
                            fontSize: 11,
                            bgcolor: isDark ? 'rgba(245,158,11,0.1)' : 'rgba(245,158,11,0.15)',
                            color: '#f59e0b',
                            '& .MuiChip-deleteIcon': { color: '#f59e0b', opacity: 0.5, '&:hover': { opacity: 1 } },
                          }}
                        />
                      ))}
                    </Stack>
                  </Paper>
                )}

                {prediction && (
                  <FundamentalsPanel
                    prediction={prediction}
                    rsiInfo={rsiInfo}
                    isDark={isDark}
                    primaryColor={primaryColor}
                  />
                )}

                {/* ── Level 2 Order Book ───────────────────────────── */}
                {prediction && (
                  <OrderBookPanel symbol={prediction.symbol} />
                )}

                {/* ── Peer Comparison ──────────────────────────────────── */}
                {prediction && (
                  <PeerComparisonPanel
                    baseSymbol={prediction.symbol}
                    isDark={isDark}
                    primaryColor={primaryColor}
                  />
                )}

                {/* ── Market Intelligence ──────────────────────────────── */}
                {prediction && (
                  prediction.news?.length > 0 ||
                  (prediction.stocktwits?.bullish ?? 0) + (prediction.stocktwits?.bearish ?? 0) > 0 ||
                  (prediction.sentiment?.headline_count ?? 0) > 0
                ) && prediction && (
                  <>
                    <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1 }}>
                      <Newspaper size={20} /> Market Intelligence
                    </Typography>

                    {prediction.sentiment && prediction.sentiment.headline_count > 0 && (
                      <Stack direction="row" flexWrap="wrap" alignItems="center" gap={1} sx={{ px: 1 }}>
                        <Chip
                          label={`Sentiment: ${prediction.sentiment.label} (${prediction.sentiment.compound >= 0 ? '+' : ''}${prediction.sentiment.compound.toFixed(3)})`}
                          size="small"
                          sx={{
                            fontWeight: 700,
                            bgcolor: prediction.sentiment.label === 'Bullish'
                              ? (isDark ? 'rgba(0,255,163,0.15)' : 'rgba(22,163,74,0.15)')
                              : prediction.sentiment.label === 'Bearish'
                              ? (isDark ? 'rgba(255,0,85,0.15)' : 'rgba(220,38,38,0.15)')
                              : undefined,
                            color: prediction.sentiment.label === 'Bullish'
                              ? (isDark ? '#00ffa3' : '#16a34a')
                              : prediction.sentiment.label === 'Bearish'
                              ? (isDark ? '#ff0055' : '#dc2626')
                              : 'text.secondary',
                          }}
                        />
                        <Typography variant="caption" sx={{ opacity: 0.5 }}>
                          {prediction.sentiment.headline_count} headlines scored
                        </Typography>
                        {prediction.stocktwits &&
                          (prediction.stocktwits.bullish + prediction.stocktwits.bearish) > 0 && (
                          <>
                            <Typography variant="caption" sx={{ opacity: 0.3, mx: 0.5 }}>·</Typography>
                            <Chip
                              label={`↑ ${prediction.stocktwits.bullish}`}
                              size="small"
                              sx={{ bgcolor: isDark ? 'rgba(0,255,163,0.12)' : 'rgba(22,163,74,0.12)', color: isDark ? '#00ffa3' : '#16a34a', fontWeight: 700 }}
                            />
                            <Chip
                              label={`↓ ${prediction.stocktwits.bearish}`}
                              size="small"
                              sx={{ bgcolor: isDark ? 'rgba(255,0,85,0.12)' : 'rgba(220,38,38,0.12)', color: isDark ? '#ff0055' : '#dc2626', fontWeight: 700 }}
                            />
                            <Typography variant="caption" sx={{ opacity: 0.5 }}>StockTwits</Typography>
                          </>
                        )}
                      </Stack>
                    )}

                    <Grid container spacing={2}>
                      {prediction.news.map((item, i) => (
                        <Grid size={12} key={i}>
                          <Card sx={{ background: 'transparent' }}>
                            <CardContent sx={{ display: 'flex', gap: 2, p: '16px !important' }}>
                              {item.thumbnail && <Avatar src={item.thumbnail} variant="rounded" sx={{ width: 60, height: 60 }} />}
                              <Box sx={{ flex: 1, minWidth: 0 }}>
                                {item.link ? (
                                  <Link href={item.link} target="_blank" rel="noopener noreferrer" underline="none" sx={{ '&:hover': { color: 'primary.main' } }}>
                                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{item.title}</Typography>
                                  </Link>
                                ) : (
                                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{item.title}</Typography>
                                )}
                                <Stack direction="row" alignItems="center" gap={0.75} sx={{ mt: 0.5, flexWrap: 'wrap' }}>
                                  <Typography variant="caption" sx={{ color: 'primary.main' }}>{item.source}</Typography>
                                  {item.date && <Typography variant="caption" sx={{ opacity: 0.5 }}>{item.date}</Typography>}
                                  {item.source_label && (
                                    <Chip
                                      label={item.source_label}
                                      size="small"
                                      sx={{ height: 16, fontSize: 9, fontWeight: 700, opacity: 0.6, '& .MuiChip-label': { px: 0.75 } }}
                                    />
                                  )}
                                </Stack>
                              </Box>
                            </CardContent>
                          </Card>
                        </Grid>
                      ))}
                    </Grid>
                  </>
                )}

                {/* ── Trending Sparklines (real 5-day) ─────────────────── */}
                {prediction?.trending?.length > 0 && (
                  <TrendingSparklines tickers={prediction.trending} isDark={isDark} />
                )}

              </>
            )}
            </Stack>
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
            onClick={() => user ? setChatOpen(o => !o) : setAuthOpen(true)}
            size="medium"
            aria-label={user ? (chatOpen ? 'Close chat' : 'Open AI chat') : 'Sign in to open AI chat'}
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

      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
    </Box>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense fallback={
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 10 }}>
        <CircularProgress />
      </Box>
    }>
      <AnalysisContent />
    </Suspense>
  );
}
