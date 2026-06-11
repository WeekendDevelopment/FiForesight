"use client";

import React from 'react';
import { Box, Card, CardContent, Chip, CircularProgress, Typography } from '@mui/material';
import { AlertTriangle } from 'lucide-react';
import type { ReversalRisk } from '../types';

interface Props {
  risk:         ReversalRisk;
  isDark:       boolean;
  primaryColor: string;
}

function signalColor(signal: ReversalRisk['signal'], isDark: boolean): string {
  if (signal === 'high')   return isDark ? '#ef4444' : '#dc2626';
  if (signal === 'medium') return isDark ? '#f59e0b' : '#d97706';
  return isDark ? '#22c55e' : '#16a34a';
}

export default function ReversalRiskCard({ risk, isDark, primaryColor }: Props) {
  const { risk_pct, signal, top_features, trained_on } = risk;
  const color = signalColor(signal, isDark);
  const bgTrack = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';

  return (
    <Card>
      <CardContent>
        <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
          <AlertTriangle size={14} color={color} />
          Reversal Risk · next 5 days
        </Typography>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2.5 }}>
          {/* Gauge ring */}
          <Box sx={{ position: 'relative', display: 'inline-flex', flexShrink: 0 }}>
            {/* Track */}
            <CircularProgress
              variant="determinate"
              value={100}
              size={76}
              thickness={5}
              sx={{ color: bgTrack }}
            />
            {/* Fill */}
            <CircularProgress
              variant="determinate"
              value={risk_pct}
              size={76}
              thickness={5}
              sx={{ color, position: 'absolute', left: 0, top: 0 }}
            />
            <Box sx={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Typography sx={{ fontWeight: 800, fontSize: '1.05rem', color, lineHeight: 1 }}>
                {risk_pct}%
              </Typography>
            </Box>
          </Box>

          {/* Signal + factors */}
          <Box sx={{ minWidth: 0 }}>
            <Chip
              label={signal.toUpperCase()}
              size="small"
              sx={{ fontWeight: 700, color, bgcolor: `${color}1a`, mb: 0.75, height: 22, fontSize: 11 }}
            />
            {top_features.slice(0, 3).map((f, i) => (
              <Typography key={i} variant="caption" sx={{ display: 'block', opacity: 0.65, lineHeight: 1.6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                · {f}
              </Typography>
            ))}
          </Box>
        </Box>

        <Typography variant="caption" sx={{ display: 'block', mt: 1.25, opacity: 0.4, fontSize: '0.65rem' }}>
          RandomForest · trained on {trained_on} bars · ≥2% drop within 5d · key signals = model-level importances
        </Typography>
      </CardContent>
    </Card>
  );
}
