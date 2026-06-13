'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Skeleton from '@mui/material/Skeleton';
import IconButton from '@mui/material/IconButton';
import Button from '@mui/material/Button';
import Link from 'next/link';
import { X, Star } from 'lucide-react';
import { LineChart, Line, YAxis } from 'recharts';
import { useWatchlistContext } from '../../../contexts/WatchlistContext';
import { useAppShell } from '../../../contexts/AppShellContext';
import { useAuth } from '../../../contexts/AuthContext';
import AuthModal from '../../../components/AuthModal';
import type { SparklineTicker } from '../../../types';

export default function WatchlistPage() {
  const { watchlist, isLoading: wlLoading, remove } = useWatchlistContext();
  const { isDark, primaryColor }                     = useAppShell();
  const { session }                                  = useAuth();
  const [authOpen,    setAuthOpen]    = useState(false);
  const [sparklines,  setSparklines]  = useState<SparklineTicker[]>([]);
  const [splLoading,  setSplLoading]  = useState(false);

  const symbolKey = useMemo(
    () => watchlist.map(i => i.symbol).join(','),
    [watchlist],
  );

  const fetchSparklines = useCallback(async () => {
    if (!symbolKey) { setSparklines([]); return; }
    setSplLoading(true);
    try {
      const res  = await fetch(`/api/sparklines?tickers=${encodeURIComponent(symbolKey)}`);
      const data = await res.json() as SparklineTicker[];
      setSparklines(Array.isArray(data) ? data : []);
    } catch { /* non-fatal */ } finally {
      setSplLoading(false);
    }
  }, [symbolKey]);

  useEffect(() => { void fetchSparklines(); }, [fetchSparklines]);

  const splMap = useMemo(() => {
    const m: Record<string, SparklineTicker> = {};
    sparklines.forEach(s => { m[s.symbol] = s; });
    return m;
  }, [sparklines]);

  const textColor = isDark ? 'rgba(220,220,220,0.85)' : 'rgba(20,30,50,0.85)';
  const dimColor  = isDark ? 'rgba(220,220,220,0.45)' : 'rgba(20,30,50,0.45)';
  const cardBg    = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.02)';
  const borderCol = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)';

  if (!session) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 260, gap: 2, textAlign: 'center' }}>
        <Star size={36} color={dimColor} />
        <Typography sx={{ color: dimColor, fontSize: 14 }}>Sign in to save and view your watchlist.</Typography>
        <Button variant="outlined" size="small" onClick={() => setAuthOpen(true)}>Sign In</Button>
        <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
      </Box>
    );
  }

  if (wlLoading) {
    return (
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 1.5 }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} variant="rectangular" height={76} sx={{ borderRadius: 2 }} />
        ))}
      </Box>
    );
  }

  if (!watchlist.length) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 260, gap: 1.5, textAlign: 'center' }}>
        <Star size={36} color={dimColor} />
        <Typography sx={{ color: dimColor, fontSize: 14 }}>Your watchlist is empty.</Typography>
        <Typography sx={{ color: dimColor, fontSize: 12 }}>
          Tap ☆ on any Analysis page to add a stock.
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Typography sx={{ fontSize: 11, fontWeight: 800, letterSpacing: 1.2, color: dimColor, textTransform: 'uppercase', mb: 2 }}>
        Watchlist · {watchlist.length} {watchlist.length === 1 ? 'symbol' : 'symbols'}
      </Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 1.5 }}>
        {watchlist.map(item => {
          const spl   = splMap[item.symbol];
          const up    = spl ? spl.change_pct >= 0 : null;
          const lineC = up === null
            ? dimColor
            : (up ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626'));
          const pts = spl ? (spl.bars ?? []).map(b => ({ v: b.c })) : [];

          return (
            <Box
              key={item.symbol}
              sx={{
                position: 'relative', p: 1.5, borderRadius: 2,
                border: `1px solid ${borderCol}`, bgcolor: cardBg,
                transition: 'border-color 0.15s',
                '&:hover': { borderColor: `${primaryColor}55` },
              }}
            >
              {/* Remove from watchlist */}
              <IconButton
                size="small"
                onClick={() => remove(item.symbol)}
                aria-label={`Remove ${item.symbol}`}
                sx={{
                  position: 'absolute', top: 4, right: 4,
                  width: 22, height: 22, opacity: 0.45,
                  '&:hover': { opacity: 1 },
                  '& svg': { width: 12, height: 12 },
                }}
              >
                <X />
              </IconButton>

              {/* Card body → analysis page */}
              <Box
                component={Link}
                href={`/analysis?symbol=${encodeURIComponent(item.symbol)}`}
                sx={{ display: 'flex', alignItems: 'center', gap: 1.5, pr: 2, textDecoration: 'none' }}
              >
                {/* Sparkline */}
                <Box sx={{ width: 64, height: 36, flexShrink: 0 }}>
                  {splLoading && !spl ? (
                    <Skeleton variant="rectangular" width={64} height={36} sx={{ borderRadius: 1 }} />
                  ) : pts.length >= 2 ? (
                    <LineChart data={pts} width={64} height={36} margin={{ top: 3, right: 2, bottom: 3, left: 2 }}>
                      <YAxis domain={['dataMin', 'dataMax']} hide />
                      <Line type="monotone" dataKey="v" stroke={lineC} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                    </LineChart>
                  ) : (
                    <Box sx={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Box sx={{ width: '85%', height: 1, bgcolor: dimColor, opacity: 0.4 }} />
                    </Box>
                  )}
                </Box>

                {/* Price info */}
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography sx={{ fontSize: 13, fontWeight: 700, color: textColor, lineHeight: 1.3 }}>
                    {item.symbol}
                  </Typography>
                  {spl ? (
                    <Typography sx={{ fontSize: 11, fontWeight: 600, color: lineC, lineHeight: 1.2 }}>
                      ${spl.price.toFixed(2)}&nbsp;·&nbsp;{up ? '+' : ''}{spl.change_pct.toFixed(2)}%
                    </Typography>
                  ) : (
                    <Typography sx={{ fontSize: 11, color: dimColor }}>–</Typography>
                  )}
                </Box>
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
