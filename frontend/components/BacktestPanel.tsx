'use client';

import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Box, Button, Paper, Typography, CircularProgress,
  Table, TableBody, TableCell, TableHead, TableRow, Tooltip as MuiTooltip,
} from '@mui/material';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  ReferenceLine, Tooltip,
} from 'recharts';
import { Activity } from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────────────

interface ModelScore {
  mae: number | null;
  directional_accuracy: number | null;
}

interface EquityPoint {
  date: string;
  cumulative_return_pct: number;
}

interface BacktestResult {
  symbol: string;
  windows_tested: number;
  ensemble: ModelScore;
  models: {
    prophet: ModelScore;
    sarimax: ModelScore;
    random_forest: ModelScore;
  };
  equity_curve: EquityPoint[];
  computed_at: string;
}

interface Props {
  symbol: string;
  isDark: boolean;
  primaryColor: string;
}

const MODEL_ROWS: Array<{ key: keyof BacktestResult['models']; label: string; color: string }> = [
  { key: 'prophet',       label: 'Prophet',       color: '#f97316' },
  { key: 'sarimax',       label: 'SARIMAX',       color: '#60a5fa' },
  { key: 'random_forest', label: 'Random Forest', color: '#34d399' },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

const fmtMae = (v: number | null) => (v == null ? '—' : `$${v.toFixed(2)}`);
const fmtAcc = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`);

// ── Component ──────────────────────────────────────────────────────────────────

export default function BacktestPanel({ symbol, isDark, primaryColor }: Props) {
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Clear any prior ticker's backtest when the symbol changes so a stale result
  // isn't shown for the newly-selected ticker until the user reruns.
  useEffect(() => {
    setResult(null);
    setError(null);
  }, [symbol]);

  const textColor = isDark ? 'rgba(220,220,220,0.55)' : 'rgba(20,30,50,0.55)';
  const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';

  const runBacktest = async () => {
    if (!symbol || loading) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await axios.get<BacktestResult>(`/api/backtest/${symbol}`, { timeout: 130000 });
      setResult(data);
    } catch (err: unknown) {
      const resp = (err as { response?: { data?: { error?: string } } })?.response;
      setError(resp?.data?.error ?? 'Backtest failed — please try again.');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  if (!symbol) return null;

  const lastReturn = result?.equity_curve.at(-1)?.cumulative_return_pct ?? 0;

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
        <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: textColor, textTransform: 'uppercase' }}>
          Walk-Forward Backtest
        </Typography>
        {result && (
          <Typography sx={{ fontSize: 10, color: textColor }}>
            {result.windows_tested} windows · 252d train / 5d horizon
          </Typography>
        )}
      </Box>

      {!result && (
        <MuiTooltip
          title="Re-fits Prophet, SARIMAX & Random Forest across ~2 years of rolling windows to measure out-of-sample accuracy. Takes ~30s."
          arrow
        >
          <span>
            <Button
              size="small"
              variant="outlined"
              onClick={runBacktest}
              disabled={loading}
              startIcon={loading ? <CircularProgress size={14} /> : <Activity size={14} />}
              sx={{
                fontSize: 11, py: 0.4, px: 1.5, textTransform: 'none',
                borderColor: `${primaryColor}55`, color: primaryColor,
                '&:hover': { borderColor: primaryColor, background: `${primaryColor}11` },
              }}
            >
              {loading ? 'Running backtest (~30s)…' : 'Run Backtest'}
            </Button>
          </span>
        </MuiTooltip>
      )}

      {error && (
        <Typography sx={{ fontSize: 11, color: '#ff6b6b', mt: 1 }}>{error}</Typography>
      )}

      {result && (
        <Paper
          sx={{
            p: 1.5, mt: 0.5, borderRadius: 2,
            border: `1px solid ${primaryColor}22`,
            background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.01)',
          }}
        >
          {/* Per-model accuracy table */}
          <Table size="small" sx={{ '& td, & th': { borderColor: gridColor, py: 0.5, px: 1 } }}>
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontSize: 10, fontWeight: 700, color: textColor }}>Model</TableCell>
                <MuiTooltip title="Mean absolute error of the predicted close vs. realized close, averaged over every forecast day." arrow>
                  <TableCell align="right" sx={{ fontSize: 10, fontWeight: 700, color: textColor, cursor: 'help' }}>MAE</TableCell>
                </MuiTooltip>
                <MuiTooltip title="How often the model called the 5-day direction (up/down) correctly." arrow>
                  <TableCell align="right" sx={{ fontSize: 10, fontWeight: 700, color: textColor, cursor: 'help' }}>Dir. Acc.</TableCell>
                </MuiTooltip>
              </TableRow>
            </TableHead>
            <TableBody>
              {MODEL_ROWS.map(({ key, label, color }) => {
                const m = result.models[key];
                return (
                  <TableRow key={key}>
                    <TableCell sx={{ fontSize: 12 }}>
                      <Box component="span" sx={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', bgcolor: color, mr: 0.75 }} />
                      {label}
                    </TableCell>
                    <TableCell align="right" sx={{ fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>{fmtMae(m.mae)}</TableCell>
                    <TableCell align="right" sx={{ fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>{fmtAcc(m.directional_accuracy)}</TableCell>
                  </TableRow>
                );
              })}
              {/* Ensemble row — emphasized */}
              <TableRow>
                <TableCell sx={{ fontSize: 12, fontWeight: 800, color: primaryColor }}>Ensemble</TableCell>
                <TableCell align="right" sx={{ fontSize: 12, fontWeight: 800, color: primaryColor, fontVariantNumeric: 'tabular-nums' }}>{fmtMae(result.ensemble.mae)}</TableCell>
                <TableCell align="right" sx={{ fontSize: 12, fontWeight: 800, color: primaryColor, fontVariantNumeric: 'tabular-nums' }}>{fmtAcc(result.ensemble.directional_accuracy)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>

          {/* Equity curve */}
          <Box sx={{ mt: 1.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mb: 0.5 }}>
              <Typography sx={{ fontSize: 10, fontWeight: 700, color: textColor, textTransform: 'uppercase', letterSpacing: 0.8 }}>
                Strategy Equity Curve
              </Typography>
              <Typography sx={{ fontSize: 11, fontWeight: 800, color: lastReturn >= 0 ? '#16a34a' : '#dc2626' }}>
                {lastReturn >= 0 ? '+' : ''}{lastReturn.toFixed(2)}%
              </Typography>
            </Box>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={result.equity_curve} margin={{ top: 6, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#64748b' }} minTickGap={28} />
                <YAxis
                  tick={{ fontSize: 9, fill: '#64748b' }}
                  tickFormatter={(v) => `${v}%`}
                  width={42}
                />
                <Tooltip
                  formatter={(v: number) => [`${v.toFixed(2)}%`, 'Cumulative']}
                  contentStyle={{
                    background: isDark ? '#0d1117' : '#fff',
                    border: `1px solid ${primaryColor}33`,
                    borderRadius: 8, fontSize: 12,
                  }}
                />
                <ReferenceLine y={0} stroke="#64748b" strokeDasharray="4 3" />
                <Line
                  type="monotone"
                  dataKey="cumulative_return_pct"
                  stroke={primaryColor}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
            <Typography sx={{ fontSize: 9, opacity: 0.45, mt: 0.5 }}>
              Long/short the ensemble&apos;s 5-day call, one trade per window. Cumulative realized return — not financial advice.
            </Typography>
          </Box>
        </Paper>
      )}
    </Box>
  );
}
