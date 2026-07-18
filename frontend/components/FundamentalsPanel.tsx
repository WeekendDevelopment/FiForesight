'use client';

import {
  Accordion, AccordionDetails, AccordionSummary,
  Box, Card, CardContent, Chip, Divider, Grid, Stack, Typography,
} from '@mui/material';
import { ChevronDown } from 'lucide-react';
import type { PredictionData } from '../types';
import { formatPrice } from '../lib/currency';

interface Props {
  prediction:   PredictionData;
  rsiInfo:      { label: string; color: 'error' | 'success' | 'primary' } | null;
  isDark:       boolean;
  primaryColor: string;
  currency?:    string | null;  // active display currency (F35)
  fx?:          number | null;  // display-time multiplier (1 = native)
}

export default function FundamentalsPanel({ prediction, rsiInfo, isDark, primaryColor, currency = 'USD', fx }: Props) {
  const money = (v: string) => formatPrice(parseFloat(v) * (fx ?? 1), currency);
  return (
    <>
      {/* Forecast summary */}
      <Card sx={{ background: isDark ? 'linear-gradient(135deg, #0d1520 0%, #1a237e 100%)' : 'linear-gradient(135deg, #ffffff 0%, #dbeafe 100%)' }}>
        <CardContent>
          <Typography variant="overline" color="primary.main">5-Day Ensemble Forecast</Typography>
          <Stack spacing={2} sx={{ mt: 2 }}>
            <Box>
              <Typography variant="caption" sx={{ opacity: 0.4 }}>5-DAY HIGH TARGET</Typography>
              <Typography variant="h4" color="success.main">{money(prediction.prediction.highRange)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" sx={{ opacity: 0.4 }}>5-DAY LOW TARGET</Typography>
              <Typography variant="h4" color="error.main">{money(prediction.prediction.lowRange)}</Typography>
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
              // ── Short interest (Feature 15) — FINRA weekly short volume ──
              {
                label: 'SHORT % VOL',
                val: prediction.shortInterest?.short_ratio != null
                  ? `${(prediction.shortInterest.short_ratio * 100).toFixed(1)}%`
                  : 'N/A',
              },
              {
                label: 'DAYS TO COVER',
                val: prediction.shortInterest?.days_to_cover != null
                  ? prediction.shortInterest.days_to_cover.toFixed(1)
                  : 'N/A',
                // Elevated short squeeze risk when it would take >5 days of
                // average volume to cover the short position.
                color: prediction.shortInterest?.days_to_cover != null
                  && prediction.shortInterest.days_to_cover > 5
                  ? (isDark ? '#ff0055' : '#dc2626')
                  : undefined,
              },
            ].map(item => (
              <Grid size={{ xs: 6, sm: 4, md: 3 }} key={item.label}>
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
                  <Grid size={{ xs: 6, sm: 4, md: 3 }} key={item.label}>
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

      {/* Earnings Surprise History (Feature 14) — collapsible; default collapsed
          when no data is available. */}
      {(() => {
        const surprises = prediction.indicators?.earnings_surprise ?? [];
        const hasData = surprises.length > 0;
        return (
          <Card>
            <Accordion
              disableGutters
              defaultExpanded={false}
              sx={{ background: 'transparent', boxShadow: 'none', '&:before': { display: 'none' } }}
            >
              <AccordionSummary expandIcon={<ChevronDown size={16} />} sx={{ px: 2 }}>
                <Typography variant="overline" sx={{ opacity: 0.5 }}>
                  Earnings Surprise History
                </Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ px: 2, pt: 0 }}>
                {hasData ? (
                  <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.72rem' }}>
                    <Box component="thead">
                      <Box component="tr" sx={{ opacity: 0.45, textAlign: 'left' }}>
                        {['Quarter', 'Est', 'Actual', 'Beat/Miss'].map(h => (
                          <Box component="th" key={h} sx={{ py: 0.5, fontWeight: 700, letterSpacing: 0.5 }}>
                            {h}
                          </Box>
                        ))}
                      </Box>
                    </Box>
                    <Box component="tbody">
                      {surprises.map((s, i) => {
                        const beat = s.surprise_pct != null && s.surprise_pct >= 0;
                        const chipColor = s.surprise_pct == null
                          ? 'text.secondary'
                          : beat ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626');
                        return (
                          <Box component="tr" key={i} sx={{ borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'}` }}>
                            <Box component="td" sx={{ py: 0.6, fontWeight: 600 }}>{s.quarter}</Box>
                            <Box component="td" sx={{ py: 0.6 }}>{s.estimate != null ? s.estimate.toFixed(2) : '—'}</Box>
                            <Box component="td" sx={{ py: 0.6 }}>{s.actual != null ? s.actual.toFixed(2) : '—'}</Box>
                            <Box component="td" sx={{ py: 0.6 }}>
                              {s.surprise_pct == null ? (
                                <Typography component="span" sx={{ fontSize: '0.7rem', opacity: 0.5 }}>—</Typography>
                              ) : (
                                <Chip
                                  label={`${beat ? '+' : ''}${s.surprise_pct.toFixed(1)}%`}
                                  size="small"
                                  sx={{
                                    height: 18, fontSize: '0.62rem', fontWeight: 700,
                                    color: chipColor,
                                    bgcolor: `${beat ? (isDark ? 'rgba(0,255,163,0.12)' : 'rgba(22,163,74,0.12)') : (isDark ? 'rgba(255,0,85,0.12)' : 'rgba(220,38,38,0.12)')}`,
                                    '& .MuiChip-label': { px: 0.75 },
                                  }}
                                />
                              )}
                            </Box>
                          </Box>
                        );
                      })}
                    </Box>
                  </Box>
                ) : (
                  <Typography variant="caption" sx={{ opacity: 0.4 }}>
                    Earnings surprise data unavailable for this ticker.
                  </Typography>
                )}
              </AccordionDetails>
            </Accordion>
          </Card>
        );
      })()}
    </>
  );
}
