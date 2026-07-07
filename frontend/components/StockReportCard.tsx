'use client';

import { useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Skeleton, Stack, Typography, useTheme,
} from '@mui/material';
import { Award } from 'lucide-react';
import type { ReportCard } from '../types';

interface Props {
  symbol: string;
}

const CATEGORIES: { key: keyof ReportCard['categories']; label: string }[] = [
  { key: 'value',          label: 'Value' },
  { key: 'growth',         label: 'Growth' },
  { key: 'profitability',  label: 'Profitability' },
  { key: 'momentum',       label: 'Momentum' },
  { key: 'financialHealth', label: 'Financial Health' },
];

/** Green (100) → red (0), matching the grade palette below. */
function scoreColor(score: number | null): string {
  if (score == null) return '#94a3b8';
  if (score >= 80) return '#16a34a';
  if (score >= 65) return '#65a30d';
  if (score >= 50) return '#f59e0b';
  if (score >= 35) return '#f97316';
  return '#dc2626';
}

const GRADE_COLORS: Record<string, string> = {
  A: '#16a34a', B: '#65a30d', C: '#f59e0b', D: '#f97316', F: '#dc2626',
};

export default function StockReportCard({ symbol }: Props) {
  const theme = useTheme();
  const [data, setData]       = useState<ReportCard | null>(null);
  const [loading, setLoading] = useState(true);

  // The parent remounts this card per symbol (key={symbol}), so the effect runs
  // once with loading already true — no synchronous setState reset needed.
  useEffect(() => {
    if (!symbol) return;
    const ctrl = new AbortController();
    fetch(`/api/report-card/${encodeURIComponent(symbol)}`, { signal: ctrl.signal })
      .then(r => (r.ok ? r.json() : null))
      .then((d: ReportCard | null) => setData(d))
      .catch(() => { /* aborted or failed — fall through to empty state */ })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [symbol]);

  const header = (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
      <Award size={16} color={theme.palette.primary.main} />
      <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
        Stock Report Card
      </Typography>
    </Stack>
  );

  if (loading) {
    return (
      <Card>
        <CardContent sx={{ p: '16px !important' }}>
          {header}
          <Skeleton variant="circular" width={56} height={56} sx={{ mb: 2 }} />
          <Skeleton variant="rectangular" height={100} sx={{ borderRadius: 1 }} />
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card>
        <CardContent sx={{ p: '16px !important' }}>
          {header}
          <Typography variant="body2" sx={{ opacity: 0.4 }}>
            Report card unavailable
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const { overall, grade, categories } = data;
  const badgeColor = grade ? GRADE_COLORS[grade] : '#94a3b8';

  return (
    <Card>
      <CardContent sx={{ p: '16px !important' }}>
        {header}

        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2.5, minWidth: 0 }}>
          <Box
            sx={{
              flexShrink: 0,
              width: 56, height: 56, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: `${badgeColor}22`,
              border: `2px solid ${badgeColor}`,
            }}
          >
            <Typography sx={{ fontSize: '1.5rem', fontWeight: 900, color: badgeColor, lineHeight: 1 }}>
              {grade ?? '—'}
            </Typography>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontSize: '1.3rem', fontWeight: 800, lineHeight: 1.2 }}>
              {overall ?? '—'}{overall != null && <Typography component="span" sx={{ fontSize: '0.8rem', opacity: 0.5, fontWeight: 600 }}>/100</Typography>}
            </Typography>
            <Typography sx={{ fontSize: '0.62rem', opacity: 0.5, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              Overall Score
            </Typography>
          </Box>
        </Stack>

        <Stack spacing={1.5}>
          {CATEGORIES.map(({ key, label }) => {
            const score = categories[key];
            const color = scoreColor(score);
            return (
              <Box key={key} sx={{ minWidth: 0 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 0.4 }}>
                  <Typography sx={{ fontSize: '0.68rem', opacity: 0.7, fontWeight: 600 }}>
                    {label}
                  </Typography>
                  <Typography sx={{ fontSize: '0.68rem', fontWeight: 800, color }}>
                    {score ?? '—'}
                  </Typography>
                </Stack>
                <Box
                  sx={{
                    height: 8, borderRadius: 4, overflow: 'hidden',
                    background: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
                  }}
                >
                  <Box
                    sx={{
                      height: '100%', width: `${score ?? 0}%`, borderRadius: 4,
                      background: color, transition: 'width 0.3s ease',
                    }}
                  />
                </Box>
              </Box>
            );
          })}
        </Stack>
      </CardContent>
    </Card>
  );
}
