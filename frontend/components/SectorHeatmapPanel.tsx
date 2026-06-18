'use client';

import React, { useEffect, useState } from 'react';
import {
  Alert, Box, Card, CardContent, Grid, Link, Skeleton, Stack, ToggleButton,
  ToggleButtonGroup, Tooltip, Typography, useTheme,
} from '@mui/material';
import type { Theme } from '@mui/material/styles';
import { ArrowRight, Grid2X2 } from 'lucide-react';
import type { SectorRow } from '../types';

interface Props {
  onSelectTicker: (ticker: string) => void;
  /** 'full' (default) = dedicated tab with 1D/5D toggle. 'overview' = compact landing strip. */
  variant?: 'full' | 'overview';
  /** Shown as a "View all →" link in the overview variant header. */
  onViewAll?: () => void;
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

export default function SectorHeatmapPanel({ onSelectTicker, variant = 'full', onViewAll }: Props) {
  const theme = useTheme();
  const isOverview = variant === 'overview';
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

  // Overview is denser (1D only); full view offers the 1D/5D toggle.
  const cellSize = isOverview
    ? ({ xs: 4, sm: 3, md: 2 } as const)        // 3 → 4 → 6 per row
    : ({ xs: 6, sm: 4, md: 3, lg: 2 } as const); // 2 → 3 → 4 → 6 per row
  const skeletonH = isOverview ? 56 : 72;
  const activeMode: Mode = isOverview ? '1d' : mode;

  return (
    <Box>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        gap={1}
        sx={{ mb: isOverview ? 1.5 : 2 }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <Grid2X2 size={isOverview ? 14 : 20} color={theme.palette.primary.main} />
          {isOverview ? (
            <Typography variant="overline" sx={{ opacity: 0.6, lineHeight: 1, fontSize: '0.65rem', letterSpacing: 1.5 }}>
              Sector Overview
            </Typography>
          ) : (
            <Typography variant="h6" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
              Sector Performance
            </Typography>
          )}
        </Stack>

        {isOverview ? (
          onViewAll && (
            <Link
              component="button"
              type="button"
              onClick={onViewAll}
              underline="hover"
              sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25, fontSize: '0.72rem', fontWeight: 700 }}
            >
              View all <ArrowRight size={13} />
            </Link>
          )
        ) : (
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
        )}
      </Stack>

      {error && !loading && rows.length === 0 ? (
        <Alert severity="warning">Sector data unavailable</Alert>
      ) : (
        <Grid container spacing={isOverview ? 1 : 1.5}>
          {loading
            ? Array.from({ length: 11 }).map((_, i) => (
                <Grid size={cellSize} key={i}>
                  <Skeleton variant="rounded" height={skeletonH} />
                </Grid>
              ))
            : rows.map(row => {
                const value = activeMode === '1d' ? row.return1d : row.return5d;
                const bg = returnColor(value, theme);
                return (
                  <Grid size={cellSize} key={row.etf}>
                    <Tooltip title={`Click to load ${row.etf} in the main chart`} arrow>
                      <Card
                        onClick={() => onSelectTicker(row.etf)}
                        role="button"
                        tabIndex={0}
                        aria-label={`Load ${row.etf} (${row.sector}) in the main chart`}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectTicker(row.etf); }
                        }}
                        sx={{
                          cursor: 'pointer',
                          background: bg,
                          transition: 'transform 120ms ease, box-shadow 120ms ease',
                          '&:hover': {
                            transform: 'translateY(-2px)',
                            boxShadow: `0 6px 18px ${bg}66`,
                          },
                          '&:focus-visible': {
                            outline: `2px solid ${theme.palette.primary.main}`,
                            outlineOffset: 2,
                          },
                        }}
                      >
                        <CardContent sx={{ p: isOverview ? 1 : 1.5, '&:last-child': { pb: isOverview ? 1 : 1.5 } }}>
                          <Typography
                            variant="caption"
                            noWrap
                            title={row.sector}
                            sx={{ fontWeight: 700, color: '#fff', display: 'block', fontSize: isOverview ? '0.65rem' : undefined }}
                          >
                            {isOverview ? row.etf : row.sector}
                          </Typography>
                          <Typography
                            variant="caption"
                            noWrap
                            title={row.sector}
                            sx={{ color: 'rgba(255,255,255,0.7)', display: 'block', lineHeight: 1.4, fontSize: isOverview ? '0.6rem' : undefined }}
                          >
                            {isOverview ? row.sector : row.etf}
                          </Typography>
                          <Typography
                            variant={isOverview ? 'caption' : 'body2'}
                            sx={{ fontWeight: 800, color: '#fff', mt: 0.5, display: 'block' }}
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
