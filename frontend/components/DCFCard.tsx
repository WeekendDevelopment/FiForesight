'use client';

import { Box, Card, CardContent, Stack, Tooltip, Typography } from '@mui/material';
import { DollarSign } from 'lucide-react';
import type { DCFResult } from '../types';

interface Props {
  dcf:          DCFResult;
  isDark:       boolean;
  primaryColor: string;
}

const SCENARIOS = [
  { key: 'bear' as const, label: 'BEAR', color: '#ff0055' },
  { key: 'base' as const, label: 'BASE', color: '#94a3b8' },
  { key: 'bull' as const, label: 'BULL', color: '#00ffa3' },
] as const;

export default function DCFCard({ dcf, isDark, primaryColor }: Props) {
  const mos = dcf.base.upside_pct;

  return (
    <Card>
      <CardContent sx={{ p: '16px !important' }}>
        {/* Header */}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <DollarSign size={16} color={primaryColor} />
            <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
              DCF Intrinsic Value
            </Typography>
          </Stack>
          <Tooltip title="Base-case margin of safety vs current price">
            <Box sx={{
              px: 1, py: 0.25, borderRadius: 1,
              background: mos >= 0 ? '#00ffa322' : '#ff005522',
              border: `1px solid ${mos >= 0 ? '#00ffa3' : '#ff0055'}44`,
            }}>
              <Typography sx={{
                fontSize: '0.62rem', fontWeight: 900,
                color: mos >= 0 ? '#00ffa3' : '#ff0055',
                letterSpacing: '0.07em',
              }}>
                {mos >= 0 ? '+' : ''}{mos.toFixed(1)}% MOS
              </Typography>
            </Box>
          </Tooltip>
        </Stack>

        {/* 3-scenario grid */}
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr 1fr' }, gap: 1.5, mb: 1.5 }}>
          {SCENARIOS.map(({ key, label, color }) => {
            const s = dcf[key];
            return (
              <Box key={key} sx={{
                p: 1.25, borderRadius: 2,
                border: `1px solid ${color}22`,
                background: `${color}08`,
                textAlign: 'center',
              }}>
                <Typography sx={{ fontSize: '0.55rem', fontWeight: 800, color, letterSpacing: '0.1em', mb: 0.5 }}>
                  {label}
                </Typography>
                <Typography sx={{ fontSize: '0.9rem', fontWeight: 900, color, lineHeight: 1.1 }}>
                  ${s.intrinsic_value.toFixed(0)}
                </Typography>
                <Typography sx={{ fontSize: '0.55rem', opacity: 0.55, mt: 0.25 }}>
                  {s.upside_pct >= 0 ? '+' : ''}{s.upside_pct.toFixed(1)}%
                </Typography>
                <Typography sx={{ fontSize: '0.5rem', opacity: 0.3, fontFamily: 'monospace', mt: 0.5 }}>
                  W {s.wacc.toFixed(1)}% · G {s.growth_rate.toFixed(1)}%
                </Typography>
              </Box>
            );
          })}
        </Box>

        {/* Footer: FCF + assumptions */}
        <Typography sx={{ fontSize: '0.65rem', opacity: 0.4, lineHeight: 1.5 }}>
          FCF ${dcf.fcf_billions.toFixed(1)}B · Base WACC {dcf.wacc_base.toFixed(1)}% · Growth {dcf.growth_rate_base.toFixed(1)}% · 5yr DCF + Gordon terminal
        </Typography>
        {dcf.fundamentals_complete === false && (
          <Typography sx={{ fontSize: '0.6rem', color: '#f59e0b', opacity: 0.8, mt: 0.5 }}>
            ⚠ Partial fundamentals — beta/growth defaulted; valuation is lower-confidence.
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
