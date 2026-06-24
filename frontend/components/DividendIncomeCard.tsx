'use client';

import { useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Skeleton, Stack, Typography, useTheme,
} from '@mui/material';
import { Coins, TrendingUp, TrendingDown } from 'lucide-react';
import type { DividendInfo } from '../types';

interface Props {
  symbol: string;
}

const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? '—' : `${v.toFixed(digits)}%`;
const usd = (v: number | null | undefined) =>
  v == null ? '—' : `$${v.toFixed(2)}`;

/** A compact stat tile mirroring the DCFCard / FundamentalsPanel density. */
function StatTile({
  label, value, color,
}: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography sx={{ fontSize: '0.55rem', opacity: 0.5, letterSpacing: '0.04em', lineHeight: 1.2 }}>
        {label}
      </Typography>
      <Typography
        sx={{
          fontSize: '0.95rem', fontWeight: 800, lineHeight: 1.3,
          color: color ?? 'text.primary', whiteSpace: 'nowrap',
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}

export default function DividendIncomeCard({ symbol }: Props) {
  const theme = useTheme();
  const [data, setData]       = useState<DividendInfo | null>(null);
  const [loading, setLoading] = useState(true);

  // The parent remounts this card per symbol (key={symbol}), so the effect runs
  // once with loading already true — no synchronous setState reset needed.
  useEffect(() => {
    if (!symbol) return;
    const ctrl = new AbortController();
    fetch(`/api/dividends/${encodeURIComponent(symbol)}`, { signal: ctrl.signal })
      .then(r => (r.ok ? r.json() : null))
      .then((d: DividendInfo | null) => setData(d))
      .catch(() => { /* aborted or failed — fall through to empty state */ })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [symbol]);

  const header = (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
      <Coins size={16} color={theme.palette.primary.main} />
      <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
        Dividend &amp; Income
      </Typography>
      {data?.paysDividend && data.dividendYield != null && (
        <Box
          sx={{
            ml: 'auto', px: 1, py: 0.25, borderRadius: 1,
            background: '#00ffa322', border: '1px solid #00ffa344',
          }}
        >
          <Typography sx={{ fontSize: '0.62rem', fontWeight: 900, color: '#16a34a', letterSpacing: '0.04em' }}>
            {data.dividendYield.toFixed(1)}% yield
          </Typography>
        </Box>
      )}
    </Stack>
  );

  if (loading) {
    return (
      <Card>
        <CardContent sx={{ p: '16px !important' }}>
          {header}
          <Skeleton variant="rectangular" height={56} sx={{ borderRadius: 1 }} />
        </CardContent>
      </Card>
    );
  }

  if (!data || !data.paysDividend) {
    return (
      <Card>
        <CardContent sx={{ p: '16px !important' }}>
          {header}
          <Typography variant="body2" sx={{ opacity: 0.4 }}>
            This company does not pay a dividend.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const growth   = data.dividendGrowthPct;
  const growthUp = (growth ?? 0) >= 0;
  const growthColor = growth == null ? undefined : growthUp ? '#16a34a' : '#dc2626';

  return (
    <Card>
      <CardContent sx={{ p: '16px !important' }}>
        {header}

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(3, 1fr)' },
            gap: 1.5,
          }}
        >
          <StatTile label="ANNUAL RATE"   value={usd(data.dividendRate)} />
          <StatTile label="PAYOUT RATIO"  value={pct(data.payoutRatio)} />
          <StatTile label="5-YR AVG YIELD" value={pct(data.fiveYearAvgYield, 2)} />
          <StatTile label="EX-DIVIDEND"   value={data.exDividendDate ?? '—'} />
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontSize: '0.55rem', opacity: 0.5, letterSpacing: '0.04em', lineHeight: 1.2 }}>
              YoY GROWTH
            </Typography>
            <Stack direction="row" alignItems="center" spacing={0.5}>
              {growth != null && (growthUp
                ? <TrendingUp size={14} color={growthColor} />
                : <TrendingDown size={14} color={growthColor} />)}
              <Typography
                sx={{ fontSize: '0.95rem', fontWeight: 800, lineHeight: 1.3, color: growthColor ?? 'text.primary' }}
              >
                {growth == null ? '—' : `${growthUp ? '+' : ''}${growth.toFixed(1)}%`}
              </Typography>
            </Stack>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}
