'use client';

import { useState } from 'react';
import {
  Box, Button, Collapse, Typography, useMediaQuery, useTheme,
} from '@mui/material';
import { ChevronDown, ChevronUp } from 'lucide-react';
import {
  Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { FeatureImportance } from '../types';

interface Props {
  importances:  FeatureImportance[];
  isDark:       boolean;
  primaryColor: string;
}

/**
 * Horizontal bar chart of the RandomForest's top-5 feature importances
 * (Feature 14). Rendered below ModelWeightBar. Open on desktop, collapsed on
 * mobile by default.
 */
export default function ModelFeatureImportanceBar({ importances, isDark, primaryColor }: Props) {
  const theme  = useTheme();
  const isXs   = useMediaQuery(theme.breakpoints.down('sm'));
  const [open, setOpen] = useState(!isXs);

  if (!importances || importances.length === 0) return null;

  const textColor = isDark ? 'rgba(220,220,220,0.55)' : 'rgba(20,30,50,0.55)';
  const data = importances.map(d => ({ ...d, pct: +(d.importance * 100).toFixed(1) }));

  return (
    <Box sx={{ width: '100%', mt: 1.5 }}>
      <Button
        size="small"
        variant="text"
        onClick={() => setOpen(o => !o)}
        endIcon={open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        sx={{
          fontSize: 10, fontWeight: 800, letterSpacing: 1.2, p: 0,
          color: textColor, textTransform: 'uppercase',
          '&:hover': { background: 'transparent', color: primaryColor },
        }}
      >
        RF Feature Importance
      </Button>
      <Collapse in={open}>
        <Box sx={{ width: '100%', height: data.length * 30 + 20, mt: 1 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={data}
              margin={{ top: 0, right: 36, bottom: 0, left: 8 }}
            >
              <XAxis type="number" hide domain={[0, 'dataMax']} />
              <YAxis
                type="category"
                dataKey="feature"
                width={92}
                tick={{ fontSize: 10, fill: textColor }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: `${primaryColor}11` }}
                contentStyle={{
                  background: isDark ? '#0d1520' : '#fff',
                  border: `1px solid ${primaryColor}44`,
                  borderRadius: 8, fontSize: 11,
                }}
                formatter={(v: number) => [`${v}%`, 'Importance']}
              />
              <Bar dataKey="pct" radius={[0, 4, 4, 0]} label={{ position: 'right', fontSize: 10, fill: textColor, formatter: (v: number) => `${v}%` }}>
                {data.map((_, i) => (
                  <Cell key={i} fill={primaryColor} fillOpacity={1 - i * 0.13} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Box>
        <Typography sx={{ fontSize: 9, opacity: 0.35, mt: 0.5 }}>
          Most influential lagged OHLCV features driving the RF forecast.
        </Typography>
      </Collapse>
    </Box>
  );
}
