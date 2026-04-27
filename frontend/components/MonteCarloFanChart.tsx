"use client";

import React, { useState } from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, ReferenceLine, Tooltip, ReferenceArea,
} from 'recharts';
import { Box, Button, Chip, Collapse, IconButton, Paper, Stack, Tooltip as MuiTooltip, Typography } from '@mui/material';
import { HelpCircle } from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface MonteCarloResult {
  p10: number;
  p50: number;
  p90: number;
  prob_gain: number;
  var_95: number;
  paths_sample: number[][];
  price_range_by_day: Array<{
    day: number;
    p10: number;
    p25: number;
    p50: number;
    p75: number;
    p90: number;
  }>;
  n_sims: number;
}

interface Props {
  monteCarlo: MonteCarloResult;
  currentPrice: number;
  symbol: string;
}

type FanPoint = {
  day: string;
  [key: string]: number | string;
};

// ── Custom tooltip ─────────────────────────────────────────────────────────────

function FanTooltip({ active, payload, label }: {
  active?: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload?: any[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const get = (key: string) => payload.find((p: any) => p.dataKey === key)?.value as number | undefined;
  const p50v = get('p50');
  const p10v = get('p10');
  const p90v = get('p90');
  return (
    <Paper sx={{
      p: 1.25, background: '#0d1117',
      border: '1px solid rgba(0,242,255,0.2)', fontSize: 12, minWidth: 170,
    }}>
      <Typography variant="caption" fontWeight={700} display="block" sx={{ mb: 0.75, opacity: 0.6 }}>{label}</Typography>
      {p90v != null && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
          <Typography variant="caption" sx={{ color: '#00ffa3' }}>🐂 Optimistic</Typography>
          <Typography variant="caption" sx={{ color: '#00ffa3', fontWeight: 700 }}>${p90v.toFixed(2)}</Typography>
        </Box>
      )}
      {p50v != null && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
          <Typography variant="caption" sx={{ color: '#00f2ff' }}>📊 Most Likely</Typography>
          <Typography variant="caption" sx={{ color: '#00f2ff', fontWeight: 700 }}>${p50v.toFixed(2)}</Typography>
        </Box>
      )}
      {p10v != null && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
          <Typography variant="caption" sx={{ color: '#ff6b6b' }}>🐻 Pessimistic</Typography>
          <Typography variant="caption" sx={{ color: '#ff6b6b', fontWeight: 700 }}>${p10v.toFixed(2)}</Typography>
        </Box>
      )}
      <Typography variant="caption" display="block" sx={{ mt: 0.75, opacity: 0.4, fontSize: 10 }}>
        Each cyan line = 1 simulated price path
      </Typography>
    </Paper>
  );
}

// ── Probability bar ────────────────────────────────────────────────────────────

function GainProbBar({ prob_gain }: { prob_gain: number }) {
  const isGain = prob_gain >= 50;
  return (
    <MuiTooltip
      title={`${prob_gain.toFixed(1)}% of simulated paths end above the current price (gain scenario). ${(100 - prob_gain).toFixed(1)}% end below (loss scenario).`}
      arrow
    >
      <Box sx={{ flex: 1, minWidth: 140 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
          <Typography variant="caption" sx={{ fontSize: 10, color: '#00ffa3' }}>Gain {prob_gain.toFixed(0)}%</Typography>
          <Typography variant="caption" sx={{ fontSize: 10, color: '#ff6b6b' }}>Loss {(100 - prob_gain).toFixed(0)}%</Typography>
        </Box>
        <Box sx={{ position: 'relative', height: 6, borderRadius: 3, overflow: 'hidden', background: '#ff6b6b44' }}>
          <Box sx={{
            position: 'absolute', left: 0, top: 0, bottom: 0,
            width: `${prob_gain}%`,
            background: isGain ? '#00ffa3' : '#f59e0b',
            borderRadius: 3,
            transition: 'width 0.5s ease',
          }} />
        </Box>
      </Box>
    </MuiTooltip>
  );
}

// ── End-of-fan labels rendered as custom SVG ──────────────────────────────────

function EndLabels({ p10, p50, p90, yMin, yMax, chartH }: {
  p10: number; p50: number; p90: number;
  yMin: number; yMax: number; chartH: number;
}) {
  const toY = (v: number) => chartH - ((v - yMin) / (yMax - yMin)) * chartH;
  return (
    <g>
      {[
        { val: p90, label: `🐂 $${p90.toFixed(0)}`, color: '#00ffa3' },
        { val: p50, label: `📊 $${p50.toFixed(0)}`, color: '#00f2ff' },
        { val: p10, label: `🐻 $${p10.toFixed(0)}`, color: '#ff6b6b' },
      ].map(({ val, label, color }) => (
        <text key={label} x={4} y={toY(val)} fill={color} fontSize={9} fontWeight={700} dominantBaseline="middle">
          {label}
        </text>
      ))}
    </g>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function MonteCarloFanChart({ monteCarlo, currentPrice, symbol }: Props) {
  const [visible, setVisible] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);

  const { price_range_by_day, paths_sample, n_sims, prob_gain, var_95, p10, p50, p90 } = monteCarlo;

  const data: FanPoint[] = [
    {
      day: 'Now',
      p10: currentPrice,
      p90: currentPrice,
      p50: currentPrice,
      ...Object.fromEntries(paths_sample.map((_, i) => [`path${i}`, currentPrice])),
    },
    ...price_range_by_day.map((d, idx) => ({
      day: `D${d.day}`,
      p10: d.p10,
      p90: d.p90,
      p50: d.p50,
      ...Object.fromEntries(paths_sample.map((path, i) => [`path${i}`, path[idx]])),
    })),
  ];

  const allP10 = data.map(d => d.p10 as number);
  const allP90 = data.map(d => d.p90 as number);
  const yMin = Math.min(...allP10) * 0.985;
  const yMax = Math.max(...allP90) * 1.015;

  // Final day percentile values (for end labels)
  const last = price_range_by_day[price_range_by_day.length - 1];

  // Gain zone: above currentPrice; Loss zone: below currentPrice
  const gainZoneTop    = yMax;
  const gainZoneBottom = currentPrice;
  const lossZoneTop    = currentPrice;
  const lossZoneBottom = yMin;

  const CHART_H = 240;

  return (
    <Box sx={{ mt: 1 }}>
      {/* Persistent "How to read" guide — always visible */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.75 }}>
        <Typography variant="caption" sx={{ fontSize: 10, opacity: 0.45, fontStyle: 'italic' }}>
          Monte Carlo: 1,000 simulated price paths using GBM
        </Typography>
        <MuiTooltip title="Show/hide guide" arrow>
          <IconButton size="small" aria-label="Toggle Monte Carlo guide" onClick={() => setGuideOpen(o => !o)} sx={{ p: 0.25, color: guideOpen ? '#7c4dff' : 'rgba(124,77,255,0.4)' }}>
            <HelpCircle size={13} />
          </IconButton>
        </MuiTooltip>
      </Box>

      <Collapse in={guideOpen}>
        <Paper sx={{ p: 1.25, mb: 1, background: 'rgba(124,77,255,0.06)', border: '1px solid rgba(124,77,255,0.2)', borderRadius: 1.5 }}>
          <Typography sx={{ fontSize: 10, fontWeight: 700, color: '#7c4dff', mb: 0.75 }}>How to read Monte Carlo charts</Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.75 }}>
            {[
              { icon: '📈', term: 'Gain % bar', desc: 'How many simulated paths ended above today\'s price — higher = more likely to profit.' },
              { icon: '📊', term: 'MC Fan Chart', desc: 'Each cyan line = one simulated future. The bold line is the median (most likely). The fan spreads wider over time because uncertainty grows.' },
              { icon: '🐂🐻', term: 'Bull / Bear case', desc: 'Top 10% of paths (Bull) and bottom 10% (Bear). 80% of paths land between these lines.' },
              { icon: '⚠️', term: 'VaR 95', desc: 'Value at Risk: the maximum expected loss in 95% of scenarios over 5 days. Think of it as a "worst normal day" estimate.' },
              { icon: '🏔️', term: '3D Surface', desc: 'Each mountain shows where prices are most likely on that day. Taller peak = higher probability. The surface fans out because uncertainty grows.' },
              { icon: '🎲', term: 'GBM model', desc: 'Paths follow Geometric Brownian Motion: drift (avg daily return) + volatility (daily std dev) estimated from the full available price history.' },
            ].map(({ icon, term, desc }) => (
              <Box key={term} sx={{ display: 'flex', gap: 0.5, alignItems: 'flex-start' }}>
                <Typography sx={{ fontSize: 11, lineHeight: 1.2, flexShrink: 0 }}>{icon}</Typography>
                <Box>
                  <Typography sx={{ fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.75)', lineHeight: 1.2 }}>{term}</Typography>
                  <Typography sx={{ fontSize: 9, opacity: 0.5, lineHeight: 1.3 }}>{desc}</Typography>
                </Box>
              </Box>
            ))}
          </Box>
        </Paper>
      </Collapse>

      {/* Toggle row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1, flexWrap: 'wrap' }}>
        <Button
          size="small"
          variant={visible ? 'contained' : 'outlined'}
          onClick={() => setVisible(v => !v)}
          sx={{
            fontSize: 11, py: 0.25, px: 1.5,
            ...(visible
              ? { background: 'rgba(0,242,255,0.18)', color: '#00f2ff', border: '1px solid rgba(0,242,255,0.5)' }
              : { borderColor: 'rgba(0,242,255,0.3)', color: 'rgba(0,242,255,0.6)' }),
          }}
        >
          {visible ? 'Hide Fan Chart' : 'MC Fan Chart'}
        </Button>
        <GainProbBar prob_gain={prob_gain} />
        <MuiTooltip title="Value at Risk (95%): the maximum expected loss in 95% of scenarios over 5 days." arrow>
          <Typography variant="caption" color="text.secondary" sx={{ cursor: 'help', textDecoration: 'underline dotted' }}>
            VaR95 ${var_95.toFixed(2)}
          </Typography>
        </MuiTooltip>
      </Box>

      {visible && (
        <Paper sx={{
          p: 1.5, mt: 0.5,
          border: '1px solid rgba(0,242,255,0.15)',
          background: 'rgba(0,242,255,0.02)',
        }}>
          {/* Header + legend */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1, flexWrap: 'wrap', gap: 0.5 }}>
            <Box>
              <Typography variant="caption" color="text.secondary" display="block">
                {symbol} · {n_sims.toLocaleString()} simulated price paths over 5 days
              </Typography>
              <Typography variant="caption" sx={{ fontSize: 10, opacity: 0.45 }}>
                Each line is one possible future. The bold cyan line is the most likely outcome.
              </Typography>
            </Box>
            <Stack direction="row" spacing={0.75} flexWrap="wrap">
              {[
                { color: '#00ffa3', label: '🐂 Optimistic' },
                { color: '#00f2ff', label: '📊 Most Likely' },
                { color: '#ff6b6b', label: '🐻 Pessimistic' },
              ].map(({ color, label }) => (
                <Chip
                  key={label}
                  label={label}
                  size="small"
                  sx={{ fontSize: 9, height: 18, bgcolor: `${color}18`, color, border: `1px solid ${color}33` }}
                />
              ))}
            </Stack>
          </Box>

          <Box sx={{ position: 'relative', minWidth: 0 }}>
            <ResponsiveContainer width="100%" height={CHART_H}>
              <ComposedChart data={data} margin={{ top: 8, right: 56, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#64748b' }} interval="preserveStartEnd" />
                <YAxis
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  tickFormatter={v => `$${(v as number).toFixed(0)}`}
                  domain={[yMin, yMax]}
                  width={62}
                  tickCount={6}
                />
                <Tooltip content={<FanTooltip />} />

                {/* Gain zone — green tint above current price */}
                <ReferenceArea
                  y1={gainZoneBottom}
                  y2={gainZoneTop}
                  fill="#00ffa3"
                  fillOpacity={0.04}
                  strokeOpacity={0}
                />
                {/* Loss zone — red tint below current price */}
                <ReferenceArea
                  y1={lossZoneBottom}
                  y2={lossZoneTop}
                  fill="#ff6b6b"
                  fillOpacity={0.04}
                  strokeOpacity={0}
                />

                {/* P90 optimistic bound */}
                <Line
                  type="monotone" dataKey="p90"
                  stroke="#00ffa3" strokeWidth={1} strokeOpacity={0.4} strokeDasharray="4 2"
                  dot={false} isAnimationActive={false} legendType="none" tooltipType="none"
                />
                {/* P10 pessimistic bound */}
                <Line
                  type="monotone" dataKey="p10"
                  stroke="#ff6b6b" strokeWidth={1} strokeOpacity={0.4} strokeDasharray="4 2"
                  dot={false} isAnimationActive={false} legendType="none" tooltipType="none"
                />

                {/* 50 sample paths */}
                {paths_sample.map((_, i) => (
                  <Line
                    key={`path${i}`}
                    type="monotone" dataKey={`path${i}`}
                    stroke="#00f2ff" strokeWidth={0.6} strokeOpacity={0.10}
                    dot={false} isAnimationActive={false} legendType="none" tooltipType="none"
                  />
                ))}

                {/* P50 median — bold, most likely */}
                <Line
                  type="monotone" dataKey="p50"
                  stroke="#00f2ff" strokeWidth={2.5}
                  dot={false} isAnimationActive={false} legendType="none" tooltipType="none"
                />

                {/* Current price anchor */}
                <ReferenceLine
                  y={currentPrice}
                  stroke="rgba(245,158,11,0.6)"
                  strokeDasharray="4 3"
                  label={({ viewBox }: any) => {
                    const { x, y, width } = viewBox;
                    return (
                      <g>
                        <text x={(x ?? 0) + (width ?? 0) + 4} y={y} fill="#f59e0b" fontSize={9} dominantBaseline="middle">
                          Current ${currentPrice.toFixed(2)}
                        </text>
                        <text x={(x ?? 0) + (width ?? 0) + 4} y={(y ?? 0) + 10} fill="#f59e0b" fontSize={8} dominantBaseline="middle" opacity={0.6}>
                          ← Break-even line
                        </text>
                      </g>
                    );
                  }}
                />
              </ComposedChart>
            </ResponsiveContainer>

            {/* End-of-fan price labels rendered over the right margin */}
            {last && (
              <Box sx={{
                position: 'absolute', top: 8, right: 0, width: 52, height: CHART_H - 12,
                pointerEvents: 'none',
              }}>
                <svg width="52" height={CHART_H - 12}>
                  <EndLabels
                    p10={last.p10} p50={last.p50} p90={last.p90}
                    yMin={yMin} yMax={yMax} chartH={CHART_H - 12}
                  />
                </svg>
              </Box>
            )}
          </Box>

          {/* Summary row — Bull / Base / Bear */}
          <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: 'wrap', gap: 0.75 }}>
            {[
              { icon: '🐂', label: 'Bull Case', val: p90, color: '#00ffa3', tip: 'Top 10% of scenarios — strong upside' },
              { icon: '📊', label: 'Base Case', val: p50, color: '#00f2ff', tip: 'Median outcome — most paths land here' },
              { icon: '🐻', label: 'Bear Case', val: p10, color: '#ff6b6b', tip: 'Bottom 10% of scenarios — worst expected move' },
            ].map(({ icon, label, val, color, tip }) => (
              <MuiTooltip key={label} title={tip} arrow>
                <Box sx={{
                  flex: 1, minWidth: 80, textAlign: 'center',
                  p: 0.75, borderRadius: 1,
                  background: `${color}0d`,
                  border: `1px solid ${color}22`,
                  cursor: 'help',
                }}>
                  <Typography sx={{ fontSize: 11 }}>{icon} {label}</Typography>
                  <Typography sx={{ fontSize: 13, fontWeight: 800, color }}>
                    ${val.toFixed(2)}
                  </Typography>
                  <Typography sx={{ fontSize: 9, opacity: 0.5 }}>
                    at Day 5
                  </Typography>
                </Box>
              </MuiTooltip>
            ))}
          </Stack>
        </Paper>
      )}
    </Box>
  );
}
