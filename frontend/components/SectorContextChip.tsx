'use client';

import React, { useEffect, useState } from 'react';
import { Chip, Tooltip } from '@mui/material';
import { ArrowRight } from 'lucide-react';
import type { SectorRow } from '../types';

interface Props {
  /** yfinance sector name from prediction.metrics.sector (e.g. "Financial Services"). */
  sector?: string;
  /** Loads the sector ETF in the analysis flow. */
  onSelectTicker: (etf: string) => void;
  isDark: boolean;
}

// yfinance uses its own sector taxonomy, which differs from GICS / our ETF map.
const YF_SECTOR_TO_ETF: Record<string, string> = {
  'Technology': 'XLK',
  'Financial Services': 'XLF',
  'Healthcare': 'XLV',
  'Consumer Cyclical': 'XLY',
  'Consumer Defensive': 'XLP',
  'Energy': 'XLE',
  'Industrials': 'XLI',
  'Basic Materials': 'XLB',
  'Utilities': 'XLU',
  'Real Estate': 'XLRE',
  'Communication Services': 'XLC',
};

export default function SectorContextChip({ sector, onSelectTicker, isDark }: Props) {
  const etf = sector ? YF_SECTOR_TO_ETF[sector] : undefined;
  // Store the resolved row tagged with its etf so a stale fetch can't paint the
  // wrong sector when the user switches tickers quickly.
  const [resolved, setResolved] = useState<{ etf: string; row: SectorRow | null } | null>(null);

  useEffect(() => {
    if (!etf) return;
    let cancelled = false;
    fetch('/api/sectors/heatmap')
      .then(r => (r.ok ? r.json() : null))
      .then((data: SectorRow[] | null) => {
        if (cancelled || !Array.isArray(data)) return;
        setResolved({ etf, row: data.find(d => d.etf === etf) ?? null });
      })
      .catch(() => { /* non-fatal */ });
    return () => { cancelled = true; };
  }, [etf]);

  // Nothing to show for unmapped sectors (e.g. "N/A", crypto, foreign).
  if (!etf) return null;

  const row = resolved && resolved.etf === etf ? resolved.row : null;

  // Prefer the 5D move (a steadier sector-trend signal); fall back to 1D.
  const pct = row ? (row.return5d ?? row.return1d) : null;
  const window = row && row.return5d !== null ? '5D' : '1D';
  const up = pct !== null && pct >= 0;
  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';
  const color = pct === null ? 'text.secondary' : up ? green : red;

  const pctLabel = pct === null ? '' : ` · ${up ? '+' : ''}${pct.toFixed(2)}% ${window}`;
  const label = `${sector} (${etf})${pctLabel}`;

  return (
    <Tooltip title={`Analyze the ${sector} sector ETF (${etf})`} arrow>
      <Chip
        onClick={() => onSelectTicker(etf)}
        clickable
        icon={<ArrowRight size={14} />}
        label={label}
        size="small"
        sx={{
          fontWeight: 700,
          flexDirection: 'row-reverse',          // arrow trails the label
          '& .MuiChip-icon': { ml: '-2px', mr: '6px', color },
          color,
          border: `1px solid ${pct === null ? (isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.18)') : (up ? `${green}55` : `${red}55`)}`,
          bgcolor: pct === null ? 'transparent' : up
            ? (isDark ? 'rgba(0,255,163,0.08)' : 'rgba(22,163,74,0.08)')
            : (isDark ? 'rgba(255,0,85,0.08)' : 'rgba(220,38,38,0.08)'),
        }}
      />
    </Tooltip>
  );
}
