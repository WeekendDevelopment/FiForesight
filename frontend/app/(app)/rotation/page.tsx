'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Alert, Box, Card, CardContent, Chip, Container, Skeleton, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, Typography,
  useMediaQuery, useTheme,
} from '@mui/material';
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, ReferenceLine, LabelList, Cell,
} from 'recharts';
import { RefreshCw } from 'lucide-react';
import { useAppShell } from '../../../contexts/AppShellContext';
import type { SectorRotationRow } from '../../../types';

type Quadrant = SectorRotationRow['quadrant'];

const QUADRANT_LABEL: Record<Quadrant, string> = {
  leading:   'Leading',
  weakening: 'Weakening',
  improving: 'Improving',
  lagging:   'Lagging',
};

// Quadrant accents — leading=green, improving=blue, weakening=amber, lagging=red.
function quadrantColor(q: Quadrant, isDark: boolean): string {
  switch (q) {
    case 'leading':   return isDark ? '#00ffa3' : '#16a34a';
    case 'improving': return isDark ? '#38bdf8' : '#2563eb';
    case 'weakening': return isDark ? '#fbbf24' : '#d97706';
    case 'lagging':   return isDark ? '#ff5d73' : '#dc2626';
  }
}

function rsColor(value: number | null, isDark: boolean): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return isDark ? '#94a3b8' : '#64748b';
  }
  if (value > 0) return isDark ? '#00ffa3' : '#16a34a';
  if (value < 0) return isDark ? '#ff5d73' : '#dc2626';
  return isDark ? '#94a3b8' : '#64748b';
}

function formatRs(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

export default function SectorRotationPage() {
  const { isDark, primaryColor } = useAppShell();
  const theme = useTheme();
  const router = useRouter();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const isTablet = useMediaQuery(theme.breakpoints.down('md'));

  const [rows, setRows] = useState<SectorRotationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const refresh = () => {
      fetch('/api/sectors/rotation')
        .then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((data: SectorRotationRow[]) => {
          if (cancelled) return;
          if (Array.isArray(data)) {
            setRows(data);
            setError(false);
          } else {
            setError(true);
          }
        })
        .catch(() => { if (!cancelled) setError(true); })
        .finally(() => { if (!cancelled) setLoading(false); });
    };

    refresh();
    const interval = setInterval(refresh, 300_000); // 5 min
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  // The analysis page auto-forecasts when ?symbol= changes — same convention the
  // sector heatmap uses for click-to-analyze.
  const handleSelect = (etf: string) => {
    router.push(`/analysis?symbol=${encodeURIComponent(etf)}`);
  };

  const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const axisColor = isDark ? '#94a3b8' : '#64748b';
  const scatterHeight = isMobile ? 220 : isTablet ? 300 : 400;

  // Only sectors with both a level (rs_3m) and a momentum reading can be plotted.
  const scatterData = rows.filter(r => r.rs_3m !== null && r.rs_momentum !== null);

  return (
    <Container maxWidth="lg" disableGutters>
      <Stack direction="row" alignItems="center" gap={1.5} sx={{ mb: 0.5 }}>
        <RefreshCw size={26} color={primaryColor} />
        <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
          Sector Rotation
        </Typography>
      </Stack>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Relative strength of all 11 GICS sector ETFs vs the S&amp;P 500 (SPY) over 1M / 3M / 6M.
        Leading sectors are outperforming and still improving; lagging ones are underperforming and
        falling further behind. Click a sector to run a full forecast on its ETF.
      </Typography>

      {error && !loading && rows.length === 0 ? (
        <Alert severity="warning">Sector rotation data unavailable</Alert>
      ) : (
        <Stack spacing={3}>
          {/* ── Leaderboard ─────────────────────────────────────────────── */}
          <Card>
            <CardContent>
              <Typography variant="overline" sx={{ opacity: 0.6 }}>
                Relative-Strength Leaderboard
              </Typography>
              {loading ? (
                <Stack spacing={1} sx={{ mt: 1 }}>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} variant="rounded" height={40} />
                  ))}
                </Stack>
              ) : (
                <TableContainer sx={{ overflowX: 'auto', mt: 1 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Sector (ETF)</TableCell>
                        <TableCell align="right">RS 1M</TableCell>
                        <TableCell align="right">RS 3M</TableCell>
                        <TableCell align="right">RS 6M</TableCell>
                        <TableCell align="right">Momentum</TableCell>
                        <TableCell align="center">Quadrant</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.map(row => (
                        <TableRow
                          key={row.etf}
                          hover
                          onClick={() => handleSelect(row.etf)}
                          role="link"
                          tabIndex={0}
                          aria-label={`Analyze ${row.sector} (${row.etf})`}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelect(row.etf); }
                          }}
                          sx={{
                            cursor: 'pointer',
                            '&:focus-visible': { outline: `2px solid ${primaryColor}`, outlineOffset: -2 },
                          }}
                        >
                          <TableCell>
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>{row.sector}</Typography>
                            <Typography variant="caption" sx={{ opacity: 0.6 }}>{row.etf}</Typography>
                          </TableCell>
                          <TableCell align="right" sx={{ color: rsColor(row.rs_1m, isDark), fontWeight: 700 }}>
                            {formatRs(row.rs_1m)}
                          </TableCell>
                          <TableCell align="right" sx={{ color: rsColor(row.rs_3m, isDark) }}>
                            {formatRs(row.rs_3m)}
                          </TableCell>
                          <TableCell align="right" sx={{ color: rsColor(row.rs_6m, isDark) }}>
                            {formatRs(row.rs_6m)}
                          </TableCell>
                          <TableCell align="right" sx={{ color: rsColor(row.rs_momentum, isDark) }}>
                            {formatRs(row.rs_momentum)}
                          </TableCell>
                          <TableCell align="center">
                            <Chip
                              size="small"
                              label={QUADRANT_LABEL[row.quadrant]}
                              sx={{
                                fontWeight: 700, height: 22,
                                color: quadrantColor(row.quadrant, isDark),
                                bgcolor: `${quadrantColor(row.quadrant, isDark)}1a`,
                              }}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>

          {/* ── Quadrant scatter (RRG-lite) ─────────────────────────────── */}
          <Card>
            <CardContent>
              <Typography variant="overline" sx={{ opacity: 0.6 }}>
                Rotation Quadrant · RS Level (3M) vs RS Momentum
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={scatterHeight} sx={{ borderRadius: 2, mt: 1 }} />
              ) : scatterData.length === 0 ? (
                <Box sx={{ height: scatterHeight, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.4 }}>
                  <Typography variant="body2" sx={{ color: axisColor }}>Not enough history to plot</Typography>
                </Box>
              ) : (
                <ResponsiveContainer width="100%" height={scatterHeight}>
                  <ScatterChart margin={{ top: 20, right: 24, bottom: 16, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                    <XAxis
                      type="number" dataKey="rs_3m" name="RS Level (3M)"
                      stroke={axisColor} tick={{ fontSize: 11 }}
                      domain={['auto', 'auto']}
                      label={{ value: 'RS Level (3M) %', position: 'insideBottom', offset: -8, fill: axisColor, fontSize: 11 }}
                    />
                    <YAxis
                      type="number" dataKey="rs_momentum" name="RS Momentum"
                      stroke={axisColor} tick={{ fontSize: 11 }}
                      domain={['auto', 'auto']}
                      label={{ value: 'Momentum', angle: -90, position: 'insideLeft', fill: axisColor, fontSize: 11 }}
                    />
                    <ZAxis range={[120, 120]} />
                    <ReferenceLine x={0} stroke={axisColor} strokeDasharray="2 2" />
                    <ReferenceLine y={0} stroke={axisColor} strokeDasharray="2 2" />
                    <Tooltip
                      cursor={{ strokeDasharray: '3 3' }}
                      contentStyle={{ background: isDark ? '#0f172a' : '#fff', border: `1px solid ${gridColor}`, borderRadius: 8 }}
                      formatter={(v: number, n: string) => [`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`, n]}
                      labelFormatter={() => ''}
                    />
                    <Scatter data={scatterData}>
                      {scatterData.map(d => (
                        <Cell key={d.etf} fill={quadrantColor(d.quadrant, isDark)} />
                      ))}
                      <LabelList dataKey="etf" position="top" style={{ fontSize: 11, fill: axisColor, fontWeight: 700 }} />
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              )}
              <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: 'wrap', gap: 0.5 }}>
                {(['leading', 'improving', 'weakening', 'lagging'] as Quadrant[]).map(q => (
                  <Chip
                    key={q}
                    size="small"
                    label={QUADRANT_LABEL[q]}
                    sx={{
                      fontWeight: 700, height: 22,
                      color: quadrantColor(q, isDark),
                      bgcolor: `${quadrantColor(q, isDark)}1a`,
                    }}
                  />
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Stack>
      )}
    </Container>
  );
}
