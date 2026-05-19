'use client';
import React from 'react';
import { Box, Card, CardContent, Typography, Stack } from '@mui/material';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface Props {
  symbol: string;
  explanation: string;
  priceChange: number;  // numeric % change, e.g. +5.2 or -3.1
  isDark: boolean;
  primaryColor: string;
}

export default function WhyDidMoveCard({ symbol, explanation, priceChange, isDark, primaryColor }: Props) {
  const isUp = priceChange >= 0;
  const color = isUp ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626');
  const Icon = isUp ? TrendingUp : TrendingDown;

  return (
    <Card sx={{ border: `1px solid ${color}44`, background: `${color}0d` }}>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Stack direction="row" alignItems="flex-start" spacing={1.5}>
          <Icon size={18} style={{ color, marginTop: 2, flexShrink: 0 }} />
          <Box>
            <Typography variant="caption" sx={{ color, fontWeight: 800, letterSpacing: 1, textTransform: 'uppercase' }}>
              {symbol} {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(1)}% today — Why?
            </Typography>
            <Typography variant="body2" sx={{ mt: 0.5, lineHeight: 1.5, opacity: 0.85, fontSize: '0.8rem' }}>
              {explanation}
            </Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
