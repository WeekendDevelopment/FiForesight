"use client";

import React from 'react';
import { Box, Card, CardContent, Chip, Typography } from '@mui/material';
import { TrendingUp, TrendingDown } from 'lucide-react';
import type { DirectionForecast } from '../types';

interface Props {
  forecast:     DirectionForecast;
  isDark:       boolean;
  primaryColor: string;
}

function directionColor(direction: 'up' | 'down', isDark: boolean): string {
  if (direction === 'up')   return isDark ? '#22c55e' : '#16a34a';
  return isDark ? '#ef4444' : '#dc2626';
}

export default function DirectionForecastCard({ forecast, isDark }: Props) {
  const { direction, confidence_pct, edge_pct, top_features, trained_on } = forecast;
  const color  = directionColor(direction, isDark);
  const isUp   = direction === 'up';
  const Icon   = isUp ? TrendingUp : TrendingDown;
  const bgGlow = `${color}18`;

  return (
    <Card>
      <CardContent>
        <Typography variant="overline" sx={{ opacity: 0.6, display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
          <Icon size={14} color={color} />
          Next-day direction · RF classifier
        </Typography>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2.5 }}>
          {/* Direction badge */}
          <Box sx={{
            width: 76, height: 76, borderRadius: '50%', flexShrink: 0,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            bgcolor: bgGlow, border: `2px solid ${color}`,
          }}>
            <Icon size={28} color={color} strokeWidth={2.5} />
            <Typography sx={{ fontWeight: 800, fontSize: '0.8rem', color, lineHeight: 1.2, mt: 0.25 }}>
              {confidence_pct}%
            </Typography>
          </Box>

          {/* Direction label + signals */}
          <Box sx={{ minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
              <Chip
                label={isUp ? 'BULLISH' : 'BEARISH'}
                size="small"
                sx={{ fontWeight: 700, color, bgcolor: bgGlow, height: 22, fontSize: 11 }}
              />
              <Chip
                label={`+${edge_pct}% edge`}
                size="small"
                variant="outlined"
                sx={{ fontWeight: 600, color, borderColor: `${color}60`, height: 22, fontSize: 10 }}
              />
            </Box>
            {top_features.slice(0, 3).map((f, i) => (
              <Typography key={i} variant="caption" sx={{ display: 'block', opacity: 0.65, lineHeight: 1.6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                · {f}
              </Typography>
            ))}
          </Box>
        </Box>

        <Typography variant="caption" sx={{ display: 'block', mt: 1.25, opacity: 0.4, fontSize: '0.65rem' }}>
          RandomForest · trained on {trained_on} bars · key signals = model-level importances
        </Typography>
      </CardContent>
    </Card>
  );
}
