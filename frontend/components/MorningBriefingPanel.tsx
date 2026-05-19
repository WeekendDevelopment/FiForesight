'use client';
import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Stack, Skeleton,
} from '@mui/material';
import { Activity } from 'lucide-react';

interface IndexEntry {
  ticker: string;
  label: string;
  change_pct: number | null;
  price: number | null;
}

interface Props {
  isDark: boolean;
  primaryColor: string;
}

export default function MorningBriefingPanel({ isDark, primaryColor }: Props) {
  const [indices, setIndices] = useState<IndexEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/briefing')
      .then(r => r.json())
      .then(data => {
        if (data?.indices) setIndices(data.indices);
      })
      .catch(() => { /* non-fatal */ })
      .finally(() => setLoading(false));
  }, []);

  return (
    <Box sx={{
      borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)'}`,
      pb: 1.5,
      mb: 2,
    }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Activity size={13} color={primaryColor} />
        <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1, fontSize: '0.6rem', letterSpacing: 1.5 }}>
          Market Pulse
        </Typography>
      </Stack>

      {loading ? (
        <Stack direction="row" spacing={1} sx={{ overflowX: 'auto', pb: 0.5 }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} variant="rounded" width={80} height={44} sx={{ flexShrink: 0 }} />
          ))}
        </Stack>
      ) : (
        <Stack
          direction="row"
          spacing={0.75}
          sx={{ overflowX: 'auto', pb: 0.5, scrollbarWidth: 'none', '&::-webkit-scrollbar': { display: 'none' } }}
        >
          {indices.map(item => {
            const up = item.change_pct !== null && item.change_pct >= 0;
            const na = item.change_pct === null || item.change_pct === undefined;
            const color = na
              ? (isDark ? '#888' : '#666')
              : up
                ? (isDark ? '#4ade80' : '#16a34a')
                : (isDark ? '#f87171' : '#dc2626');
            const bg = na
              ? (isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)')
              : up
                ? (isDark ? 'rgba(22,101,52,0.25)' : 'rgba(220,252,231,0.65)')
                : (isDark ? 'rgba(153,27,27,0.25)' : 'rgba(254,226,226,0.65)');

            return (
              <Box
                key={item.ticker}
                sx={{
                  flexShrink: 0,
                  background: bg,
                  border: `1px solid ${color}33`,
                  borderRadius: 1.5,
                  px: 1,
                  py: 0.75,
                  minWidth: 76,
                  textAlign: 'center',
                }}
              >
                <Typography sx={{ fontWeight: 800, fontSize: '0.68rem', color, lineHeight: 1.2 }}>
                  {item.label}
                </Typography>
                {item.price !== null && item.price !== undefined && (
                  <Typography sx={{ fontSize: '0.6rem', opacity: 0.7, color, lineHeight: 1.2 }}>
                    {item.price.toFixed(item.price < 10 ? 2 : item.price < 100 ? 2 : 0)}
                  </Typography>
                )}
                <Typography sx={{ fontWeight: 700, fontSize: '0.7rem', color, lineHeight: 1.4 }}>
                  {na
                    ? 'N/A'
                    : `${item.change_pct! >= 0 ? '+' : ''}${item.change_pct!.toFixed(2)}%`}
                </Typography>
              </Box>
            );
          })}
        </Stack>
      )}
    </Box>
  );
}
