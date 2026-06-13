'use client';

import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { LineChart, Line, YAxis } from 'recharts';
import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import type { SparklineTicker } from '../types';

const REFRESH_DEBOUNCE_MS = 5 * 60 * 1000; // 5 min

interface Props {
  tickers:      string[];
  isDark:       boolean;
  extraSymbols?: string[];  // watchlist symbols to append as ?extra=
}

export default function TrendingSparklines({ tickers, isDark, extraSymbols }: Props) {
  const [data,       setData]       = useState<SparklineTicker[]>([]);
  const [loading,    setLoading]    = useState(false);
  const lastFetchRef                = useRef<number>(0);
  const controllerRef               = useRef<AbortController | null>(null);

  const textColor = isDark ? 'rgba(220,220,220,0.7)' : 'rgba(20,30,50,0.7)';
  const dimColor  = isDark ? 'rgba(220,220,220,0.35)' : 'rgba(20,30,50,0.35)';
  const bg        = isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)';
  const border    = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.07)';

  // Stable string keys — prevents refetch storms when parent passes new array references
  const tickerKey = useMemo(() => tickers.map(s => s.toUpperCase()).join(','), [tickers]);
  const extraKey  = useMemo(() => (extraSymbols ?? []).map(s => s.toUpperCase()).join(','), [extraSymbols]);

  const fetchData = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastFetchRef.current < REFRESH_DEBOUNCE_MS) return;
    if (!tickers.length) return;

    // Cancel any in-flight request
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    try {
      const qs = new URLSearchParams({ tickers: tickers.slice(0, 18).join(',') });
      if (extraSymbols?.length) {
        // Deduplicate extras against the base list
        const baseSet  = new Set(tickers.map(s => s.toUpperCase()));
        const uniq     = extraSymbols.filter(s => !baseSet.has(s.toUpperCase())).slice(0, 12);
        if (uniq.length) qs.set('extra', uniq.join(','));
      }
      const res = await fetch(`/api/sparklines?${qs.toString()}`, { signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json() as SparklineTicker[];
      setData(Array.isArray(json) ? json : []);
      lastFetchRef.current = Date.now();
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      // Non-critical; keep stale data if any
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }, [tickerKey, extraKey]);

  // Initial fetch
  useEffect(() => { void fetchData(true); }, [fetchData]);

  // Refresh on tab visibility change (debounced to once per 5 min)
  useEffect(() => {
    const handler = () => { if (document.visibilityState === 'visible') void fetchData(); };
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, [fetchData]);

  // Cleanup on unmount
  useEffect(() => () => { controllerRef.current?.abort(); }, []);

  if (!tickers.length) return null;

  const SKELETON_COUNT = Math.min(tickers.length, 12);

  return (
    <Box>
      <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: dimColor, textTransform: 'uppercase', mb: 1 }}>
        Trending {loading && <span style={{ opacity: 0.5 }}>· refreshing…</span>}
      </Typography>
      <Box sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
        gap: 1,
      }}>
        {loading && data.length === 0
          ? Array.from({ length: SKELETON_COUNT }).map((_, i) => (
              <Skeleton
                key={i}
                variant="rectangular"
                sx={{ borderRadius: 1.5, height: 44, bgcolor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' }}
              />
            ))
          : data.map(ticker => {
              const up     = ticker.change_pct >= 0;
              const lineC  = up
                ? (isDark ? '#00ffa3' : '#16a34a')
                : (isDark ? '#ff0055' : '#dc2626');
              const pts    = (ticker.bars ?? []).map(b => ({ v: b.c }));

              return (
                <Box
                  key={ticker.symbol}
                  sx={{
                    p: '6px 8px', borderRadius: 1.5, border: `1px solid ${border}`,
                    background: bg, display: 'flex', alignItems: 'center', gap: 1,
                    minWidth: 0,
                  }}
                >
                  {/* Sparkline */}
                  <Box sx={{ width: 52, height: 28, flexShrink: 0 }}>
                    {pts.length >= 2 ? (
                      <LineChart data={pts} width={52} height={28} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
                        <YAxis domain={['dataMin', 'dataMax']} hide />
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
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography sx={{ fontSize: 11, fontWeight: 700, color: textColor, lineHeight: 1.2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {ticker.symbol}
                    </Typography>
                    <Typography sx={{ fontSize: 10, color: lineC, fontWeight: 600, lineHeight: 1.2 }}>
                      {up ? '+' : ''}{ticker.change_pct.toFixed(2)}%
                    </Typography>
                  </Box>
                </Box>
              );
            })
        }
      </Box>
    </Box>
  );
}
