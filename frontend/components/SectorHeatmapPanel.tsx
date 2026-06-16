'use client';

import React, { useEffect, useState } from 'react';
import {
  Alert, Box, Card, CardContent, Grid, Skeleton, Stack, ToggleButton,
  ToggleButtonGroup, Tooltip, Typography, useTheme,
} from '@mui/material';
import type { Theme } from '@mui/material/styles';
import { Grid2X2 } from 'lucide-react';
import type { SectorRow } from '../types';

interface Props {
  onSelectTicker: (ticker: string) => void;
}

type Mode = '1d' | '5d';

/** Map a return % to a cell background — intensity tracks magnitude. */
function returnColor(value: number | null, theme: Theme): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return theme.palette.grey[700];
  }
  if (value <= -2) return theme.palette.error.dark;     // #b71c1c
  if (value < -0.5) return theme.palette.error.main;    // #ef5350
  if (value <= 0.5) return theme.palette.grey[700];     // ±0.5% flat
  if (value < 2) return theme.palette.success.main;     // #4caf50
  return theme.palette.success.dark;                    // #1b5e20
}

function formatPct(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

export default function SectorHeatmapPanel({ onSelectTicker }: Props) {
  const theme = useTheme();
  const [rows, setRows] = useState<SectorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [mode, setMode] = useState<Mode>('1d');

  useEffect(() => {
    let cancelled = false;

    const refresh = () => {
      fetch('/api/sectors/heatmap')
        .then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((data: SectorRow[]) => {
          if (cancelled) return;
          if (Array.isArray(data)) {
            setRows(data);
            setError(false);
          } else {
            setError(true);
          }
        })
        .catch(() => { if (!cancelled) setError(true); })
        .finally(() => { if (!cancelled) setLoading(false); });
    };

    refresh();
    const interval = setInterval(refresh, 300_000); // 5 min
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  // Responsive: 2/row on phones, 3 on tablet, 4 on laptop, 6 on desktop.
  const cellSize = { xs: 6, sm: 4, md: 3, lg: 2 } as const;

  return (
    <Box>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        gap={1}
        sx={{ mb: 2 }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <Grid2X2 size={20} color={theme.palette.primary.main} />
          <Typography variant="h6" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
            Sector Performance
          </Typography>
        </Stack>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={mode}
          onChange={(_, v: Mode | null) => { if (v) setMode(v); }}
          aria-label="Return window"
        >
          <ToggleButton value="1d" aria-label="1 day">1D</ToggleButton>
          <ToggleButton value="5d" aria-label="5 day">5D</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {error && !loading && rows.length === 0 ? (
        <Alert severity="warning">Sector data unavailable</Alert>
      ) : (
        <Grid container spacing={1.5}>
          {loading
            ? Array.from({ length: 11 }).map((_, i) => (
                <Grid size={cellSize} key={i}>
                  <Skeleton variant="rounded" height={72} />
                </Grid>
              ))
            : rows.map(row => {
                const value = mode === '1d' ? row.return1d : row.return5d;
                const bg = returnColor(value, theme);
                return (
                  <Grid size={cellSize} key={row.etf}>
                    <Tooltip title={`Click to load ${row.etf} in the main chart`} arrow>
                      <Card
                        onClick={() => onSelectTicker(row.etf)}
                        sx={{
                          cursor: 'pointer',
                          background: bg,
                          transition: 'transform 120ms ease, box-shadow 120ms ease',
                          '&:hover': {
                            transform: 'translateY(-2px)',
                            boxShadow: `0 6px 18px ${bg}66`,
                          },
                        }}
                      >
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Typography
                            variant="caption"
                            noWrap
                            title={row.sector}
                            sx={{ fontWeight: 700, color: '#fff', display: 'block' }}
                          >
                            {row.sector}
                          </Typography>
                          <Typography
                            variant="caption"
                            sx={{ color: 'rgba(255,255,255,0.7)', display: 'block', lineHeight: 1.4 }}
                          >
                            {row.etf}
                          </Typography>
                          <Typography
                            variant="body2"
                            sx={{ fontWeight: 800, color: '#fff', mt: 0.5 }}
                          >
                            {formatPct(value)}
                          </Typography>
                        </CardContent>
                      </Card>
                    </Tooltip>
                  </Grid>
                );
              })}
        </Grid>
      )}
    </Box>
  );
}
