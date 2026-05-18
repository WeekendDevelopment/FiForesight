'use client';
import React, { useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Typography, Stack, Skeleton,
} from '@mui/material';
import { Grid2X2 } from 'lucide-react';

interface SectorEntry {
  ticker: string;
  label: string;
  change_pct: number | null;
  price?: number | null;
}

interface Props {
  isDark: boolean;
  primaryColor: string;
}

function getSectorColor(change_pct: number | null, isDark: boolean): { bg: string; text: string } {
  if (change_pct === null || change_pct === undefined) {
    return {
      bg: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)',
      text: isDark ? '#888' : '#666',
    };
  }
  if (change_pct > 1) {
    return {
      bg: isDark ? 'rgba(22,101,52,0.45)' : 'rgba(220,252,231,0.85)',
      text: isDark ? '#4ade80' : '#166534',
    };
  }
  if (change_pct > 0) {
    return {
      bg: isDark ? 'rgba(22,101,52,0.22)' : 'rgba(220,252,231,0.50)',
      text: isDark ? '#86efac' : '#15803d',
    };
  }
  if (change_pct > -1) {
    return {
      bg: isDark ? 'rgba(153,27,27,0.22)' : 'rgba(254,226,226,0.50)',
      text: isDark ? '#fca5a5' : '#b91c1c',
    };
  }
  return {
    bg: isDark ? 'rgba(153,27,27,0.45)' : 'rgba(254,226,226,0.85)',
    text: isDark ? '#f87171' : '#991b1b',
  };
}

export default function SectorHeatmap({ isDark, primaryColor }: Props) {
  const [sectors, setSectors] = useState<SectorEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/sectors')
      .then(r => r.json())
      .then(data => {
        if (data?.sectors) setSectors(data.sectors);
      })
      .catch(() => { /* non-fatal */ })
      .finally(() => setLoading(false));
  }, []);

  return (
    <Card sx={{
      border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'}`,
      background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.7)',
    }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
          <Grid2X2 size={14} color={primaryColor} />
          <Typography variant="overline" sx={{ opacity: 0.6, lineHeight: 1, fontSize: '0.65rem', letterSpacing: 1.5 }}>
            Sector Overview
          </Typography>
        </Stack>

        {loading ? (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
            {Array.from({ length: 11 }).map((_, i) => (
              <Skeleton key={i} variant="rounded" width={88} height={56} />
            ))}
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
            {sectors.map(s => {
              const { bg, text } = getSectorColor(s.change_pct, isDark);
              const sign = s.change_pct !== null && s.change_pct !== undefined
                ? (s.change_pct >= 0 ? '+' : '')
                : '';
              return (
                <Box
                  key={s.ticker}
                  sx={{
                    background: bg,
                    borderRadius: 1.5,
                    px: 1,
                    py: 0.75,
                    minWidth: 84,
                    textAlign: 'center',
                    border: `1px solid ${text}33`,
                  }}
                >
                  <Typography sx={{ fontWeight: 800, fontSize: '0.72rem', color: text, lineHeight: 1.2 }}>
                    {s.ticker}
                  </Typography>
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.7, lineHeight: 1.3, color: text }}>
                    {s.label}
                  </Typography>
                  <Typography sx={{ fontWeight: 700, fontSize: '0.75rem', color: text, lineHeight: 1.4 }}>
                    {s.change_pct !== null && s.change_pct !== undefined
                      ? `${sign}${s.change_pct.toFixed(2)}%`
                      : 'N/A'}
                  </Typography>
                </Box>
              );
            })}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
