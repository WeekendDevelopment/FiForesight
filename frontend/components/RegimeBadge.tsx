'use client';

import { Chip, Tooltip } from '@mui/material';
import { TrendingUp, TrendingDown, Minus, HelpCircle } from 'lucide-react';

interface Props {
  regime: string;
  confidence: number;            // 0..1
  barsInCurrentRegime?: number;
}

// regime → { icon, label, colour }. `Minus` stands in for a flat / sideways
// market (lucide has no TrendingFlat icon).
const REGIME_META: Record<string, { Icon: typeof TrendingUp; label: string; color: string }> = {
  trending_up:   { Icon: TrendingUp,   label: 'Trending Up',   color: '#00ffa3' },
  ranging:       { Icon: Minus,        label: 'Ranging',       color: '#f59e0b' },
  trending_down: { Icon: TrendingDown, label: 'Trending Down', color: '#ff0055' },
  unknown:       { Icon: HelpCircle,   label: 'Regime N/A',    color: '#94a3b8' },
};

export default function RegimeBadge({ regime, confidence, barsInCurrentRegime = 0 }: Props) {
  const meta = REGIME_META[regime] ?? REGIME_META.unknown;
  const pct = Math.round((confidence ?? 0) * 100);
  const { Icon, label, color } = meta;

  const tooltip =
    regime === 'unknown'
      ? 'Market Regime — not enough history to classify.'
      : `Market Regime — ${pct}% confidence, ${barsInCurrentRegime} bars in current state.`;

  return (
    <Tooltip title={tooltip} arrow>
      <Chip
        size="small"
        icon={<Icon size={13} color={color} />}
        label={regime === 'unknown' ? label : `${label} · ${pct}%`}
        sx={{
          height: 22,
          background: `${color}1a`,
          border: `1px solid ${color}44`,
          color,
          fontSize: '0.6rem',
          fontWeight: 800,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          '& .MuiChip-icon': { ml: 0.5, mr: -0.25 },
          '& .MuiChip-label': { px: 0.75 },
        }}
      />
    </Tooltip>
  );
}
