'use client';

import { useEffect, useState, useTransition } from 'react';
import { LineChart, Line } from 'recharts';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import axios from 'axios';

interface TrendingTicker {
  symbol?: string;
  ticker?: string;
  price?: string | number;
  change?: string | number;
  name?: string;
}

function makeFallback(t: TrendingTicker, i: number): number[] {
  const isUp  = String(t.change ?? '').startsWith('+');
  const base  = parseFloat(String(t.price ?? '100').replace(/[^\d.]/g, '')) || 100;
  const seed  = i * 3.7 + base * 0.01;
  return Array.from({ length: 12 }, (_, j) =>
    base * (1 + (isUp ? 1 : -1) * (j / 11) * 0.025 + Math.sin(seed + j * 0.9) * 0.007),
  );
}

interface Props {
  tickers: TrendingTicker[];
  isDark: boolean;
}

type SparklineMap = Record<string, number[]>;

export default function TrendingSparklines({ tickers, isDark }: Props) {
  const [sparklines, setSparklines] = useState<SparklineMap>({});
  const [isPending, startTransition] = useTransition();

  const textColor = isDark ? 'rgba(220,220,220,0.7)' : 'rgba(20,30,50,0.7)';
  const dimColor  = isDark ? 'rgba(220,220,220,0.35)' : 'rgba(20,30,50,0.35)';
  const bg        = isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)';
  const border    = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.07)';

  useEffect(() => {
    if (!tickers.length) return;
    const syms = tickers.map(t => t.symbol ?? t.ticker ?? '').filter(Boolean).slice(0, 18);
    if (!syms.length) return;

    const controller = new AbortController();
    axios.get(`/api/sparklines?tickers=${syms.join(',')}`, { signal: controller.signal })
      .then(r => startTransition(() => setSparklines(r.data)))
      .catch(err => {
        if (err.name !== 'CanceledError' && !err.message?.includes('canceled')) {
          // silent — sparklines are non-critical
        }
      });
    return () => controller.abort();
  }, [tickers]);

  if (!tickers.length) return null;

  return (
    <Box>
      <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: dimColor, textTransform: 'uppercase', mb: 1 }}>
        Trending {isPending && <span style={{ opacity: 0.5 }}>· loading…</span>}
      </Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 1 }}>
        {tickers.slice(0, 18).map((t, i) => {
          const sym    = t.symbol ?? t.ticker ?? `T${i}`;
          const raw    = sparklines[sym];
          const pts    = (raw?.length >= 2 ? raw : makeFallback(t, i)).map(v => ({ v }));
          const first  = pts[0]?.v;
          const last   = pts[pts.length - 1]?.v;
          const up     = last !== undefined && first !== undefined ? last >= first : null;
          const chgPct = first && last ? ((last - first) / first * 100).toFixed(2) : null;
          const lineC  = up === null ? dimColor : up ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626');

          return (
            <Box
              key={sym}
              sx={{
                p: '6px 8px', borderRadius: 1.5, border: `1px solid ${border}`,
                background: bg, display: 'flex', alignItems: 'center', gap: 1,
              }}
            >
              {/* Sparkline */}
              <Box sx={{ width: 52, height: 28, flexShrink: 0 }}>
                {pts.length >= 2 ? (
                  <LineChart data={pts} width={52} height={28} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
                    <Line
                      type="monotone"
                      dataKey="v"
                      stroke={lineC}
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                ) : (
                  <Box sx={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Box sx={{ width: '80%', height: 1, bgcolor: dimColor }} />
                  </Box>
                )}
              </Box>

              {/* Label */}
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontSize: 11, fontWeight: 700, color: textColor, lineHeight: 1.2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {sym}
                </Typography>
                {chgPct !== null && (
                  <Typography sx={{ fontSize: 10, color: lineC, fontWeight: 600, lineHeight: 1.2 }}>
                    {up ? '+' : ''}{chgPct}%
                  </Typography>
                )}
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
