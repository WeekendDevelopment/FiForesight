'use client';

import Box from '@mui/material/Box';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';

interface Weights { prophet: number; sarima: number; rf: number; }

interface Props {
  weights: Weights;
  isDark: boolean;
}

const MODELS = [
  { key: 'prophet' as const, label: 'Prophet', color: '#f97316' },
  { key: 'sarima'  as const, label: 'SARIMA',  color: '#60a5fa' },
  { key: 'rf'      as const, label: 'RF',       color: '#34d399' },
];

export default function ModelWeightBar({ weights, isDark }: Props) {
  const total = weights.prophet + weights.sarima + weights.rf || 1;
  const pcts  = MODELS.map(m => ({ ...m, pct: weights[m.key] / total }));
  const textColor = isDark ? 'rgba(220,220,220,0.55)' : 'rgba(20,30,50,0.55)';
  const dominant  = pcts.reduce((a, b) => a.pct > b.pct ? a : b);

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
        <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: textColor, textTransform: 'uppercase' }}>
          Ensemble Weights
        </Typography>
        <Typography sx={{ fontSize: 10, color: dominant.color, fontWeight: 700 }}>
          {dominant.label} dominant ({(dominant.pct * 100).toFixed(0)}%)
        </Typography>
      </Box>

      {/* Stacked bar */}
      <Box sx={{ display: 'flex', height: 14, borderRadius: 1, overflow: 'hidden', width: '100%' }}>
        {pcts.map(({ key, label, color, pct }) => (
          <Tooltip key={key} title={`${label}: ${(pct * 100).toFixed(1)}%`} placement="top" arrow>
            <Box
              sx={{
                width: `${pct * 100}%`,
                bgcolor: color,
                transition: 'width 0.4s ease',
                cursor: 'default',
                '&:hover': { filter: 'brightness(1.2)' },
              }}
            />
          </Tooltip>
        ))}
      </Box>

      {/* Legend */}
      <Box sx={{ display: 'flex', gap: 2, mt: 0.75 }}>
        {pcts.map(({ key, label, color, pct }) => (
          <Box key={key} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: color, flexShrink: 0 }} />
            <Typography sx={{ fontSize: 10, color: textColor }}>
              {label} <span style={{ color, fontWeight: 700 }}>{(pct * 100).toFixed(0)}%</span>
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
