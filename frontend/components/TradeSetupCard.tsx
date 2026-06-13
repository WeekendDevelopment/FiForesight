'use client';

import { Box, Card, CardContent, Chip, Skeleton, Stack, Typography } from '@mui/material';
import { Shield, Target, TrendingUp } from 'lucide-react';
import type { TradeSetupResponse } from '../types';

interface Props {
  setup:        TradeSetupResponse | null;
  loading:      boolean;
  isDark:       boolean;
  primaryColor: string;
}

export default function TradeSetupCard({ setup, loading, isDark, primaryColor }: Props) {
  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';

  if (loading) {
    return <Skeleton variant="rectangular" height={140} sx={{ borderRadius: 2 }} />;
  }
  if (!setup) return null;

  return (
    <Card>
      <CardContent sx={{ p: '16px !important' }}>
        {/* Header row */}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Target size={16} color={primaryColor} />
            <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
              Trade Setup
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Chip
              label={setup.setup_type}
              size="small"
              sx={{
                fontSize: '0.65rem', fontWeight: 700,
                background: `${primaryColor}22`, color: primaryColor,
                border: `1px solid ${primaryColor}44`,
              }}
            />
            <Chip
              label={`R:R ${setup.risk_reward}`}
              size="small"
              sx={{
                fontSize: '0.65rem', fontWeight: 700,
                background: `${green}18`, color: green,
                border: `1px solid ${green}44`,
              }}
            />
          </Stack>
        </Stack>

        {/* 3-column grid */}
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr 1fr' }, gap: 1.5, mb: 1.5 }}>

          {/* Entry zone */}
          <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${primaryColor}22`, background: `${primaryColor}08` }}>
            <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
              <TrendingUp size={12} color={primaryColor} />
              <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>ENTRY</Typography>
            </Stack>
            <Typography sx={{ fontSize: '0.8rem', fontWeight: 800, color: primaryColor }}>
              ${setup.entry_low.toFixed(2)}
            </Typography>
            <Typography sx={{ fontSize: '0.7rem', color: primaryColor, opacity: 0.7 }}>
              – ${setup.entry_high.toFixed(2)}
            </Typography>
          </Box>

          {/* Stop loss */}
          <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${red}22`, background: `${red}08` }}>
            <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
              <Shield size={12} color={red} />
              <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>STOP</Typography>
            </Stack>
            <Typography sx={{ fontSize: '0.8rem', fontWeight: 800, color: red }}>
              ${setup.stop_loss.toFixed(2)}
            </Typography>
            {setup.atr_14 != null && setup.atr_multiplier != null && (
              <Typography sx={{ fontSize: '0.55rem', color: red, opacity: 0.65, mt: 0.25, lineHeight: 1.3 }}>
                ATR-14: {setup.atr_14.toFixed(2)} · entry − {setup.atr_multiplier}×ATR
              </Typography>
            )}
          </Box>

          {/* Targets */}
          <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${green}22`, background: `${green}08` }}>
            <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.75 }}>
              <Target size={12} color={green} />
              <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, letterSpacing: '0.07em', fontWeight: 700 }}>TARGETS</Typography>
            </Stack>
            <Typography sx={{ fontSize: '0.75rem', fontWeight: 800, color: green }}>T1 ${setup.target_1.toFixed(2)}</Typography>
            <Typography sx={{ fontSize: '0.7rem', color: green, opacity: 0.8 }}>T2 ${setup.target_2.toFixed(2)}</Typography>
            <Typography sx={{ fontSize: '0.65rem', color: green, opacity: 0.6 }}>T3 ${setup.target_3.toFixed(2)}</Typography>
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

        {/* Rationale */}
        <Typography sx={{ fontSize: '0.78rem', opacity: 0.7, lineHeight: 1.5 }}>
          {setup.rationale}
        </Typography>
      </CardContent>
    </Card>
  );
}
