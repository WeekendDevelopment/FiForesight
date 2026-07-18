'use client';

import {
  Box, Card, CardContent, Skeleton, Stack, Typography, useTheme,
} from '@mui/material';
import { Target } from 'lucide-react';
import type { AnalystTargets } from '../types';
import { formatPrice } from '../lib/currency';

interface Props {
  data:     AnalystTargets | null;
  loading:  boolean;
  currency?: string | null;  // active display currency (F35)
  fx?:       number | null;  // display-time multiplier (1 = native)
}

const RATINGS = [
  { key: 'strongBuy'  as const, label: 'Strong Buy',  color: '#2e7d32' },
  { key: 'buy'        as const, label: 'Buy',         color: '#4caf50' },
  { key: 'hold'       as const, label: 'Hold',        color: '#ed6c02' },
  { key: 'sell'       as const, label: 'Sell',        color: '#ef5350' },
  { key: 'strongSell' as const, label: 'Strong Sell', color: '#c62828' },
] as const;

// Clamp a 0–100 position so absolutely-positioned markers never escape the track.
const clamp = (n: number) => Math.max(0, Math.min(100, n));

export default function AnalystTargetsCard({ data, loading, currency = 'USD', fx }: Props) {
  const theme        = useTheme();
  const warningColor = theme.palette.warning.main;
  const fmt = (v: number | null | undefined) => {
    if (v == null) return '—';
    const scaled = v * (fx ?? 1);
    return formatPrice(scaled, currency, { decimals: scaled >= 100 ? 0 : 2 });
  };

  const header = (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
      <Target size={16} color={theme.palette.primary.main} />
      <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
        Wall St. Targets
      </Typography>
      {data?.numberOfAnalysts != null && (
        <Typography variant="caption" sx={{ opacity: 0.4, ml: 'auto' }}>
          {data.numberOfAnalysts} analyst{data.numberOfAnalysts === 1 ? '' : 's'}
        </Typography>
      )}
    </Stack>
  );

  if (loading) {
    return (
      <Card>
        <CardContent sx={{ p: '16px !important' }}>
          {header}
          <Skeleton variant="rectangular" height={44} sx={{ borderRadius: 1, mb: 1.5 }} />
          <Skeleton variant="rectangular" height={28} sx={{ borderRadius: 1 }} />
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
            Analyst data unavailable
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const { currentPrice, targetLow, targetMean, targetHigh } = data;
  const hasRange =
    currentPrice != null && targetLow != null && targetHigh != null && targetHigh > targetLow;

  // Upside from the current price to the mean target.
  const upsidePct =
    targetMean != null && currentPrice != null && currentPrice > 0
      ? ((targetMean - currentPrice) / currentPrice) * 100
      : null;
  const upsideUp = (upsidePct ?? 0) >= 0;

  // Marker positions along the low→high track (percentages).
  const pos = (price: number) =>
    clamp(((price - targetLow!) / (targetHigh! - targetLow!)) * 100);
  const curPos  = hasRange ? pos(currentPrice!) : 0;
  const meanPos = hasRange && targetMean != null ? pos(targetMean) : 50;

  const anyRatings = RATINGS.some(({ key }) => data[key] > 0);

  return (
    <Card>
      <CardContent sx={{ p: '16px !important' }}>
        {header}

        {hasRange ? (
          <Box sx={{ mb: anyRatings ? 2 : 0 }}>
            {/* Upside-to-mean summary */}
            {upsidePct != null && (
              <Typography
                sx={{
                  fontSize: '0.7rem', fontWeight: 800, mb: 1.5,
                  color: upsideUp ? '#16a34a' : '#dc2626',
                }}
              >
                {upsideUp ? '+' : ''}{upsidePct.toFixed(1)}% to mean
              </Typography>
            )}

            {/* Range bar */}
            <Box sx={{ position: 'relative', height: 56, px: 0.5 }}>
              {/* "Current" label above the marker line */}
              <Box
                sx={{
                  position: 'absolute', top: 0,
                  left: `${clamp(curPos)}%`, transform: 'translateX(-50%)',
                  whiteSpace: 'nowrap', textAlign: 'center',
                }}
              >
                <Typography sx={{ fontSize: '0.55rem', fontWeight: 700, color: warningColor, lineHeight: 1.1 }}>
                  Current
                </Typography>
                <Typography sx={{ fontSize: '0.62rem', fontWeight: 900, color: warningColor, lineHeight: 1.1 }}>
                  {fmt(currentPrice)}
                </Typography>
              </Box>

              {/* Track (low → high) */}
              <Box
                sx={{
                  position: 'absolute', top: 30, left: 0, right: 0, height: 8,
                  borderRadius: 4,
                  background: 'linear-gradient(90deg, #ef535044 0%, #94a3b844 50%, #00ffa344 100%)',
                  border: `1px solid ${theme.palette.divider}`,
                }}
              />

              {/* Mean tick */}
              <Box
                sx={{
                  position: 'absolute', top: 27, left: `${meanPos}%`,
                  transform: 'translateX(-50%)', width: 3, height: 14,
                  borderRadius: 2, background: '#94a3b8',
                }}
              />

              {/* Current-price vertical line */}
              <Box
                sx={{
                  position: 'absolute', top: 22, left: `${curPos}%`,
                  transform: 'translateX(-50%)', width: 2, height: 24,
                  background: warningColor,
                  boxShadow: `0 0 6px ${warningColor}`,
                }}
              />

              {/* Low / Mean / High labels below the track */}
              <Box sx={{ position: 'absolute', top: 42, left: 0 }}>
                <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color: '#ef5350', lineHeight: 1.1 }}>
                  {fmt(targetLow)}
                </Typography>
                <Typography sx={{ fontSize: '0.5rem', opacity: 0.5, lineHeight: 1 }}>Low</Typography>
              </Box>
              <Box
                sx={{
                  position: 'absolute', top: 42, left: `${meanPos}%`,
                  transform: 'translateX(-50%)', textAlign: 'center',
                }}
              >
                <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color: '#94a3b8', lineHeight: 1.1 }}>
                  {fmt(targetMean)}
                </Typography>
                <Typography sx={{ fontSize: '0.5rem', opacity: 0.5, lineHeight: 1 }}>Mean</Typography>
              </Box>
              <Box sx={{ position: 'absolute', top: 42, right: 0, textAlign: 'right' }}>
                <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color: '#16a34a', lineHeight: 1.1 }}>
                  {fmt(targetHigh)}
                </Typography>
                <Typography sx={{ fontSize: '0.5rem', opacity: 0.5, lineHeight: 1 }}>High</Typography>
              </Box>
            </Box>
          </Box>
        ) : (
          !anyRatings && (
            <Typography variant="body2" sx={{ opacity: 0.4 }}>
              No price target range available
            </Typography>
          )
        )}

        {/* Rating breakdown */}
        {anyRatings && (
          <Stack direction="row" flexWrap="wrap" gap={1}>
            {RATINGS.map(({ key, label, color }) => {
              const count = data[key];
              if (count === 0) return null;
              return (
                <Box
                  key={key}
                  sx={{
                    px: 1, py: 0.4, borderRadius: 1,
                    background: `${color}1f`,
                    border: `1px solid ${color}55`,
                    display: 'flex', alignItems: 'center', gap: 0.5,
                  }}
                >
                  <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, color, letterSpacing: '0.02em' }}>
                    {label}
                  </Typography>
                  <Typography sx={{ fontSize: '0.68rem', fontWeight: 900, color }}>
                    {count}
                  </Typography>
                </Box>
              );
            })}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
