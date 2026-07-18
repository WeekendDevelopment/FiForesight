'use client';

import { Box, Card, CardContent, Chip, Skeleton, Stack, Typography } from '@mui/material';
import { AlertTriangle, Banknote, CheckCircle2, Clock, Shield, Target, TrendingUp } from 'lucide-react';
import type { TradeSetupResponse } from '../types';
import { formatPrice } from '../lib/currency';

interface Props {
  setup:        TradeSetupResponse | null;
  loading:      boolean;
  isDark:       boolean;
  primaryColor: string;
  currency?:    string | null;  // active display currency (F35)
  fx?:          number | null;  // display-time multiplier (1 = native)
}

export default function TradeSetupCard({ setup, loading, isDark, primaryColor, currency = 'USD', fx }: Props) {
  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';
  const amber = isDark ? '#ffb020' : '#b45309';
  const money = (v: number) => formatPrice(v * (fx ?? 1), currency);

  if (loading) {
    return <Skeleton variant="rectangular" height={140} sx={{ borderRadius: 2 }} />;
  }
  if (!setup) return null;

  // Coherence gate (Feature: signal coherence). `actionable === false` means the
  // setup contradicts the 5-day forecast, the trend is mixed, or reward < risk —
  // we surface the reason instead of presenting misleading entry/stop/targets.
  const actionable = setup.actionable !== false;
  const dirColor   = setup.direction === 'Short' ? red
                   : setup.direction === 'Long'  ? green : amber;

  return (
    <Card>
      <CardContent sx={{ p: '16px !important' }}>
        {/* Header row */}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Target size={16} color={primaryColor} />
            <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
              Swing Setup · 5D
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1}>
            {setup.direction && (
              <Chip
                label={setup.direction === 'Neutral' ? 'NO TRADE' : setup.direction.toUpperCase()}
                size="small"
                sx={{
                  fontSize: '0.65rem', fontWeight: 800, letterSpacing: '0.04em',
                  background: `${dirColor}22`, color: dirColor,
                  border: `1px solid ${dirColor}66`,
                }}
              />
            )}
            <Chip
              label={setup.setup_type}
              size="small"
              sx={{
                fontSize: '0.65rem', fontWeight: 700,
                background: `${primaryColor}22`, color: primaryColor,
                border: `1px solid ${primaryColor}44`,
              }}
            />
            {actionable && (
              <Chip
                label={`R:R ${setup.risk_reward}`}
                size="small"
                sx={{
                  fontSize: '0.65rem', fontWeight: 700,
                  background: `${green}18`, color: green,
                  border: `1px solid ${green}44`,
                }}
              />
            )}
          </Stack>
        </Stack>

        {/* ── Non-actionable: explain the conflict instead of faking a trade ── */}
        {!actionable ? (
          <>
            <Box sx={{
              display: 'flex', gap: 1, alignItems: 'flex-start',
              p: 1.5, mb: 1.5, borderRadius: 2,
              border: `1px solid ${amber}55`, background: `${amber}12`,
            }}>
              <Box sx={{ mt: '1px', flexShrink: 0 }}><AlertTriangle size={15} color={amber} /></Box>
              <Typography sx={{ fontSize: '0.78rem', lineHeight: 1.5, color: amber }}>
                {setup.conflict_note ?? 'No clean setup at current levels.'}
              </Typography>
            </Box>
            {/* Reference levels only — clearly not a recommendation. */}
            <Box sx={{
              display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1,
              px: 1.25, py: 1, borderRadius: 1.5,
              background: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)',
              border: '1px solid rgba(255,255,255,0.06)', opacity: 0.75,
            }}>
              <Typography sx={{ fontSize: '0.65rem', opacity: 0.7, fontFamily: 'monospace' }}>
                Watch range {money(setup.entry_low)}–{money(setup.entry_high)}
              </Typography>
              <Typography sx={{ fontSize: '0.6rem', opacity: 0.45, letterSpacing: '0.05em', fontWeight: 700 }}>
                REFERENCE ONLY · NO POSITION
              </Typography>
            </Box>
          </>
        ) : (
          <>
            {/* 3-column grid */}
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr 1fr' }, gap: 1.5, mb: 1.5 }}>

              {/* Entry zone */}
              <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${primaryColor}22`, background: `${primaryColor}08` }}>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
                  <TrendingUp size={12} color={primaryColor} />
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>ENTRY</Typography>
                </Stack>
                <Typography sx={{ fontSize: '0.8rem', fontWeight: 800, color: primaryColor }}>
                  {money(setup.entry_low)}
                </Typography>
                <Typography sx={{ fontSize: '0.7rem', color: primaryColor, opacity: 0.7 }}>
                  – {money(setup.entry_high)}
                </Typography>
              </Box>

              {/* Stop loss */}
              <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${red}22`, background: `${red}08` }}>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
                  <Shield size={12} color={red} />
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>STOP</Typography>
                </Stack>
                <Typography sx={{ fontSize: '0.8rem', fontWeight: 800, color: red }}>
                  {money(setup.stop_loss)}
                </Typography>
                {setup.atr_14 != null && setup.atr_multiplier != null && (
                  <Typography sx={{ fontSize: '0.55rem', color: red, opacity: 0.65, mt: 0.25, lineHeight: 1.3 }}>
                    ATR-14: {setup.atr_14.toFixed(2)} · entry {setup.stop_loss <= (setup.entry_low + setup.entry_high) / 2 ? '−' : '+'} {setup.atr_multiplier.toFixed(1)}×ATR
                  </Typography>
                )}
              </Box>

              {/* Targets */}
              <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${green}22`, background: `${green}08` }}>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
                  <Target size={12} color={green} />
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>TARGETS</Typography>
                </Stack>
                <Typography sx={{ fontSize: '0.75rem', fontWeight: 800, color: green }}>T1 {money(setup.target_1)}</Typography>
                <Typography sx={{ fontSize: '0.7rem', color: green, opacity: 0.8 }}>T2 {money(setup.target_2)}</Typography>
                <Typography sx={{ fontSize: '0.65rem', color: green, opacity: 0.6 }}>T3 {money(setup.target_3)}</Typography>
              </Box>
            </Box>

            {/* Position sizing */}
            <Box sx={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              px: 1.25, py: 0.75, mb: 1.5, borderRadius: 1.5,
              background: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)',
              border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <Typography sx={{ fontSize: '0.65rem', opacity: 0.5, letterSpacing: '0.06em', fontWeight: 700 }}>
                POSITION SIZE
              </Typography>
              <Stack direction="row" spacing={2} alignItems="center">
                <Typography sx={{ fontSize: '0.72rem', fontWeight: 800, color: primaryColor }}>
                  {setup.suggested_position_pct.toFixed(1)}% of portfolio
                </Typography>
                <Typography sx={{ fontSize: '0.6rem', opacity: 0.4, fontFamily: 'monospace' }}>
                  {setup.risk_pct.toFixed(1)}% risk/share · 1% rule
                </Typography>
              </Stack>
            </Box>

            {/* Entry trigger — a setup is a plan: wait for the candle, don't chase. */}
            {setup.entry_trigger && (() => {
              const confirmed = setup.confirmation === 'confirmed';
              const c = confirmed ? green : amber;
              const Icon = confirmed ? CheckCircle2 : Clock;
              return (
                <Box sx={{
                  display: 'flex', gap: 1, alignItems: 'flex-start',
                  p: 1.25, mb: 1.5, borderRadius: 1.5,
                  border: `1px solid ${c}44`, background: `${c}0f`,
                }}>
                  <Box sx={{ mt: '1px', flexShrink: 0 }}><Icon size={14} color={c} /></Box>
                  <Box>
                    <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, letterSpacing: '0.05em', color: c, mb: 0.25 }}>
                      {confirmed ? 'ENTRY CONFIRMED' : 'ENTRY TRIGGER · PENDING'}
                    </Typography>
                    <Typography sx={{ fontSize: '0.72rem', opacity: 0.8, lineHeight: 1.45 }}>
                      {setup.entry_trigger}
                    </Typography>
                  </Box>
                </Box>
              );
            })()}

            {/* CFD-ready framing — same setup expressed for a CFD broker. */}
            {setup.cfd_note && (
              <Box sx={{
                display: 'flex', gap: 1, alignItems: 'flex-start',
                p: 1.25, mb: 1.5, borderRadius: 1.5,
                border: `1px solid ${primaryColor}33`, background: `${primaryColor}0a`,
              }}>
                <Box sx={{ mt: '1px', flexShrink: 0 }}><Banknote size={14} color={primaryColor} /></Box>
                <Box>
                  <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, letterSpacing: '0.05em', color: primaryColor, mb: 0.25 }}>
                    CFD {setup.cfd_side ? `· ${setup.cfd_side.toUpperCase()}` : ''}
                    {setup.cfd_margin_pct != null ? ` · ~${setup.cfd_margin_pct}% MARGIN` : ''}
                  </Typography>
                  <Typography sx={{ fontSize: '0.72rem', opacity: 0.75, lineHeight: 1.45 }}>
                    {setup.cfd_note}
                  </Typography>
                </Box>
              </Box>
            )}
          </>
        )}

        {/* Rationale (actionable setups only — the note is shown above otherwise) */}
        {actionable && (
          <Typography sx={{ fontSize: '0.78rem', opacity: 0.7, lineHeight: 1.5 }}>
            {setup.rationale}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
