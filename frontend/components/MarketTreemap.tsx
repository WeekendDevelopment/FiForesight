'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Paper, Skeleton, Stack, Typography, useMediaQuery, useTheme,
} from '@mui/material';
import type { Theme } from '@mui/material/styles';
import { ResponsiveContainer, Tooltip as ChartTooltip, Treemap } from 'recharts';
import type { TreemapRow } from '../types';

interface Props {
  onSelectTicker: (ticker: string) => void;
}

/** Same palette thresholds as SectorHeatmapPanel — intensity tracks magnitude. */
function changeColor(value: number | null | undefined, theme: Theme): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return theme.palette.grey[700];
  }
  if (value <= -2) return theme.palette.error.dark;
  if (value < -0.5) return theme.palette.error.main;
  if (value <= 0.5) return theme.palette.grey[700];
  if (value < 2) return theme.palette.success.main;
  return theme.palette.success.dark;
}

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function formatCap(value: number | null | undefined): string {
  if (!value) return '—';
  if (value >= 1e12) return `${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `${(value / 1e9).toFixed(0)}B`;
  return `${(value / 1e6).toFixed(0)}M`;
}

/**
 * Custom tile renderer. Depth 1 = sector block (outline only — the gap between
 * blocks is what visually groups sectors); depth 2 = stock tile. Labels drop as
 * tiles shrink (symbol+% → symbol → nothing) so the map stays legible at 320px.
 * The sector caption is drawn inside each sector's largest tile (`sectorLabel`)
 * because SVG paints children over their parent — a depth-1 label would be
 * hidden under the leaf tiles.
 */
function TreemapTile(props: Record<string, unknown>) {
  const { x, y, width, height, depth, theme, onSelect } = props as {
    x: number; y: number; width: number; height: number; depth: number;
    theme: Theme; onSelect: (t: string) => void;
  };
  const d = (props.symbol !== undefined ? props : (props.payload ?? {})) as Partial<TreemapRow> & {
    sectorLabel?: string;
  };
  if (!width || !height || width <= 0 || height <= 0) return <g />;

  const gap = theme.palette.background.default;

  if (depth === 1) {
    return (
      <g>
        <rect x={x} y={y} width={width} height={height} fill="none" stroke={gap} strokeWidth={3} />
      </g>
    );
  }
  if (depth !== 2 || !d.symbol) return <g />;

  const fill = changeColor(d.changePct, theme);
  const showBoth = width > 55 && height > 28;
  const showSymbol = width > 34 && height > 16;
  const symbolSize = Math.min(13, Math.max(9, width / 6));
  const cx = x + width / 2;
  const cy = y + height / 2;

  return (
    <g
      onClick={() => onSelect(d.symbol as string)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(d.symbol as string);
        }
      }}
      role="button"
      tabIndex={0}
      style={{ cursor: 'pointer' }}
      aria-label={`Load ${d.symbol} in the main chart`}
    >
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke={gap} strokeWidth={1} />
      {d.sectorLabel && width > 80 && height > 44 && (
        <text
          x={x + 5}
          y={y + 12}
          fill="rgba(255,255,255,0.6)"
          fontSize={8}
          fontWeight={700}
          letterSpacing={0.8}
          pointerEvents="none"
        >
          {d.sectorLabel.toUpperCase()}
        </text>
      )}
      {showBoth ? (
        <>
          <text
            x={cx} y={cy - 2} textAnchor="middle" fill="#fff"
            fontSize={symbolSize} fontWeight={800} pointerEvents="none"
          >
            {d.symbol}
          </text>
          <text
            x={cx} y={cy + symbolSize} textAnchor="middle" fill="rgba(255,255,255,0.85)"
            fontSize={Math.max(8, symbolSize - 3)} fontWeight={600} pointerEvents="none"
          >
            {formatPct(d.changePct)}
          </text>
        </>
      ) : showSymbol ? (
        <text
          x={cx} y={cy + 3.5} textAnchor="middle" fill="#fff"
          fontSize={9} fontWeight={700} pointerEvents="none"
        >
          {d.symbol}
        </text>
      ) : null}
    </g>
  );
}

type TooltipNode = Partial<TreemapRow> & { companyName?: string };

function MapTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload?: TooltipNode } & TooltipNode>;
}) {
  // Recharts nests the node under entry.payload; fall back to the entry itself.
  const d = payload?.[0]?.payload ?? payload?.[0];
  if (!active || !d?.symbol) return null;
  const company = d.companyName && d.companyName !== d.symbol ? ` · ${d.companyName}` : '';
  return (
    <Paper elevation={6} sx={{ p: 1.25, pointerEvents: 'none', maxWidth: 240 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 800, lineHeight: 1.3 }}>
        {d.symbol}{company}
      </Typography>
      <Typography variant="caption" display="block" color="text.secondary">
        {d.sector}
      </Typography>
      <Typography variant="caption" display="block">
        Mkt cap: {formatCap(d.marketCap)}
      </Typography>
      <Typography variant="caption" display="block" sx={{ fontWeight: 700 }}>
        {formatPct(d.changePct)} today
      </Typography>
    </Paper>
  );
}

export default function MarketTreemap({ onSelectTicker }: Props) {
  const theme = useTheme();
  const downSm = useMediaQuery(theme.breakpoints.down('sm'));
  const downLg = useMediaQuery(theme.breakpoints.down('lg'));
  const height = downSm ? 380 : downLg ? 520 : 640;

  const [rows, setRows] = useState<TreemapRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const refresh = () => {
      fetch('/api/market/treemap', { signal: controller.signal })
        .then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((data: TreemapRow[]) => {
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
    return () => { cancelled = true; controller.abort(); clearInterval(interval); };
  }, []);

  // Nest rows into sector blocks (sectors by total cap desc, stocks by cap
  // desc inside each). The largest stock of each sector carries the sector
  // caption — see TreemapTile for why the parent node can't draw it.
  const data = useMemo(() => {
    const bySector = new Map<string, TreemapRow[]>();
    for (const r of rows) {
      if (!r.marketCap) continue;
      const list = bySector.get(r.sector) ?? [];
      list.push(r);
      bySector.set(r.sector, list);
    }
    return Array.from(bySector.entries())
      .map(([sector, stocks]) => {
        const children = [...stocks].sort((a, b) => b.marketCap - a.marketCap);
        return {
          name: sector,
          totalCap: children.reduce((s, r) => s + r.marketCap, 0),
          children: children.map((r, i) => ({
            ...r,
            name: r.symbol,        // Recharts nameKey — the tile identity
            companyName: r.name,   // preserved for the tooltip
            size: r.marketCap,
            sectorLabel: i === 0 ? sector : undefined,
          })),
        };
      })
      .sort((a, b) => b.totalCap - a.totalCap);
  }, [rows]);

  const legend: Array<{ color: string; label: string }> = [
    { color: theme.palette.error.dark, label: '≤ −2%' },
    { color: theme.palette.error.main, label: '−2 … −0.5%' },
    { color: theme.palette.grey[700], label: '±0.5%' },
    { color: theme.palette.success.main, label: '+0.5 … 2%' },
    { color: theme.palette.success.dark, label: '≥ +2%' },
  ];

  if (loading) {
    return <Skeleton variant="rounded" height={height} />;
  }
  if (error && rows.length === 0) {
    return <Alert severity="warning">Market map data unavailable</Alert>;
  }

  return (
    <Box>
      {/* overflow:hidden stops the fixed-width SVG contributing min-content width —
          without it the flex <main> can't shrink on viewport resize, so the
          ResponsiveContainer's ResizeObserver never fires and the map can't reflow. */}
      <Box sx={{ width: '100%', height, overflow: 'hidden' }}>
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={data}
            dataKey="size"
            aspectRatio={4 / 3}
            isAnimationActive={false}
            content={<TreemapTile theme={theme} onSelect={onSelectTicker} />}
          >
            <ChartTooltip content={<MapTooltip />} />
          </Treemap>
        </ResponsiveContainer>
      </Box>

      <Stack
        direction="row"
        flexWrap="wrap"
        alignItems="center"
        columnGap={1.5}
        rowGap={0.5}
        sx={{ mt: 1.5 }}
      >
        <Typography variant="caption" sx={{ fontWeight: 700, opacity: 0.7 }}>
          Today&apos;s change:
        </Typography>
        {legend.map(item => (
          <Stack key={item.label} direction="row" alignItems="center" spacing={0.5}>
            <Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: item.color }} />
            <Typography variant="caption" color="text.secondary">{item.label}</Typography>
          </Stack>
        ))}
        <Typography variant="caption" color="text.secondary" sx={{ opacity: 0.7 }}>
          · tile size = market cap
        </Typography>
      </Stack>
    </Box>
  );
}
