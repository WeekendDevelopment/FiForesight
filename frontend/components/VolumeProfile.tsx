'use client';

import { useMemo } from 'react';
import { BarChart, Bar, YAxis, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

interface HistoryPoint {
  price: number;
  high?: number;
  low?: number;
  volume?: number;
}

interface Props {
  history: HistoryPoint[];
  isDark: boolean;
  height?: number;
  buckets?: number;
}

export default function VolumeProfile({ history, isDark, height = 380, buckets = 24 }: Props) {
  const data = useMemo(() => {
    if (history.length === 0 || !(Number.isInteger(buckets) && buckets > 0)) return [];
    const prices = history.map(h => h.price);
    const minP   = Math.min(...prices);
    const maxP   = Math.max(...prices);
    const range  = maxP - minP || 1;
    const step   = range / buckets;

    const bins: { price: number; volume: number }[] = Array.from({ length: buckets }, (_, i) => ({
      price:  parseFloat((minP + (i + 0.5) * step).toFixed(2)),
      volume: 0,
    }));

    history.forEach(h => {
      const idx = Math.min(Math.floor((h.price - minP) / step), buckets - 1);
      bins[idx].volume += h.volume ?? 1;
    });

    const maxVol = Math.max(...bins.map(b => b.volume), 1);
    return bins.map(b => ({ ...b, pct: b.volume / maxVol }));
  }, [history, buckets]);

  const currentPrice = history[history.length - 1]?.price ?? 0;
  const textColor    = isDark ? 'rgba(220,220,220,0.6)' : 'rgba(20,30,50,0.6)';
  const barColor     = isDark ? '#60a5fa' : '#2563eb';
  const poaColor     = isDark ? '#00ffa3' : '#16a34a';

  return (
    <Box sx={{ width: 72, height, display: 'flex', flexDirection: 'column' }}>
      <Typography sx={{ fontSize: 9, fontWeight: 800, letterSpacing: 1.2, color: textColor, textTransform: 'uppercase', mb: 0.3, textAlign: 'center' }}>
        Vol Profile
      </Typography>
      <Box sx={{ flex: 1 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 0, bottom: 0, left: 0 }}
            barCategoryGap={1}
          >
            <YAxis dataKey="price" type="number" domain={['dataMin', 'dataMax']} hide />
            <Tooltip
              cursor={false}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload;
                return (
                  <Box sx={{ background: isDark ? '#1e293b' : '#fff', border: '1px solid #334155', borderRadius: 1, px: 1, py: 0.5 }}>
                    <Typography sx={{ fontSize: 10, color: textColor }}>${d.price.toFixed(2)}</Typography>
                    <Typography sx={{ fontSize: 10, color: barColor }}>{d.volume.toLocaleString()} vol</Typography>
                  </Box>
                );
              }}
            />
            <Bar dataKey="pct" maxBarSize={60} isAnimationActive={false}>
              {data.map((entry, i) => {
                const isNear = Math.abs(entry.price - currentPrice) < (data[1]?.price - data[0]?.price) * 1.2;
                return <Cell key={i} fill={isNear ? poaColor : barColor + '99'} />;
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}
