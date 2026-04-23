'use client';

import { Box, Typography } from '@mui/material';

export default function ConfidenceBadge({ pct }: { pct: number }) {
  const color = pct >= 70 ? '#00ffa3' : pct >= 50 ? '#00f2ff' : '#f59e0b';
  return (
    <Box sx={{
      display: 'inline-flex', alignItems: 'center', gap: 0.5,
      px: 1, py: 0.25, borderRadius: 1,
      border: `1px solid ${color}44`, background: `${color}11`,
    }}>
      <Box sx={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color }}>{pct}%</Typography>
    </Box>
  );
}
