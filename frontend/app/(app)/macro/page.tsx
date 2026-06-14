'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box, Card, CardContent, Container, Grid, Skeleton, Stack, Typography, useMediaQuery,
} from '@mui/material';
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { AlertTriangle, ArrowDown, ArrowUp, Globe, Minus } from 'lucide-react';
import { useAppShell } from '../../../contexts/AppShellContext';
import type { MacroSnapshot, MacroSeries } from '../../../types';

// ── Series display config ─────────────────────────────────────────────────────
// `upIsBad` decides delta-arrow colour: when true, a rising value is risk-on-red.
type SeriesKey = 'dgs10' | 'cpiaucsl' | 'unrate' | 'fedfunds' | 't10y2y';
interface SeriesMeta {
  key:     SeriesKey;
  label:   string;
  unit:    string;
  upIsBad: boolean;
  /** Orange (not red) when rising — used for UNRATE. */
  warn?:   boolean;
}

const SERIES: SeriesMeta[] = [
  { key: 'dgs10',    label: '10Y Treasury',  unit: '%', upIsBad: true  },
  { key: 'cpiaucsl', label: 'CPI',           unit: '',  upIsBad: true  },
  { key: 'unrate',   label: 'Unemployment',  unit: '%', upIsBad: true, warn: true },
  { key: 'fedfunds', label: 'Fed Funds',     unit: '%', upIsBad: true  },
  { key: 't10y2y',   label: '10Y–2Y Spread', unit: '%', upIsBad: false },
];

const RED   = (dark: boolean) => (dark ? '#ff0055' : '#dc2626');
const GREEN = (dark: boolean) => (dark ? '#00ffa3' : '#16a34a');
const AMBER = '#f59e0b';

export default function MacroPage() {
  const { isDark, primaryColor } = useAppShell();
  // Responsive chart sizing (320/768/1280/2560 breakpoint policy).
  const isMobile  = useMediaQuery('(max-width:768px)');
  const is4k      = useMediaQuery('(min-width:2560px)');
  const chartH    = isMobile ? 200 : is4k ? 320 : 260;
  const [snapshot, setSnapshot] = useState<MacroSnapshot | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error,   setError]     = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/macro/snapshot');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: MacroSnapshot = await res.json();
      setSnapshot(json);
      setError(null);
    } catch {
      setError('Macro data unavailable — FRED may be unreachable.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + auto-refresh every 60 min + on tab focus.
  useEffect(() => {
    load();
    const interval = setInterval(load, 60 * 60 * 1000);
    const onVisible = () => { if (document.visibilityState === 'visible') load(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [load]);

  const hasData = useMemo(
    () => !!snapshot && SERIES.some(s => snapshot[s.key]),
    [snapshot],
  );

  // 30d deltas for the bar chart, normalised to each series' own magnitude
  // (percent change of value) so a 0.1 yield move and a 26-pt CPI-index move are
  // visually comparable instead of CPI dominating the axis. `delta` is kept for
  // sign-based colouring + the tooltip.
  const deltaBars = useMemo(() => {
    if (!snapshot) return [];
    return SERIES
      .map(s => {
        const series = snapshot[s.key] as MacroSeries | undefined;
        if (!series) return null;
        const mag = Math.abs(series.value);
        const pct = mag > 0.01 ? (series.delta_30d / mag) * 100 : series.delta_30d;
        return { key: s.key, label: s.label, delta: series.delta_30d, pct: Number(pct.toFixed(2)) };
      })
      .filter((d): d is NonNullable<typeof d> => d !== null);
  }, [snapshot]);

  const axisColor = isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.45)';
  const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';

  function deltaColor(meta: SeriesMeta, delta: number, value?: number): string {
    // An inverted yield-curve spread is always a warning — red regardless of
    // which way the delta moved.
    if (meta.key === 't10y2y' && value != null && value < 0) return RED(isDark);
    if (delta === 0) return axisColor;
    const rising = delta > 0;
    if (meta.warn) return rising ? AMBER : GREEN(isDark);
    if (meta.upIsBad) return rising ? RED(isDark) : GREEN(isDark);
    return rising ? GREEN(isDark) : RED(isDark);
  }

  return (
    <Container maxWidth="lg" disableGutters>
      {/* Heading */}
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.5 }}>
        <Globe size={26} color={primaryColor} />
        <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
          Macro Dashboard
        </Typography>
      </Stack>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Live macro regime context from FRED — rates, inflation, employment, and the yield curve.
      </Typography>

      {/* Inversion banner */}
      {!loading && snapshot?.inverted && (
        <Card sx={{
          mb: 3,
          border: `1px solid ${AMBER}66`,
          background: isDark ? 'rgba(245,158,11,0.08)' : 'rgba(245,158,11,0.10)',
        }}>
          <CardContent sx={{ py: '12px !important', display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <AlertTriangle size={20} color={AMBER} />
            <Box>
              <Typography sx={{ fontWeight: 700, color: AMBER, fontSize: '0.9rem' }}>
                Yield curve inverted
              </Typography>
              <Typography variant="caption" sx={{ opacity: 0.7 }}>
                The 10Y–2Y spread is negative ({snapshot.t10y2y?.value?.toFixed(2)}%) — historically a recession warning.
              </Typography>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <Grid container spacing={2}>
          {[0, 1, 2, 3, 4].map(i => (
            <Grid size={{ xs: 6, sm: 4, md: 2.4 }} key={i}>
              <Skeleton variant="rounded" height={96} />
            </Grid>
          ))}
          <Grid size={12}><Skeleton variant="rounded" height={300} sx={{ mt: 1 }} /></Grid>
          <Grid size={12}><Skeleton variant="rounded" height={280} /></Grid>
        </Grid>
      )}

      {/* Empty / error */}
      {!loading && (!hasData || error) && (
        <Box sx={{ py: 8, textAlign: 'center', opacity: 0.55 }}>
          <Globe size={44} color={primaryColor} style={{ opacity: 0.5 }} />
          <Typography sx={{ mt: 2 }}>
            {error ?? 'Macro data unavailable — FRED may be unreachable.'}
          </Typography>
        </Box>
      )}

      {/* Data */}
      {!loading && hasData && !error && (
        <Stack spacing={3}>
          {/* Stat cards */}
          <Grid container spacing={2}>
            {SERIES.map(meta => {
              const s = snapshot![meta.key] as MacroSeries | undefined;
              if (!s) return null;
              const col = deltaColor(meta, s.delta_30d, s.value);
              const Arrow = s.delta_30d > 0 ? ArrowUp : s.delta_30d < 0 ? ArrowDown : Minus;
              return (
                <Grid size={{ xs: 6, sm: 4, md: 2.4 }} key={meta.key}>
                  <Card sx={{ height: '100%' }}>
                    <CardContent sx={{ p: '14px !important' }}>
                      <Typography variant="caption" sx={{ opacity: 0.5, fontWeight: 700, letterSpacing: 0.5 }}>
                        {meta.label.toUpperCase()}
                      </Typography>
                      <Typography sx={{ fontWeight: 800, fontSize: '1.4rem', mt: 0.5, lineHeight: 1.1 }}>
                        {s.value.toFixed(2)}{meta.unit}
                      </Typography>
                      <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 0.5, color: col }}>
                        <Arrow size={14} />
                        <Typography sx={{ fontSize: '0.78rem', fontWeight: 700 }}>
                          {s.delta_30d > 0 ? '+' : ''}{s.delta_30d.toFixed(2)} 30d
                        </Typography>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
              );
            })}
          </Grid>

          {/* T10Y2Y 30-day trend */}
          {snapshot!.t10y2y_trend && snapshot!.t10y2y_trend.length > 1 && (
            <Card>
              <CardContent>
                <Typography variant="overline" sx={{ opacity: 0.5 }}>
                  10Y–2Y Spread · 30-day trend
                </Typography>
                <Box sx={{ mt: 2 }}>
                  <ResponsiveContainer width="100%" height={chartH}>
                    <LineChart data={snapshot!.t10y2y_trend} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: axisColor }}
                        tickFormatter={(d: string) => d.slice(5)}
                        minTickGap={28}
                      />
                      <YAxis tick={{ fontSize: 10, fill: axisColor }} width={44} />
                      <Tooltip
                        contentStyle={{
                          background: isDark ? '#0d1520' : '#fff',
                          border: `1px solid ${gridColor}`, borderRadius: 8, fontSize: 12,
                        }}
                      />
                      <ReferenceLine y={0} stroke={AMBER} strokeDasharray="4 4" />
                      <Line
                        type="monotone" dataKey="value"
                        stroke={primaryColor} strokeWidth={2} dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              </CardContent>
            </Card>
          )}

          {/* Normalised 30-day % change (each series scaled to its own value) */}
          {deltaBars.length > 0 && (
            <Card>
              <CardContent>
                <Typography variant="overline" sx={{ opacity: 0.5 }}>
                  30-day change by series (% of value)
                </Typography>
                <Box sx={{ mt: 2 }}>
                  <ResponsiveContainer width="100%" height={chartH}>
                    <BarChart data={deltaBars} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: axisColor }} interval={0} />
                      <YAxis tick={{ fontSize: 10, fill: axisColor }} width={44} unit="%" />
                      <Tooltip
                        cursor={{ fill: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)' }}
                        contentStyle={{
                          background: isDark ? '#0d1520' : '#fff',
                          border: `1px solid ${gridColor}`, borderRadius: 8, fontSize: 12,
                        }}
                        formatter={(v: number, _n, p) => [
                          `${v > 0 ? '+' : ''}${v}%  (${p?.payload?.delta > 0 ? '+' : ''}${p?.payload?.delta} abs)`,
                          '30d change',
                        ]}
                      />
                      <ReferenceLine y={0} stroke={axisColor} />
                      <Bar dataKey="pct" radius={[3, 3, 0, 0]}>
                        {deltaBars.map((d, i) => {
                          const meta = SERIES.find(s => s.key === d.key)!;
                          const value = (snapshot![d.key] as MacroSeries).value;
                          return <Cell key={i} fill={deltaColor(meta, d.delta, value)} />;
                        })}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </Box>
              </CardContent>
            </Card>
          )}

          {snapshot!.fetched_at && (
            <Typography variant="caption" sx={{ opacity: 0.4, textAlign: 'right' }}>
              FRED · updated {new Date(snapshot!.fetched_at).toLocaleString()}
            </Typography>
          )}
        </Stack>
      )}
    </Container>
  );
}
