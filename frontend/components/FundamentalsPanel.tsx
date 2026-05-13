'use client';

import { Box, Card, CardContent, Chip, Divider, Grid, Stack, Typography } from '@mui/material';
import type { PredictionData } from '../types';

interface Props {
  prediction:   PredictionData;
  rsiInfo:      { label: string; color: 'error' | 'success' | 'primary' } | null;
  isDark:       boolean;
  primaryColor: string;
}

export default function FundamentalsPanel({ prediction, rsiInfo, isDark, primaryColor }: Props) {
  return (
    <>
      {/* Forecast summary */}
      <Card sx={{ background: isDark ? 'linear-gradient(135deg, #0d1520 0%, #1a237e 100%)' : 'linear-gradient(135deg, #ffffff 0%, #dbeafe 100%)' }}>
        <CardContent>
          <Typography variant="overline" color="primary.main">5-Day Ensemble Forecast</Typography>
          <Stack spacing={2} sx={{ mt: 2 }}>
            <Box>
              <Typography variant="caption" sx={{ opacity: 0.4 }}>5-DAY HIGH TARGET</Typography>
              <Typography variant="h4" color="success.main">${prediction.prediction.highRange}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" sx={{ opacity: 0.4 }}>5-DAY LOW TARGET</Typography>
              <Typography variant="h4" color="error.main">${prediction.prediction.lowRange}</Typography>
            </Box>
          </Stack>
          <Divider sx={{ my: 2, opacity: 0.1 }} />
          <Typography variant="body2" sx={{ fontStyle: 'italic', opacity: 0.85, lineHeight: 1.6 }}>
            {prediction.analystNote}
          </Typography>
          <Chip
            label={`${prediction.confidence.toUpperCase()} CONFIDENCE`}
            size="small" color="secondary"
            sx={{ mt: 2, fontWeight: 900, fontSize: '0.6rem' }}
          />
        </CardContent>
      </Card>

      {/* Fundamentals */}
      <Card>
        <CardContent>
          <Typography variant="overline" sx={{ opacity: 0.5 }}>Fundamentals & Model Stats</Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {[
              { label: 'MARKET CAP', val: prediction.metrics.market_cap },
              { label: 'P/E RATIO',  val: prediction.metrics.pe_ratio   },
              {
                label: 'RSI',
                val: rsiInfo ? `${prediction.rsi} (${rsiInfo.label})` : `${prediction.rsi}`,
                color: rsiInfo?.color === 'error'   ? (isDark ? '#ff0055' : '#dc2626')
                     : rsiInfo?.color === 'success' ? (isDark ? '#00ffa3' : '#16a34a')
                     : primaryColor,
              },
              { label: '52W RANGE',  val: prediction.metrics.range_52w  },
              {
                label: 'ANN. VOL',
                val: prediction.modelStats?.ann_volatility_pct != null
                  ? `${prediction.modelStats.ann_volatility_pct}%`
                  : '—',
              },
              {
                label: 'TREND SLOPE',
                val: prediction.modelStats?.trend_slope != null
                  ? `${prediction.modelStats.trend_slope > 0 ? '▲' : prediction.modelStats.trend_slope < 0 ? '▼' : '—'} ${Math.abs(prediction.modelStats.trend_slope).toFixed(3)}/day`
                  : '—',
                color: prediction.modelStats?.trend_slope == null ? undefined
                     : prediction.modelStats.trend_slope > 0 ? (isDark ? '#00ffa3' : '#16a34a')
                     : prediction.modelStats.trend_slope < 0 ? (isDark ? '#ff0055' : '#dc2626')
                     : undefined,
              },
              {
                label: 'VS SMA20',
                val: prediction.modelStats?.price_vs_sma20_pct != null
                  ? `${prediction.modelStats.price_vs_sma20_pct > 0 ? '+' : ''}${prediction.modelStats.price_vs_sma20_pct.toFixed(2)}%`
                  : '—',
                color: prediction.modelStats?.price_vs_sma20_pct == null ? undefined
                     : prediction.modelStats.price_vs_sma20_pct > 0  ? (isDark ? '#00ffa3' : '#16a34a')
                     : prediction.modelStats.price_vs_sma20_pct < 0  ? (isDark ? '#ff0055' : '#dc2626')
                     : undefined,
              },
              { label: 'DIVIDEND', val: prediction.metrics.yield },
            ].map(item => (
              <Grid size={6} key={item.label}>
                <Typography variant="caption" sx={{ opacity: 0.4 }}>{item.label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700, color: item.color ?? 'inherit' }}>
                  {item.val}
                </Typography>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>

      {/* Valuation & Growth */}
      {(prediction.metrics.beta || prediction.metrics.forward_pe || prediction.metrics.ev_to_ebitda) && (
        <Card>
          <CardContent>
            <Typography variant="overline" sx={{ opacity: 0.5 }}>Valuation & Growth</Typography>
            {prediction.metrics.industry && prediction.metrics.industry !== 'N/A' && (
              <Typography variant="caption" sx={{ display: 'block', opacity: 0.4, mb: 1 }}>
                {prediction.metrics.industry}
              </Typography>
            )}
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              {([
                {
                  label: 'BETA',
                  val: prediction.metrics.beta ?? 'N/A',
                  tip: 'Market sensitivity. >1 = more volatile than market; <1 = more stable.',
                  color: (() => {
                    const b = parseFloat(prediction.metrics.beta ?? '');
                    if (isNaN(b)) return undefined;
                    return b > 1.5 ? (isDark ? '#ff0055' : '#dc2626')
                         : b < 0.8 ? (isDark ? '#00ffa3' : '#16a34a')
                         : undefined;
                  })(),
                },
                {
                  label: 'FWD P/E',
                  val: prediction.metrics.forward_pe ?? 'N/A',
                  tip: 'Forward P/E based on next 12m estimated earnings. Lower = cheaper.',
                },
                {
                  label: 'PEG RATIO',
                  val: prediction.metrics.peg_ratio ?? 'N/A',
                  tip: 'P/E divided by growth rate. <1 = potentially undervalued; >2 = expensive.',
                  color: (() => {
                    const p = parseFloat(prediction.metrics.peg_ratio ?? '');
                    if (isNaN(p)) return undefined;
                    return p < 1   ? (isDark ? '#00ffa3' : '#16a34a')
                         : p > 2   ? (isDark ? '#ff0055' : '#dc2626')
                         : undefined;
                  })(),
                },
                {
                  label: 'P/B RATIO',
                  val: prediction.metrics.price_to_book ?? 'N/A',
                  tip: 'Price-to-book. <1 = trading below book value.',
                },
                {
                  label: 'EV/EBITDA',
                  val: prediction.metrics.ev_to_ebitda ?? 'N/A',
                  tip: 'Enterprise value vs earnings. <10 often considered value; >20 growth premium.',
                },
                {
                  label: 'FREE CF',
                  val: prediction.metrics.free_cash_flow ?? 'N/A',
                  tip: 'Free cash flow — cash generated after capex. Positive = self-funding.',
                  color: (() => {
                    const fcf = prediction.metrics.free_cash_flow ?? '';
                    if (fcf === 'N/A' || !fcf) return undefined;
                    return fcf.startsWith('-') ? (isDark ? '#ff0055' : '#dc2626')
                                               : (isDark ? '#00ffa3' : '#16a34a');
                  })(),
                },
                {
                  label: 'REV GROWTH',
                  val: prediction.metrics.revenue_growth ?? 'N/A',
                  tip: 'Year-over-year revenue growth rate.',
                  color: (() => {
                    const rg = prediction.metrics.revenue_growth ?? '';
                    if (rg === 'N/A' || !rg) return undefined;
                    return rg.startsWith('-') ? (isDark ? '#ff0055' : '#dc2626')
                                              : (isDark ? '#00ffa3' : '#16a34a');
                  })(),
                },
                {
                  label: 'TOTAL DEBT',
                  val: prediction.metrics.total_debt ?? 'N/A',
                  tip: 'Total balance-sheet debt.',
                },
              ] as { label: string; val: string; tip?: string; color?: string }[])
                .filter(item => item.val && item.val !== 'N/A')
                .map(item => (
                  <Grid size={6} key={item.label}>
                    <Typography variant="caption" sx={{ opacity: 0.4 }}>{item.label}</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700, color: item.color ?? 'inherit' }}>
                      {item.val}
                    </Typography>
                    {item.tip && (
                      <Typography variant="caption" sx={{ opacity: 0.3, fontSize: '0.55rem', display: 'block', lineHeight: 1.3 }}>
                        {item.tip}
                      </Typography>
                    )}
                  </Grid>
                ))}
            </Grid>
          </CardContent>
        </Card>
      )}
    </>
  );
}
