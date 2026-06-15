"use client";

import React, { useState } from 'react';
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, ReferenceLine, Tooltip,
} from 'recharts';
import { Box, Button, Chip, Collapse, IconButton, Paper, Stack, Tooltip as MuiTooltip, Typography } from '@mui/material';
import { HelpCircle } from 'lucide-react';
import type { RegimeInfo } from '../types';

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
  regime?: RegimeInfo | null;
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
  // Read from the data row directly — percentile lines use tooltipType="none"
  // and p25/p75 aren't rendered as standalone series.
  const row = payload[0]?.payload as Partial<
    Record<'p10' | 'p25' | 'p50' | 'p75' | 'p90', number>
  > | undefined;
  const p10v = row?.p10;
  const p25v = row?.p25;
  const p50v = row?.p50;
  const p75v = row?.p75;
  const p90v = row?.p90;
  return (
    <Paper sx={{
      p: 1.25, background: '#0d1117',
      border: '1px solid rgba(0,242,255,0.2)', fontSize: 12, minWidth: 190,
    }}>
      <Typography variant="caption" fontWeight={700} display="block" sx={{ mb: 0.75, opacity: 0.6 }}>{label}</Typography>
      {[
        { val: p90v, label: '🐂 Best 10%',    color: '#00ffa3' },
        { val: p75v, label: '   75th pctl',    color: 'rgba(0,242,255,0.6)' },
        { val: p50v, label: '📊 Most Likely',  color: '#00f2ff' },
        { val: p25v, label: '   25th pctl',    color: 'rgba(0,242,255,0.6)' },
        { val: p10v, label: '🐻 Worst 10%',   color: '#ff6b6b' },
      ].map(({ val, label: lbl, color }) => val != null && (
        <Box key={lbl} sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
          <Typography variant="caption" sx={{ color }}>{lbl}</Typography>
          <Typography variant="caption" sx={{ color, fontWeight: 700 }}>${val.toFixed(2)}</Typography>
        </Box>
      ))}
      <Typography variant="caption" display="block" sx={{ mt: 0.75, opacity: 0.4, fontSize: 10 }}>
        Shaded bands = likely price range · Cyan lines = sample paths
      </Typography>
    </Paper>
  );
}

// ── Probability bar ────────────────────────────────────────────────────────────

function GainProbBar({ prob_gain }: { prob_gain: number }) {
  const isGain = prob_gain >= 50;
  const sentiment = prob_gain >= 65 ? 'Odds favor a gain'
                  : prob_gain >= 50 ? 'Slightly favors gain'
                  : prob_gain >= 35 ? 'Slightly favors loss'
                  :                   'Odds favor a loss';
  const sentimentColor = prob_gain >= 65 ? '#00ffa3'
                       : prob_gain >= 50 ? '#4ade80'
                       : prob_gain >= 35 ? '#f59e0b'
                       :                   '#ff6b6b';
  return (
    <MuiTooltip
      title={`${prob_gain.toFixed(1)}% of 1,000 simulated paths end above today's price. ${sentiment}.`}
      arrow
    >
      <Box sx={{ flex: 1, minWidth: 140 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
          <Typography variant="caption" sx={{ fontSize: 10, color: '#00ffa3' }}>Gain {prob_gain.toFixed(0)}%</Typography>
          <Typography variant="caption" sx={{ fontSize: 10, color: sentimentColor, fontWeight: 600 }}>{sentiment}</Typography>
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

export default function MonteCarloFanChart({ monteCarlo, currentPrice, symbol, regime }: Props) {
  const [visible, setVisible] = useState(false);
  const [guideOpen, setGuideOpen] = useState(true);

  const { price_range_by_day, paths_sample, n_sims, prob_gain, var_95, p10, p50, p90 } = monteCarlo;

  // Build chart data with stacked band fields for the percentile envelope.
  // Recharts stacked areas render bottom-up, so we split into:
  //   bandBase       = p10                (transparent — just the baseline)
  //   bandOuterLow   = p25 − p10          (outer band, lower half)
  //   bandInner      = p75 − p25          (inner band — "likely" range)
  //   bandOuterHigh  = p90 − p75          (outer band, upper half)
  const data: FanPoint[] = [
    {
      day: 'Now',
      p10: currentPrice, p25: currentPrice, p50: currentPrice,
      p75: currentPrice, p90: currentPrice,
      bandBase: currentPrice, bandOuterLow: 0, bandInner: 0, bandOuterHigh: 0,
      ...Object.fromEntries(paths_sample.map((_, i) => [`path${i}`, currentPrice])),
    },
    ...price_range_by_day.map((d, idx) => ({
      day: `D${d.day}`,
      p10: d.p10, p25: d.p25, p50: d.p50,
      p75: d.p75, p90: d.p90,
      bandBase: d.p10,
      bandOuterLow: d.p25 - d.p10,
      bandInner: d.p75 - d.p25,
      bandOuterHigh: d.p90 - d.p75,
      ...Object.fromEntries(paths_sample.map((path, i) => [`path${i}`, path[idx] ?? d.p50])),
    })),
  ];

  const allP10 = data.map(d => d.p10 as number);
  const allP90 = data.map(d => d.p90 as number);
  const allPathValues = paths_sample.flat();
  const yMin = Math.min(...allP10, ...allPathValues) * 0.985;
  const yMax = Math.max(...allP90, ...allPathValues) * 1.015;

  // Final day percentile values (for end labels)
  const last = price_range_by_day[price_range_by_day.length - 1];

  const CHART_H = 240;

  return (
    <Box sx={{ mt: 1 }}>
      {/* Persistent "How to read" guide — always visible */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.75 }}>
        <Typography variant="caption" sx={{ fontSize: 10, opacity: 0.45, fontStyle: 'italic' }}>
          Monte Carlo: 1,000 &quot;what if?&quot; scenarios for this stock&apos;s price over the next 5 days
          {regime && regime.regime !== 'unknown' && (
            <>  ·  Regime: {regime.regime.replace(/_/g, ' ')} ({Math.round((regime.confidence ?? 0) * 100)}%)</>
          )}
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
              { icon: '📈', term: 'Gain % bar', desc: 'Out of 1,000 simulated futures, this is how many ended above today\'s price. Above 50%? The odds lean in your favor.' },
              { icon: '📊', term: 'Fan Chart', desc: 'Each faint line is one possible future for the stock. The bold cyan line is the middle outcome — where things most likely land. The fan widens because the future gets harder to predict.' },
              { icon: '🐂🐻', term: 'Bull / Bear case', desc: 'The best 10% of outcomes (Bull) and the worst 10% (Bear). 80% of all simulated paths fall between these two lines — that\'s your likely range.' },
              { icon: '⚠️', term: 'VaR 95 (Risk gauge)', desc: 'Stands for "Value at Risk." If you held this stock for 5 days, this is the most you\'d expect to lose in 95 out of 100 scenarios. Lower = safer.' },
              { icon: '🏔️', term: '3D Surface', desc: 'A 3D view where mountain peaks show the most likely price for each day. Taller peak = higher chance of landing there. Open it from the "3D Surface" button.' },
              { icon: '🎲', term: 'How it works', desc: 'The simulation uses the stock\'s real historical data (daily returns and volatility) to generate 1,000 realistic random price paths — like rolling the dice 1,000 times.' },
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
        <MuiTooltip
          title={`VaR 95 = $${var_95.toFixed(2)} per share. In 95 out of 100 simulated scenarios, you wouldn't lose more than this amount per share over 5 days. Think of it as your "reasonable worst case."`}
          arrow
        >
          <Box sx={{ cursor: 'help', textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary" sx={{ textDecoration: 'underline dotted' }}>
              VaR95 ${var_95.toFixed(2)}/share
            </Typography>
            <Typography variant="caption" display="block" sx={{ fontSize: 9, opacity: 0.45 }}>
              Max likely loss per share
            </Typography>
          </Box>
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
                { color: '#00ffa3', label: '🐂 Best 10%' },
                { color: '#00f2ff', label: '📊 Likely Range' },
                { color: '#ff6b6b', label: '🐻 Worst 10%' },
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

                {/* ── Percentile envelope bands (stacked areas) ────────────── */}
                {/* Transparent baseline up to p10 */}
                <Area
                  type="monotone" dataKey="bandBase" stackId="envelope"
                  fill="transparent" stroke="none"
                  isAnimationActive={false} legendType="none" tooltipType="none"
                />
                {/* Outer band lower: p10 → p25 */}
                <Area
                  type="monotone" dataKey="bandOuterLow" stackId="envelope"
                  fill="#00f2ff" fillOpacity={0.06} stroke="none"
                  isAnimationActive={false} legendType="none" tooltipType="none"
                />
                {/* Inner band: p25 → p75 (most likely range) */}
                <Area
                  type="monotone" dataKey="bandInner" stackId="envelope"
                  fill="#00f2ff" fillOpacity={0.14} stroke="none"
                  isAnimationActive={false} legendType="none" tooltipType="none"
                />
                {/* Outer band upper: p75 → p90 */}
                <Area
                  type="monotone" dataKey="bandOuterHigh" stackId="envelope"
                  fill="#00f2ff" fillOpacity={0.06} stroke="none"
                  isAnimationActive={false} legendType="none" tooltipType="none"
                />

                {/* P90 optimistic bound — dashed line at outer edge */}
                <Line
                  type="monotone" dataKey="p90"
                  stroke="#00ffa3" strokeWidth={1} strokeOpacity={0.4} strokeDasharray="4 2"
                  dot={false} isAnimationActive={false} legendType="none" tooltipType="none"
                />
                {/* P10 pessimistic bound — dashed line at outer edge */}
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
              { icon: '🐂', label: 'Best Case', val: p90, color: '#00ffa3', tip: 'If things go really well (top 10% of simulations) — this is a realistic upside target' },
              { icon: '📊', label: 'Most Likely', val: p50, color: '#00f2ff', tip: 'The middle outcome — half of simulations ended above this, half below. Your best single guess.' },
              { icon: '🐻', label: 'Worst Case', val: p10, color: '#ff6b6b', tip: 'If things go poorly (bottom 10% of simulations) — a realistic downside to plan for' },
            ].map(({ icon, label, val, color, tip }) => {
              const pctChange = ((val - currentPrice) / currentPrice) * 100;
              const sign = pctChange >= 0 ? '+' : '';
              return (
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
                    <Typography sx={{ fontSize: 9, color, opacity: 0.7 }}>
                      {sign}{pctChange.toFixed(1)}% from now
                    </Typography>
                    <Typography sx={{ fontSize: 9, opacity: 0.4 }}>
                      at Day 5
                    </Typography>
                  </Box>
                </MuiTooltip>
              );
            })}
          </Stack>
        </Paper>
      )}
    </Box>
  );
}
