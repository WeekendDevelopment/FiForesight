'use client';

import { useState } from 'react';
import {
  Box, Stack, ToggleButton, ToggleButtonGroup, Typography,
} from '@mui/material';
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, YAxis } from 'recharts';
import type { Divergences, SubPanelKey } from '../types';

interface Props {
  stochK?:   number | null;
  stochD?:   number | null;
  adx?:      number | null;
  plusDi?:   number | null;
  minusDi?:  number | null;
  obvHistory?: number[] | null;
  divergences?: Divergences;
  isDark:       boolean;
  primaryColor: string;
}

const LS_KEY = 'fiforesight:subpanels';

const PANELS: { key: SubPanelKey; label: string }[] = [
  { key: 'stoch', label: 'STOCH' },
  { key: 'adx',   label: 'ADX'   },
  { key: 'obv',   label: 'OBV'   },
];

/** A 0–100 gauge with reference lines (Stochastic / ADX). */
function Gauge({
  label, value, color, refs, isDark, max = 100,
}: { label: string; value: number; color: string; refs: number[]; isDark: boolean; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const track = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  return (
    <Box sx={{ flex: '1 1 96px', minWidth: 96 }}>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.3 }}>
        <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, fontWeight: 700 }}>{label}</Typography>
        <Typography sx={{ fontSize: '0.6rem', fontWeight: 800, color }}>{value.toFixed(1)}</Typography>
      </Stack>
      <Box sx={{ position: 'relative', height: 8, borderRadius: 4, background: track }}>
        <Box sx={{ position: 'absolute', inset: 0, width: `${pct}%`, borderRadius: 4, background: color, transition: 'width 0.4s ease' }} />
        {refs.map(r => (
          <Box key={r} sx={{ position: 'absolute', top: -2, bottom: -2, left: `${(r / max) * 100}%`, width: '1px', background: isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.4)' }} />
        ))}
      </Box>
    </Box>
  );
}

/**
 * Optional sub-panels for the price chart (Feature 14): Stochastic, ADX, OBV.
 * Visibility is toggled per panel and persisted in localStorage. Default hidden.
 * Divergence badges are surfaced above the toggle whenever a signal fires.
 */
export default function SignalPanels({
  stochK, stochD, adx, plusDi, minusDi, obvHistory, divergences, isDark, primaryColor,
}: Props) {
  // Lazy initialiser restores the persisted selection without an effect.
  // SignalPanels only renders after a client-side prediction fetch, so there
  // is no SSR pass to mismatch against.
  const [selected, setSelected] = useState<SubPanelKey[]>(() => {
    if (typeof window === 'undefined') return [];
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return parsed.filter((k): k is SubPanelKey => ['stoch', 'adx', 'obv'].includes(k));
        }
      }
    } catch { /* ignore malformed storage */ }
    return [];
  });

  const handleChange = (_e: unknown, vals: SubPanelKey[]) => {
    setSelected(vals);
    try { localStorage.setItem(LS_KEY, JSON.stringify(vals)); } catch { /* ignore */ }
  };

  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';

  const divBadges = divergences ? ([
    { on: divergences.rsi_bullish,  text: 'RSI Div ↑',  color: green },
    { on: divergences.rsi_bearish,  text: 'RSI Div ↓',  color: red   },
    { on: divergences.macd_bullish, text: 'MACD Div ↑', color: green },
    { on: divergences.macd_bearish, text: 'MACD Div ↓', color: red   },
  ].filter(b => b.on)) : [];

  const obvData = (obvHistory ?? []).map((v, i) => ({ i, v }));

  // Only render panel toggles for which we have data.
  const available = PANELS.filter(p =>
    (p.key === 'stoch' && stochK != null) ||
    (p.key === 'adx'   && adx != null)    ||
    (p.key === 'obv'   && obvData.length > 0),
  );

  if (available.length === 0 && divBadges.length === 0) return null;

  return (
    <Box sx={{ mt: 2 }}>
      {divBadges.length > 0 && (
        <Stack direction="row" spacing={1} sx={{ mb: 1.5, flexWrap: 'wrap', gap: 0.5 }}>
          {divBadges.map(b => (
            <Box
              key={b.text}
              sx={{
                px: 1, py: 0.3, borderRadius: 1, border: `1px solid ${b.color}55`,
                background: `${b.color}1a`, color: b.color,
                fontSize: '0.62rem', fontWeight: 800, letterSpacing: 0.5,
              }}
            >
              {b.text}
            </Box>
          ))}
        </Stack>
      )}

      {available.length > 0 && (
        <ToggleButtonGroup
          value={selected}
          onChange={handleChange}
          size="small"
          sx={{ flexWrap: 'wrap', gap: 0.5, mb: 1 }}
        >
          {available.map(p => (
            <ToggleButton key={p.key} value={p.key} sx={{ fontSize: '0.6rem', py: 0.4, px: 1.5, borderRadius: '8px !important' }}>
              {p.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      )}

      <Stack spacing={1.5}>
        {/* Stochastic %K / %D — reference lines at 20 / 80 */}
        {selected.includes('stoch') && stochK != null && (
          <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${primaryColor}22`, background: `${primaryColor}08` }}>
            <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, fontWeight: 700, mb: 0.75, letterSpacing: 0.5 }}>
              STOCHASTIC (14, 3) — ref 20 / 80
            </Typography>
            <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
              <Gauge label="%K" value={stochK} color="#3b82f6" refs={[20, 80]} isDark={isDark} />
              {stochD != null && <Gauge label="%D" value={stochD} color="#f97316" refs={[20, 80]} isDark={isDark} />}
            </Stack>
          </Box>
        )}

        {/* ADX / +DI / −DI — reference line at 25 (trend-strength threshold) */}
        {selected.includes('adx') && adx != null && (
          <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${primaryColor}22`, background: `${primaryColor}08` }}>
            <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, fontWeight: 700, mb: 0.75, letterSpacing: 0.5 }}>
              ADX (14) — ref 25 · {adx >= 25 ? 'trending' : 'ranging'}
            </Typography>
            <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
              <Gauge label="ADX" value={adx} color="#a855f7" refs={[25]} isDark={isDark} />
              {plusDi  != null && <Gauge label="+DI" value={plusDi}  color={green} refs={[]} isDark={isDark} />}
              {minusDi != null && <Gauge label="−DI" value={minusDi} color={red}   refs={[]} isDark={isDark} />}
            </Stack>
          </Box>
        )}

        {/* OBV — area chart of the last 30 values */}
        {selected.includes('obv') && obvData.length > 0 && (
          <Box sx={{ p: 1.5, borderRadius: 2, border: `1px solid ${primaryColor}22`, background: `${primaryColor}08` }}>
            <Typography sx={{ fontSize: '0.6rem', opacity: 0.5, fontWeight: 700, mb: 0.75, letterSpacing: 0.5 }}>
              ON-BALANCE VOLUME (30d)
            </Typography>
            <Box sx={{ width: '100%', height: 90 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={obvData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="obvFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={primaryColor} stopOpacity={0.5} />
                      <stop offset="100%" stopColor={primaryColor} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <YAxis hide domain={['dataMin', 'dataMax']} />
                  <ReferenceLine y={0} stroke={isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)'} />
                  <Tooltip
                    contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}44`, borderRadius: 8, fontSize: 11 }}
                    labelFormatter={() => ''}
                    formatter={(v: number) => [v.toLocaleString(), 'OBV']}
                  />
                  <Area type="monotone" dataKey="v" stroke={primaryColor} strokeWidth={2} fill="url(#obvFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </Box>
          </Box>
        )}
      </Stack>
    </Box>
  );
}
