"use client";

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import axios from 'axios';
import {
  Box, Container, Typography, TextField, Button, Card, CardContent,
  Grid, CircularProgress, Alert, Paper, Stack, Autocomplete, Skeleton, Chip,
} from '@mui/material';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, ReferenceLine, Cell, Legend,
} from 'recharts';
import { Activity, Search, Target, TrendingUp, Gauge, ShieldCheck } from 'lucide-react';
import { useAppShell } from '../../../contexts/AppShellContext';
import type { AccuracyAnalytics, SentimentAnalytics, SentimentPoint, CalibrationReport } from '../../../types';

// ── Constants ────────────────────────────────────────────────────────────────

const POPULAR_TICKERS = [
  'AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK.B','JPM','V',
  'UNH','MA','XOM','LLY','JNJ','PG','HD','MRK','AVGO','CVX',
  'KO','PEP','ABBV','COST','MCD','CSCO','TMO','WMT','ACN','ABT',
  'SPY','QQQ','DIA','IWM','GLD','SLV','TLT','BTC-USD','ETH-USD',
];

const MODEL_LABELS: Record<string, string> = {
  prophet:       'Prophet',
  sarima:        'SARIMA',
  random_forest: 'Random Forest',
  ensemble:      'Ensemble',
};

function sentimentColor(label: string, isDark: boolean): string {
  if (label === 'Bullish') return isDark ? '#00ffa3' : '#16a34a';
  if (label === 'Bearish') return isDark ? '#ff0055' : '#dc2626';
  return isDark ? '#94a3b8' : '#64748b';
}

// ── Insights content ───────────────────────────────────────────────────────────

function InsightsContent() {
  const { isDark, primaryColor } = useAppShell();
  const router       = useRouter();
  const searchParams = useSearchParams();
  const symbolFromUrl = searchParams.get('symbol');

  const [ticker,    setTicker]    = useState('');
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [accuracy,  setAccuracy]  = useState<AccuracyAnalytics | null>(null);
  const [sentiment, setSentiment] = useState<SentimentAnalytics | null>(null);
  const [calibration, setCalibration] = useState<CalibrationReport | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const axisColor = isDark ? '#94a3b8' : '#64748b';

  // Tracks the most recently requested symbol so a slow in-flight calibration
  // response from an older ticker can't overwrite the current card.
  const latestSymbolRef = useRef<string | null>(null);

  const fetchInsights = useCallback(async (raw: string) => {
    const sym = raw.trim().toUpperCase().split(':')[0];
    if (!sym) return;
    latestSymbolRef.current = sym;
    setSubmitted(sym);
    setLoading(true);
    setError(null);
    setAccuracy(null);
    setSentiment(null);
    setCalibration(null);
    router.replace(`/insights?symbol=${encodeURIComponent(sym)}`, { scroll: false });
    // Calibration is a read-only add-on — fetch it best-effort so a failure
    // there never blocks the core accuracy + sentiment views. Drop the result
    // if a newer search has since started (stale-response guard).
    axios.get(`/api/analytics/calibration/${sym}`)
      .then(res => { if (latestSymbolRef.current === sym) setCalibration(res.data); })
      .catch(() => { if (latestSymbolRef.current === sym) setCalibration(null); });
    try {
      const [accRes, sentRes] = await Promise.all([
        axios.get(`/api/analytics/accuracy/${sym}`),
        axios.get(`/api/analytics/sentiment/${sym}`),
      ]);
      setAccuracy(accRes.data);
      setSentiment(sentRes.data);
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err)
        ? (err.response?.data?.error ?? err.message)
        : 'Failed to load insights.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [router]);

  // Auto-load when arriving with ?symbol= (shareable / reload-safe).
  useEffect(() => {
    if (symbolFromUrl && symbolFromUrl.toUpperCase() !== submitted) {
      setTicker(symbolFromUrl.toUpperCase());
      fetchInsights(symbolFromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbolFromUrl]);

  const hasData = !!accuracy && (
    accuracy.samples > 0 ||
    Object.keys(accuracy.model_mae).length > 0 ||
    accuracy.ensemble_mae_by_horizon.length > 0
  );
  const hasCalibration = !!calibration && calibration.samples > 0;

  // ── Derived chart data ───────────────────────────────────────────────────────
  const modelMaeData = accuracy
    ? Object.entries(accuracy.model_mae)
        .map(([model, mae]) => ({
          model: MODEL_LABELS[model] ?? model,
          key: model,
          mae,
          skill: accuracy.model_skill?.[model as keyof typeof accuracy.model_skill] ?? null,
        }))
        .sort((a, b) => a.mae - b.mae)
    : [];

  const dirCards = accuracy
    ? (['prophet', 'sarima', 'random_forest', 'ensemble'] as const)
        .map(k => ({ key: k, label: MODEL_LABELS[k], value: accuracy.directional_accuracy[k] ?? null }))
    : [];

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <Box>
      <Container maxWidth="xl" disableGutters>

        {/* ── Header + search ──────────────────────────────────────────── */}
        <Stack direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'center' }} justifyContent="space-between" gap={2} sx={{ mb: 4 }}>
          <Stack direction="row" alignItems="center" gap={1.5}>
            <Activity size={28} color={primaryColor} />
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>Insights</Typography>
              <Typography variant="body2" sx={{ opacity: 0.6 }}>Forecast accuracy &amp; sentiment trend</Typography>
            </Box>
          </Stack>

          <Paper sx={{
            p: 0.5, display: 'flex', gap: 1, alignItems: 'center',
            width: { xs: '100%', md: 420 },
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
                  onKeyDown={e => e.key === 'Enter' && fetchInsights(ticker)}
                  InputProps={{ ...params.InputProps, disableUnderline: true, sx: { px: 2, fontWeight: 700 } }}
                />
              )}
            />
            <Button
              variant="contained"
              onClick={() => fetchInsights(ticker)}
              disabled={loading || !ticker.trim()}
              sx={{ borderRadius: 3, minWidth: 50, py: 1, boxShadow: `0 0 20px ${primaryColor}4d` }}
            >
              {loading ? <CircularProgress size={20} color="inherit" /> : <Search size={20} />}
            </Button>
          </Paper>
        </Stack>

        {error && <Alert severity="error" sx={{ mb: 4, borderRadius: 3 }}>{error}</Alert>}

        {/* ── Loading skeletons ─────────────────────────────────────────── */}
        {loading && (
          <Grid container spacing={3}>
            {[0, 1, 2, 3].map(i => (
              <Grid size={{ xs: 12, md: 6 }} key={i}>
                <Skeleton variant="rectangular" height={300} sx={{ borderRadius: 3 }} />
              </Grid>
            ))}
          </Grid>
        )}

        {/* ── Pre-search empty state ────────────────────────────────────── */}
        {!loading && !submitted && (
          <Box sx={{ height: '55vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, opacity: 0.25, textAlign: 'center', px: 3 }}>
            <Activity size={52} color={primaryColor} />
            <Typography variant="h6" sx={{ fontWeight: 300, letterSpacing: 1 }}>
              Search a ticker to see its forecast accuracy and sentiment trend
            </Typography>
          </Box>
        )}

        {/* ── No-data empty state (searched, but no history yet) ─────────── */}
        {!loading && submitted && accuracy && !hasData && !hasCalibration && (!sentiment || sentiment.history.length === 0) && (
          <Box sx={{ height: '45vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, opacity: 0.4, textAlign: 'center', px: 3 }}>
            <Gauge size={48} color={primaryColor} />
            <Typography variant="h6" sx={{ fontWeight: 400 }}>No accuracy history yet for {submitted}</Typography>
            <Typography variant="body2" sx={{ maxWidth: 460, opacity: 0.8 }}>
              Forecast accuracy accumulates as predictions resolve against real closes. Run a few analyses
              for {submitted} over the coming days and its scorecard will fill in here.
            </Typography>
          </Box>
        )}

        {/* ── Charts ────────────────────────────────────────────────────── */}
        {!loading && submitted && (hasData || hasCalibration || (sentiment && sentiment.history.length > 0)) && (
          <Grid container spacing={3}>

            {/* 0. Forecast calibration audit (Feature 30) */}
            {calibration && (
              <Grid size={12}>
                <CalibrationSection report={calibration} isDark={isDark} primaryColor={primaryColor} />
              </Grid>
            )}

            {/* 1. Model performance ranking (MAE, lower = better) */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Target size={14} /> Model Performance · MAE (lower is better)
                  </Typography>
                  {modelMaeData.length > 0 ? (
                    <>
                      <ResponsiveContainer width="100%" height={240}>
                        <BarChart layout="vertical" data={modelMaeData} margin={{ top: 16, right: 32, bottom: 0, left: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
                          <XAxis type="number" stroke={axisColor} tick={{ fontSize: 12 }} />
                          <YAxis type="category" dataKey="model" stroke={axisColor} tick={{ fontSize: 12 }} width={90} />
                          <Tooltip
                            contentStyle={{ background: isDark ? '#0f172a' : '#fff', border: `1px solid ${gridColor}`, borderRadius: 8 }}
                            formatter={(v: number, _n: string, props: { payload?: { skill: number | null } }) => {
                              const skill = props.payload?.skill;
                              const skillStr = skill != null
                                ? `  (skill: ${skill >= 0 ? '+' : ''}${Math.round(skill * 100)}%)`
                                : '';
                              return [`$${v.toFixed(2)}${skillStr}`, 'MAE'];
                            }}
                          />
                          {accuracy?.naive_mae != null && (
                            <ReferenceLine
                              x={accuracy.naive_mae}
                              stroke={isDark ? '#f59e0b' : '#d97706'}
                              strokeDasharray="4 4"
                              label={{ value: `Naive $${accuracy.naive_mae}`, fill: isDark ? '#f59e0b' : '#d97706', fontSize: 10, position: 'insideTopRight' }}
                            />
                          )}
                          <Bar dataKey="mae" radius={[0, 6, 6, 0]}>
                            {modelMaeData.map(d => (
                              <Cell key={d.key} fill={accuracy && d.key === accuracy.best_model ? (isDark ? '#00ffa3' : '#16a34a') : primaryColor} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                      {accuracy?.best_model && (
                        <Typography variant="caption" sx={{ opacity: 0.7 }}>
                          Most accurate: <strong style={{ color: isDark ? '#00ffa3' : '#16a34a' }}>{MODEL_LABELS[accuracy.best_model]}</strong>
                          {' · '}{accuracy.samples} resolved sample{accuracy.samples === 1 ? '' : 's'}
                        </Typography>
                      )}
                      {/* Skill score chips — how much each model beats naive persistence */}
                      {accuracy?.model_skill && Object.keys(accuracy.model_skill).length > 0 && (
                        <Stack direction="row" spacing={0.5} sx={{ mt: 1, flexWrap: 'wrap', gap: 0.5 }}>
                          {modelMaeData.map(d => {
                            if (d.skill == null) return null;
                            const pct = Math.round(d.skill * 100);
                            const col = pct > 0 ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff6b6b' : '#dc2626');
                            return (
                              <Chip
                                key={d.key}
                                size="small"
                                label={`${d.model}: ${pct >= 0 ? '+' : ''}${pct}% vs naive`}
                                sx={{ fontSize: 11, height: 22, color: col, bgcolor: `${col}1a`, fontWeight: 600 }}
                              />
                            );
                          })}
                        </Stack>
                      )}
                    </>
                  ) : <EmptyChart label="No per-model accuracy yet" isDark={isDark} />}
                </CardContent>
              </Card>
            </Grid>

            {/* 2. Ensemble MAE by horizon */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Gauge size={14} /> Ensemble Confidence by Horizon
                  </Typography>
                  {accuracy && accuracy.ensemble_mae_by_horizon.length > 0 ? (
                    <ResponsiveContainer width="100%" height={240}>
                      <BarChart data={accuracy.ensemble_mae_by_horizon} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                        <XAxis dataKey="horizon" stroke={axisColor} tick={{ fontSize: 12 }} />
                        <YAxis stroke={axisColor} tick={{ fontSize: 12 }} />
                        <Tooltip
                          contentStyle={{ background: isDark ? '#0f172a' : '#fff', border: `1px solid ${gridColor}`, borderRadius: 8 }}
                          formatter={(v: number) => [`$${v.toFixed(2)}`, 'MAE']}
                        />
                        <Bar dataKey="mae" fill={primaryColor} radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : <EmptyChart label="No horizon accuracy yet" isDark={isDark} />}
                  <Typography variant="caption" sx={{ opacity: 0.55 }}>
                    Error typically grows from d1→d5 — confidence decays with horizon.
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            {/* 3. Directional accuracy stat cards */}
            <Grid size={12}>
              <Card>
                <CardContent>
                  <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                    <TrendingUp size={14} /> Directional Accuracy (correct up/down calls)
                  </Typography>
                  <Grid container spacing={2}>
                    {dirCards.map(({ key, label, value }) => {
                      const pct = value === null ? null : Math.round(value * 100);
                      const col = pct === null ? axisColor : pct >= 50 ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626');
                      return (
                        <Grid size={{ xs: 6, md: 3 }} key={key}>
                          <Box sx={{ p: 2, borderRadius: 2, textAlign: 'center', border: `1px solid ${col}33`, background: `${col}0d` }}>
                            <Typography sx={{ fontSize: 12, opacity: 0.6, mb: 0.5 }}>{label}</Typography>
                            <Typography sx={{ fontSize: '1.7rem', fontWeight: 800, color: col }}>
                              {pct === null ? '—' : `${pct}%`}
                            </Typography>
                          </Box>
                        </Grid>
                      );
                    })}
                  </Grid>
                </CardContent>
              </Card>
            </Grid>

            {/* 4. Forecast vs Actual */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Target size={14} /> Forecast vs Actual (d1 ensemble)
                  </Typography>
                  {accuracy && accuracy.forecast_vs_actual.length > 0 ? (
                    <ResponsiveContainer width="100%" height={260}>
                      <LineChart data={accuracy.forecast_vs_actual} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                        <XAxis dataKey="date" stroke={axisColor} tick={{ fontSize: 11 }} minTickGap={24} />
                        <YAxis stroke={axisColor} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
                        <Tooltip
                          contentStyle={{ background: isDark ? '#0f172a' : '#fff', border: `1px solid ${gridColor}`, borderRadius: 8 }}
                          formatter={(v: number, n: string) => [`$${v.toFixed(2)}`, n]}
                        />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Line type="monotone" dataKey="forecast" name="Forecast" stroke={primaryColor} strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="actual" name="Actual" stroke={isDark ? '#f59e0b' : '#d97706'} strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : <EmptyChart label="No resolved forecasts yet" isDark={isDark} />}
                </CardContent>
              </Card>
            </Grid>

            {/* 5. Sentiment trend */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Activity size={14} /> Sentiment Trend · 30 days
                    {sentiment?.current && (
                      <Chip
                        size="small"
                        label={`${sentiment.current.label} (${sentiment.current.compound >= 0 ? '+' : ''}${sentiment.current.compound.toFixed(2)})`}
                        sx={{ ml: 'auto', fontWeight: 700, height: 22, color: sentimentColor(sentiment.current.label, isDark), bgcolor: `${sentimentColor(sentiment.current.label, isDark)}1a` }}
                      />
                    )}
                  </Typography>
                  {sentiment && sentiment.history.length > 0 ? (
                    <ResponsiveContainer width="100%" height={260}>
                      <LineChart data={sentiment.history} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                        <XAxis dataKey="date" stroke={axisColor} tick={{ fontSize: 11 }} minTickGap={24} />
                        <YAxis stroke={axisColor} tick={{ fontSize: 11 }} domain={[-1, 1]} />
                        <Tooltip
                          contentStyle={{ background: isDark ? '#0f172a' : '#fff', border: `1px solid ${gridColor}`, borderRadius: 8 }}
                          formatter={(v: number, _n, p) => [`${v >= 0 ? '+' : ''}${v.toFixed(3)}`, (p?.payload as SentimentPoint)?.label ?? 'Sentiment']}
                        />
                        <ReferenceLine y={0} stroke={axisColor} strokeDasharray="2 2" />
                        <Line
                          type="monotone" dataKey="compound" name="Compound"
                          stroke={primaryColor} strokeWidth={2}
                          dot={(props) => {
                            const { cx, cy, payload, index } = props as { cx: number; cy: number; payload: SentimentPoint; index: number };
                            return <circle key={index} cx={cx} cy={cy} r={3} fill={sentimentColor(payload.label, isDark)} />;
                          }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : <EmptyChart label="No sentiment history yet" isDark={isDark} />}
                </CardContent>
              </Card>
            </Grid>

          </Grid>
        )}
      </Container>
    </Box>
  );
}

// ── Calibration audit section (Feature 30) ──────────────────────────────────────

const VERDICT_META: Record<string, { label: string; tone: 'good' | 'bad' | 'warn'; blurb: string }> = {
  well_calibrated: { label: 'Well Calibrated', tone: 'good', blurb: 'Realized prices land inside the forecast band about as often as they should.' },
  overconfident:   { label: 'Overconfident',   tone: 'bad',  blurb: 'Bands are too tight — prices escape the range more often than expected.' },
  underconfident:  { label: 'Underconfident',  tone: 'warn', blurb: 'Bands are too wide — prices almost always land inside, so the range is uninformative.' },
};

function CalibrationSection({ report, isDark, primaryColor }: { report: CalibrationReport; isDark: boolean; primaryColor: string }) {
  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';
  const amber = isDark ? '#f59e0b' : '#d97706';
  const axis  = isDark ? '#94a3b8' : '#64748b';

  const coverage = report.p10_p90_coverage_pct ?? report.range_coverage_pct;
  const target   = report.coverage_target_pct ?? 80;
  const verdict  = report.calibration_verdict;
  const meta     = verdict ? VERDICT_META[verdict] : null;
  const toneColor = (t: 'good' | 'bad' | 'warn') => (t === 'good' ? green : t === 'bad' ? red : amber);

  // Insufficient history → reuse the page's samples-too-thin empty pattern.
  if (!meta || coverage === null) {
    return (
      <Card>
        <CardContent>
          <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1 }}>
            <ShieldCheck size={14} /> Forecast Calibration · should I trust this forecast?
          </Typography>
          <Box sx={{ py: 4, textAlign: 'center', opacity: 0.6 }}>
            <Typography variant="body2" sx={{ maxWidth: 520, mx: 'auto' }}>
              Not enough resolved forecasts yet to audit calibration
              {report.samples ? ` (${report.samples} so far)` : ''}. Coverage, directional edge,
              and bias appear once more predictions resolve against real closes.
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  const coverageColor = toneColor(meta.tone);
  const edge = report.edge_pct;
  const dir  = report.directional_accuracy_pct;
  const naive = report.naive_accuracy_pct;
  const bias = report.mean_signed_error;

  const clampPct = (v: number) => Math.max(0, Math.min(100, v));

  return (
    <Card>
      <CardContent>
        <Stack direction={{ xs: 'column', sm: 'row' }} alignItems={{ sm: 'center' }} justifyContent="space-between" gap={1} sx={{ mb: 2 }}>
          <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1 }}>
            <ShieldCheck size={14} /> Forecast Calibration · should I trust this forecast?
          </Typography>
          <Chip
            label={meta.label}
            sx={{ fontWeight: 800, color: coverageColor, bgcolor: `${coverageColor}1a`, border: `1px solid ${coverageColor}55` }}
          />
        </Stack>

        <Grid container spacing={3}>
          {/* Coverage gauge — actual vs 80% target */}
          <Grid size={{ xs: 12, md: 6 }}>
            <Typography variant="caption" sx={{ opacity: 0.7 }}>
              Band coverage — % of realized prices inside the forecast range
            </Typography>
            <Stack direction="row" alignItems="baseline" gap={1} sx={{ mt: 0.5, mb: 1.5 }}>
              <Typography sx={{ fontSize: '2.4rem', fontWeight: 800, color: coverageColor, lineHeight: 1 }}>
                {coverage.toFixed(0)}%
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.6 }}>vs {target.toFixed(0)}% target</Typography>
            </Stack>

            {/* Track + fill + target marker */}
            <Box sx={{ position: 'relative', height: 16, borderRadius: 8, bgcolor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)' }}>
              <Box sx={{ width: `${clampPct(coverage)}%`, height: '100%', borderRadius: 8, bgcolor: coverageColor, transition: 'width .4s ease' }} />
              <Box sx={{ position: 'absolute', left: `${clampPct(target)}%`, top: -3, bottom: -3, width: 2, bgcolor: axis }} />
              <Box sx={{ position: 'absolute', left: `${clampPct(target)}%`, top: -18, transform: 'translateX(-50%)' }}>
                <Typography variant="caption" sx={{ color: axis, fontWeight: 600, whiteSpace: 'nowrap' }}>{target.toFixed(0)}%</Typography>
              </Box>
            </Box>
            <Typography variant="caption" sx={{ opacity: 0.6, display: 'block', mt: 2 }}>{meta.blurb}</Typography>
            <Typography variant="caption" sx={{ opacity: 0.5, display: 'block', mt: 0.5 }}>
              {report.samples} resolved sample{report.samples === 1 ? '' : 's'}
              {report.symbol === 'ALL' ? ' · all symbols' : ''}
            </Typography>
          </Grid>

          {/* Directional edge + bias */}
          <Grid size={{ xs: 12, md: 6 }}>
            <Typography variant="caption" sx={{ opacity: 0.7 }}>Directional edge vs naive persistence</Typography>
            {dir !== null && naive !== null && edge !== null ? (
              <Box sx={{ mt: 0.5, mb: 2 }}>
                <Typography sx={{ fontSize: '1.05rem', fontWeight: 700 }}>
                  {dir.toFixed(0)}% <Box component="span" sx={{ opacity: 0.6, fontWeight: 400 }}>ensemble</Box>
                  {' vs '}{naive.toFixed(0)}% <Box component="span" sx={{ opacity: 0.6, fontWeight: 400 }}>naive</Box>
                </Typography>
                <Chip
                  size="small"
                  icon={<TrendingUp size={14} />}
                  label={`${edge >= 0 ? '+' : ''}${edge.toFixed(0)}% edge`}
                  sx={{ mt: 1, fontWeight: 700, color: edge > 0 ? green : red, bgcolor: `${edge > 0 ? green : red}1a` }}
                />
                <Typography variant="caption" sx={{ opacity: 0.6, display: 'block', mt: 1 }}>
                  {edge > 0 ? 'The ensemble beats simply assuming yesterday’s move repeats.' : 'The ensemble is not beating a naive persistence baseline.'}
                </Typography>
              </Box>
            ) : (
              <Typography variant="body2" sx={{ opacity: 0.5, mt: 1, mb: 2 }}>Not enough directional samples yet.</Typography>
            )}

            <Typography variant="caption" sx={{ opacity: 0.7 }}>Bias — mean signed error (forecast − actual)</Typography>
            {bias !== null ? (
              <Stack direction="row" alignItems="baseline" gap={1} sx={{ mt: 0.5 }}>
                <Typography sx={{ fontSize: '1.4rem', fontWeight: 800, color: Math.abs(bias) < 0.5 ? axis : (bias > 0 ? amber : primaryColor) }}>
                  {bias >= 0 ? '+' : ''}{bias.toFixed(2)}
                </Typography>
                <Typography variant="body2" sx={{ opacity: 0.6 }}>
                  {Math.abs(bias) < 0.5 ? 'roughly unbiased' : bias > 0 ? 'forecasts run high' : 'forecasts run low'}
                </Typography>
              </Stack>
            ) : (
              <Typography variant="body2" sx={{ opacity: 0.5, mt: 0.5 }}>—</Typography>
            )}
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
}

// ── Small inline empty-chart placeholder ────────────────────────────────────────

function EmptyChart({ label, isDark }: { label: string; isDark: boolean }) {
  return (
    <Box sx={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.4 }}>
      <Typography variant="body2" sx={{ color: isDark ? '#94a3b8' : '#64748b' }}>{label}</Typography>
    </Box>
  );
}

export default function InsightsPage() {
  return (
    <Suspense fallback={
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 10 }}>
        <CircularProgress />
      </Box>
    }>
      <InsightsContent />
    </Suspense>
  );
}
