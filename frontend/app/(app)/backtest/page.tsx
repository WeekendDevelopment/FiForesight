"use client";

import React, { useState } from 'react';
import axios from 'axios';
import {
  Box, Container, Typography, TextField, Button, Card, CardContent,
  Grid, Alert, Paper, Stack, Skeleton, MenuItem, Select, InputLabel,
  FormControl, ToggleButton, ToggleButtonGroup, useMediaQuery,
} from '@mui/material';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, Legend,
} from 'recharts';
import { FlaskConical } from 'lucide-react';
import { useAppShell } from '../../../contexts/AppShellContext';
import type { BacktestResult } from '../../../types';

// ── Strategy metadata ────────────────────────────────────────────────────────

type ParamField = { key: string; label: string; default: number };

const STRATEGIES: { value: string; label: string; params: ParamField[] }[] = [
  {
    value: 'sma_cross',
    label: 'SMA Cross',
    params: [
      { key: 'fast', label: 'Fast SMA', default: 20 },
      { key: 'slow', label: 'Slow SMA', default: 50 },
    ],
  },
  {
    value: 'rsi_reversion',
    label: 'RSI Reversion',
    params: [
      { key: 'oversold', label: 'Oversold', default: 30 },
      { key: 'overbought', label: 'Overbought', default: 70 },
    ],
  },
  { value: 'macd_cross', label: 'MACD Cross', params: [] },
  { value: 'bollinger_bounce', label: 'Bollinger Bounce', params: [] },
];

const PERIODS = ['1y', '2y', '5y'] as const;

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function BacktestPage() {
  const { isDark, primaryColor } = useAppShell();
  const isMobile = useMediaQuery('(max-width:768px)');
  const isTablet = useMediaQuery('(max-width:1280px)');
  const chartHeight = isMobile ? 220 : isTablet ? 300 : 400;

  const [ticker, setTicker] = useState('');
  const [strategy, setStrategy] = useState('sma_cross');
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>('2y');
  const [params, setParams] = useState<Record<string, number>>({ fast: 20, slow: 50 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const axisColor = isDark ? '#94a3b8' : '#64748b';
  const greenColor = isDark ? '#00ffa3' : '#16a34a';
  const redColor = isDark ? '#ff0055' : '#dc2626';

  const activeStrategy = STRATEGIES.find((s) => s.value === strategy)!;

  const handleStrategyChange = (value: string) => {
    setStrategy(value);
    const next = STRATEGIES.find((s) => s.value === value)!;
    const seeded: Record<string, number> = {};
    next.params.forEach((p) => { seeded[p.key] = p.default; });
    setParams(seeded);
  };

  const runBacktest = async () => {
    const sym = ticker.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await axios.post('/api/backtest', {
        symbol: sym, strategy, params, period,
      });
      setResult(res.data as BacktestResult);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Backtest failed. Try another ticker.');
    } finally {
      setLoading(false);
    }
  };

  const beatBuyHold = result ? result.totalReturnPct > result.buyHoldReturnPct : false;

  const statCards: { label: string; value: string; color?: string }[] = result
    ? [
        { label: 'Total Return', value: fmtPct(result.totalReturnPct),
          color: result.totalReturnPct >= 0 ? greenColor : redColor },
        { label: 'vs Buy & Hold', value: fmtPct(result.buyHoldReturnPct),
          color: beatBuyHold ? greenColor : redColor },
        { label: 'CAGR', value: fmtPct(result.cagrPct) },
        { label: 'Win Rate', value: result.winRatePct === null ? '—' : `${result.winRatePct.toFixed(1)}%` },
        { label: '# Trades', value: String(result.numTrades) },
        { label: 'Max Drawdown', value: fmtPct(result.maxDrawdownPct), color: redColor },
        { label: 'Sharpe', value: result.sharpe.toFixed(2) },
      ]
    : [];

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 2, md: 4 } }}>
      <Stack direction="row" spacing={1.5} alignItems="center" mb={1}>
        <FlaskConical size={26} color={primaryColor} />
        <Typography variant="h4" fontWeight={700}>Strategy Backtester</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Simulate a curated long-only strategy over historical data and compare it to buy &amp; hold.
        Single full position, no leverage, no costs.
      </Typography>

      {/* ── Rule builder ── */}
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mb: 3 }}>
        <Grid container spacing={2} alignItems="flex-end">
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <TextField
              label="Ticker" fullWidth size="small" value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') runBacktest(); }}
              placeholder="AAPL"
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <FormControl fullWidth size="small">
              <InputLabel id="strategy-label">Strategy</InputLabel>
              <Select
                labelId="strategy-label" label="Strategy" value={strategy}
                onChange={(e) => handleStrategyChange(e.target.value)}
              >
                {STRATEGIES.map((s) => (
                  <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          {activeStrategy.params.map((p) => (
            <Grid size={{ xs: 6, sm: 3, md: 1.5 }} key={p.key}>
              <TextField
                label={p.label} type="number" fullWidth size="small"
                value={params[p.key] ?? p.default}
                onChange={(e) => setParams((prev) => ({ ...prev, [p.key]: Number(e.target.value) }))}
              />
            </Grid>
          ))}
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <ToggleButtonGroup
              exclusive size="small" value={period} fullWidth
              onChange={(_, v) => { if (v) setPeriod(v); }}
            >
              {PERIODS.map((p) => (
                <ToggleButton key={p} value={p}>{p.toUpperCase()}</ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Grid>
          <Grid size={{ xs: 12, md: 'auto' }}>
            <Button
              variant="contained" onClick={runBacktest}
              disabled={loading || !ticker.trim()} sx={{ height: 40 }}
            >
              {loading ? 'Running…' : 'Run Backtest'}
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {error && <Alert severity="warning" sx={{ mb: 3 }}>{error}</Alert>}

      {loading && (
        <Box>
          <Grid container spacing={2} mb={3}>
            {Array.from({ length: 7 }).map((_, i) => (
              <Grid size={{ xs: 6, sm: 4, md: 3 }} key={i}>
                <Skeleton variant="rounded" height={88} />
              </Grid>
            ))}
          </Grid>
          <Skeleton variant="rounded" height={chartHeight} />
        </Box>
      )}

      {result && !loading && (
        <Box>
          {/* ── Stat cards ── */}
          <Grid container spacing={2} mb={3}>
            {statCards.map((c) => (
              <Grid size={{ xs: 6, sm: 4, md: 3 }} key={c.label}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent sx={{ py: 2 }}>
                    <Typography variant="caption" color="text.secondary">{c.label}</Typography>
                    <Typography variant="h6" fontWeight={700} sx={{ color: c.color }}>
                      {c.value}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          {beatBuyHold ? (
            <Alert severity="success" sx={{ mb: 3 }}>
              This strategy beat buy &amp; hold by {(result.totalReturnPct - result.buyHoldReturnPct).toFixed(2)} pts.
            </Alert>
          ) : (
            <Alert severity="info" sx={{ mb: 3 }}>
              Buy &amp; hold outperformed this strategy by {(result.buyHoldReturnPct - result.totalReturnPct).toFixed(2)} pts.
            </Alert>
          )}

          {/* ── Equity curve ── */}
          <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 3 } }}>
            <Typography variant="subtitle1" fontWeight={600} mb={1}>
              Equity Curve (growth of $1)
            </Typography>
            <ResponsiveContainer width="100%" height={chartHeight}>
              <LineChart data={result.equityCurve} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={gridColor} vertical={false} />
                <XAxis
                  dataKey="date" tick={{ fill: axisColor, fontSize: 11 }}
                  minTickGap={48} stroke={gridColor}
                />
                <YAxis
                  tick={{ fill: axisColor, fontSize: 11 }} stroke={gridColor}
                  tickFormatter={(v) => `${v.toFixed(2)}×`} width={48}
                />
                <Tooltip
                  contentStyle={{
                    background: isDark ? '#0f172a' : '#fff',
                    border: `1px solid ${gridColor}`, borderRadius: 8,
                  }}
                  formatter={(v: number) => `${v.toFixed(3)}×`}
                />
                <Legend />
                <Line
                  type="monotone" dataKey="strategy" name="Strategy"
                  stroke={primaryColor} dot={false} strokeWidth={2}
                />
                <Line
                  type="monotone" dataKey="buyHold" name="Buy & Hold"
                  stroke={axisColor} dot={false} strokeWidth={1.5} strokeDasharray="5 4"
                />
              </LineChart>
            </ResponsiveContainer>
          </Paper>
        </Box>
      )}
    </Container>
  );
}
