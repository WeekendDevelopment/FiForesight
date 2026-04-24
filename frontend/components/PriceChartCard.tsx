'use client';

import React, { useState, useMemo, useRef, useEffect } from 'react';
import {
  Box, Card, CardContent, Chip, Collapse, Stack, Typography,
  ToggleButton, ToggleButtonGroup, Button,
} from '@mui/material';
import { Info, ChevronDown, ChevronUp } from 'lucide-react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Line, ReferenceLine, ComposedChart, Area, Legend,
  BarChart, Bar, Cell,
} from 'recharts';
import dynamic from 'next/dynamic';
import VolumeProfile from './VolumeProfile';
import type { PredictionData, IndicatorKey, ChartEntry, ChartStats, IndicatorSignals } from '../types';

const AdvancedChart = dynamic(() => import('./AdvancedChart'), { ssr: false });

const CHART_HEIGHT = 380;

interface Props {
  prediction:      PredictionData;
  indicators:      IndicatorKey[];
  setIndicators:   (v: IndicatorKey[]) => void;
  chartMode:       'line' | 'candle';
  setChartMode:    (v: 'line' | 'candle') => void;
  chartEngine:     'classic' | 'pro';
  setChartEngine:  (v: 'classic' | 'pro') => void;
  isDark:          boolean;
  primaryColor:    string;
  trendColor:      string;
  chartStats:      ChartStats | null;
  indicatorSignals: IndicatorSignals;
}

export default function PriceChartCard({
  prediction, indicators, setIndicators,
  chartMode, setChartMode, chartEngine, setChartEngine,
  isDark, primaryColor, trendColor, chartStats, indicatorSignals,
}: Props) {
  const [legendOpen, setLegendOpen] = useState(false);
  const chartBoxRef = useRef<HTMLDivElement>(null);
  const [clipBox, setClipBox] = useState<{ l: number; t: number; w: number; h: number } | null>(null);

  useEffect(() => {
    if (chartMode !== 'candle') return;
    const el = chartBoxRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.querySelector('clipPath rect');
      if (!rect) return;
      setClipBox({
        l: +rect.getAttribute('x')!,
        t: +rect.getAttribute('y')!,
        w: +rect.getAttribute('width')!,
        h: +rect.getAttribute('height')!,
      });
    };
    measure();
    const id = setTimeout(measure, 50);
    return () => clearTimeout(id);
  }, [chartMode, prediction]);

  const chartData = useMemo(() => {
    const hist = prediction.history.map(h => ({
      date:      h.date,
      price:     h.price,
      bb_upper:  h.bb_upper  ?? undefined,
      bb_middle: h.bb_middle ?? undefined,
      bb_lower:  h.bb_lower  ?? undefined,
      sma50:     h.sma50     ?? undefined,
      sma200:    h.sma200    ?? undefined,
      predicted: undefined as number | undefined,
      foreHigh:  undefined as number | undefined,
      foreLow:   undefined as number | undefined,
    }));
    const fore = (prediction.forecastDays || []).map(f => ({
      date:      f.date,
      price:     undefined as number | undefined,
      bb_upper:  undefined, bb_middle: undefined, bb_lower: undefined,
      sma50:     undefined, sma200:    undefined,
      predicted: f.predicted,
      foreHigh:  f.high,
      foreLow:   f.low,
    }));
    return [...hist, ...fore];
  }, [prediction]);

  const candleChartData = useMemo(() => {
    const hist = prediction.history.map(h => ({
      date:      h.date,
      open:      h.open  ?? h.price,
      high:      h.high  ?? h.price,
      low:       h.low   ?? h.price,
      close:     h.price,
      bb_upper:  h.bb_upper  ?? undefined,
      bb_middle: h.bb_middle ?? undefined,
      bb_lower:  h.bb_lower  ?? undefined,
      sma50:     h.sma50     ?? undefined,
      sma200:    h.sma200    ?? undefined,
      predicted: undefined as number | undefined,
      foreHigh:  undefined as number | undefined,
      foreLow:   undefined as number | undefined,
    }));
    const fore = (prediction.forecastDays || []).map(f => ({
      date: f.date, open: undefined as number | undefined,
      high: undefined as number | undefined, low: undefined as number | undefined,
      close: undefined as number | undefined,
      bb_upper: undefined, bb_middle: undefined, bb_lower: undefined,
      sma50: undefined, sma200: undefined,
      predicted: f.predicted, foreHigh: f.high, foreLow: f.low,
    }));
    return [...hist, ...fore];
  }, [prediction]);

  const macdData = useMemo(() =>
    prediction.history.map(h => ({
      date:   h.date,
      macd:   h.macd        ?? null,
      signal: h.macd_signal ?? null,
      hist:   h.macd_hist   ?? null,
    }))
  , [prediction]);

  const rsiData = useMemo(() => {
    const rsiSeries = prediction.indicators?.rsi_series ?? [];
    return prediction.history.map((h, i) => ({
      date: h.date,
      rsi:  rsiSeries[i] ?? null,
    }));
  }, [prediction]);

  const volumeData = useMemo(() =>
    prediction.history.map(h => ({
      date:   h.date,
      volume: h.volume ?? 0,
    }))
  , [prediction]);

  const chartDomain = useMemo((): [number, number] | ['auto', 'auto'] => {
    const data = chartMode === 'line' ? chartData : candleChartData;
    if (!data.length) return ['auto', 'auto'];
    const allVals = data.flatMap(d => [
      (d as any).price,    (d as any).predicted, (d as any).foreHigh, (d as any).foreLow,
      (d as any).open,     (d as any).high,       (d as any).low,      (d as any).close,
      indicators.includes('bb') ? (d as any).bb_upper : undefined,
      indicators.includes('bb') ? (d as any).bb_lower : undefined,
    ].filter((v): v is number => v !== undefined && v !== null));
    if (!allVals.length) return ['auto', 'auto'];
    const min = Math.min(...allVals);
    const max = Math.max(...allVals);
    const pad = (max - min) * 0.12 || max * 0.02;
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [chartData, candleChartData, chartMode, indicators]);

  const toggleSx = {
    '& .MuiToggleButton-root': {
      fontSize: '0.65rem', fontWeight: 800, letterSpacing: 1,
      py: 0.4, px: 1.5, borderRadius: '6px !important',
      border: '1px solid rgba(128,128,128,0.2) !important',
      '&.Mui-selected': { background: `${primaryColor}1a`, color: primaryColor },
      '&:not(.Mui-selected)': { color: 'rgba(128,128,128,0.5)' },
      '&:hover': { color: primaryColor, background: `${primaryColor}0d` },
    },
  };

  return (
    <Card>
      <CardContent sx={{ p: 4 }}>
        {/* Symbol header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
          <Box>
            <Typography variant="h2">{prediction.symbol}</Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
              <Chip
                label={`${prediction.prediction.trend} Trend`}
                color={prediction.prediction.trend === 'Bullish' ? 'success' : 'error'}
                size="small"
                sx={{ fontWeight: 900, fontSize: '0.7rem' }}
              />
              {prediction.metrics.sector && prediction.metrics.sector !== 'N/A' && (
                <Chip label={prediction.metrics.sector} size="small" variant="outlined" sx={{ fontSize: '0.65rem', opacity: 0.6 }} />
              )}
            </Stack>
          </Box>
          <Box sx={{ textAlign: 'right' }}>
            <Typography variant="h3" color="primary.main">${prediction.currentPrice}</Typography>
            <Typography variant="caption" sx={{ opacity: 0.4 }}>
              {prediction.metrics.currency ?? 'USD'} · LIVE FEED
            </Typography>
          </Box>
        </Box>

        {/* Stats bar */}
        {chartStats && (
          <Stack direction="row" spacing={3} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
            {[
              { label: 'CHANGE',      val: `${chartStats.isUp ? '+' : ''}${chartStats.change.toFixed(2)} (${chartStats.isUp ? '+' : ''}${chartStats.changePct.toFixed(2)}%)`, col: trendColor },
              { label: 'PERIOD HIGH', val: `$${chartStats.high.toFixed(2)}`, col: isDark ? '#00ffa3' : '#16a34a' },
              { label: 'PERIOD LOW',  val: `$${chartStats.low.toFixed(2)}`,  col: isDark ? '#ff0055' : '#dc2626' },
              { label: 'SMA 20',      val: `$${prediction.modelStats?.sma_20 ?? '—'}`, col: '#f59e0b' },
              { label: 'ANN. VOL',    val: `${prediction.modelStats?.ann_volatility_pct ?? '—'}%`, col: 'text.secondary' },
            ].map(s => (
              <Box key={s.label}>
                <Typography variant="caption" sx={{ opacity: 0.4, display: 'block', letterSpacing: 1 }}>{s.label}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 800, color: s.col }}>{s.val}</Typography>
              </Box>
            ))}
          </Stack>
        )}

        {/* Indicator toggles */}
        <ToggleButtonGroup
          value={indicators}
          onChange={(_, v) => setIndicators(v)}
          size="small"
          sx={{ mb: 2, flexWrap: 'wrap', gap: 0.5 }}
        >
          {([
            { key: 'bb',     label: 'Bollinger Bands' },
            { key: 'sma',    label: 'SMA 50/200'      },
            { key: 'macd',   label: 'MACD'            },
            { key: 'rsi',    label: 'RSI'             },
            { key: 'volume', label: 'Volume'          },
          ] as { key: IndicatorKey; label: string }[]).map(({ key, label }) => (
            <ToggleButton key={key} value={key} sx={{ fontSize: '0.65rem', py: 0.5, px: 1.5, borderRadius: '8px !important' }}>
              {label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        {/* Chart mode + engine toggles */}
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap' }}>
          <ToggleButtonGroup exclusive aria-label="chart-mode" value={chartMode}
            onChange={(_e, val) => val && setChartMode(val)} size="small" sx={toggleSx}
          >
            <ToggleButton value="line">LINE</ToggleButton>
            <ToggleButton value="candle">CANDLE</ToggleButton>
          </ToggleButtonGroup>
          <ToggleButtonGroup exclusive aria-label="chart-engine" value={chartEngine}
            onChange={(_e, val) => val && setChartEngine(val)} size="small" sx={toggleSx}
          >
            <ToggleButton value="classic">CLASSIC</ToggleButton>
            <ToggleButton value="pro">PRO (ZOOM)</ToggleButton>
          </ToggleButtonGroup>
        </Box>

        {/* Indicators Guide (collapsible) */}
        <Box sx={{ mb: 1 }}>
          <Button
            size="small" variant="text"
            onClick={() => setLegendOpen(o => !o)}
            startIcon={<Info size={12} />}
            endIcon={legendOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            sx={{
              fontSize: '0.6rem', letterSpacing: 1.5, textTransform: 'uppercase',
              py: 0.3, px: 1, opacity: 0.45, transition: 'opacity 0.2s',
              '&:hover': { opacity: 1 },
            }}
          >
            Indicators Guide
          </Button>
          <Collapse in={legendOpen}>
            <Box sx={{
              mt: 1, p: 2, borderRadius: 2,
              background: isDark ? 'rgba(255,255,255,0.015)' : 'rgba(0,0,0,0.025)',
              border: `1px solid ${primaryColor}1a`,
            }}>
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 1.5 }}>
                {([
                  { key: 'bb', always: false, label: 'Bollinger Bands', color: primaryColor,
                    description: 'Volatility envelope: upper/lower = ±2 std devs from the 20-day MA. Bands widen during high volatility, narrow during consolidation.' },
                  { key: 'sma', always: false, label: 'SMA 50 / SMA 200', color: '#f97316', color2: '#a855f7',
                    description: 'Trend-following averages. SMA50 (orange) tracks medium-term, SMA200 (purple) tracks long-term. Golden cross (50 > 200) = bullish; death cross (50 < 200) = bearish.' },
                  { key: 'macd', always: false, label: 'MACD (12, 26, 9)', color: isDark ? '#00f2ff' : '#0077ff',
                    description: 'Momentum oscillator. Line crossing above signal = bullish; below = bearish. Histogram bars show momentum strength — growing bars = accelerating trend.' },
                  { key: 'rsi', always: false, label: 'RSI (14)', color: '#bc13fe',
                    description: 'Relative Strength Index: 0–100 oscillator. Above 70 = overbought (potential reversal down). Below 30 = oversold (potential reversal up). 50 is the neutral midline.' },
                  { key: 'volume', always: false, label: 'Volume', color: primaryColor,
                    description: 'Number of shares traded. High volume on an up-move = strong buying conviction. High volume on a down-move = heavy selling distribution. Low volume = weak signal.' },
                  { key: 'sma20', always: true, label: 'SMA 20 (ref)', color: '#f59e0b',
                    description: "Short-term 20-day moving average shown as a horizontal reference line at today's value. Price above = near-term uptrend; below = near-term weakness." },
                  { key: 'support', always: true, label: 'Support Levels (S)', color: isDark ? '#00ffa3' : '#16a34a',
                    description: 'Price floors identified from the last 3 months using local price minima. Historically where buyers stepped in — expect potential bounce or consolidation when revisited.' },
                  { key: 'resistance', always: true, label: 'Resistance Levels (R)', color: isDark ? '#ff0055' : '#dc2626',
                    description: 'Price ceilings identified from the last 3 months using local price maxima. Historically where sellers emerged — expect potential rejection or slowdown on approach.' },
                ] as { key: string; always: boolean; label: string; color: string; color2?: string; description: string }[])
                  .filter(item => item.always || indicators.includes(item.key as IndicatorKey))
                  .map(item => {
                    const sig = indicatorSignals[item.key];
                    return (
                      <Box key={item.key} sx={{
                        p: 1.5, borderRadius: 1.5,
                        background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)',
                        border: `1px solid ${item.color}22`,
                        display: 'flex', flexDirection: 'column', gap: 0.5,
                      }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                          <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: item.color, flexShrink: 0 }} />
                          {item.color2 && <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: item.color2, flexShrink: 0 }} />}
                          <Typography sx={{ fontSize: '0.7rem', fontWeight: 800, letterSpacing: 0.5 }}>{item.label}</Typography>
                        </Box>
                        <Typography sx={{ fontSize: '0.6rem', opacity: 0.55, lineHeight: 1.5 }}>
                          {item.description}
                        </Typography>
                        {sig && (
                          <Box sx={{
                            mt: 0.5, px: 1, py: 0.4, borderRadius: 1,
                            background: `${sig.color}14`,
                            border: `1px solid ${sig.color}33`,
                          }}>
                            <Typography sx={{ fontSize: '0.58rem', color: sig.color, fontWeight: 700, lineHeight: 1.4 }}>
                              ▶ {sig.text}
                            </Typography>
                          </Box>
                        )}
                      </Box>
                    );
                  })}
              </Box>
            </Box>
          </Collapse>
        </Box>

        {chartEngine === 'pro' ? (
          <AdvancedChart
            history={prediction.history}
            forecast={prediction.forecastDays}
            rsiSeries={prediction.indicators?.rsi_series ?? []}
            indicators={indicators}
            mode={chartMode}
            isDark={isDark}
            primaryColor={primaryColor}
            trendColor={trendColor}
            support={prediction.indicators?.support ?? []}
            resistance={prediction.indicators?.resistance ?? []}
          />
        ) : (<>
          {/* Main price + overlay chart */}
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Box ref={chartBoxRef} sx={{ height: 380, position: 'relative', flex: 1 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={(chartMode === 'line' ? chartData : candleChartData) as ChartEntry[]} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                  <defs>
                    <linearGradient id="histGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={trendColor} stopOpacity={0.35} />
                      <stop offset="95%" stopColor={trendColor} stopOpacity={0}    />
                    </linearGradient>
                    <linearGradient id="foreGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#bc13fe" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#bc13fe" stopOpacity={0}    />
                    </linearGradient>
                    <linearGradient id="bbGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={primaryColor} stopOpacity={0.08} />
                      <stop offset="95%" stopColor={primaryColor} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>

                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.1)" vertical={false} />
                  <XAxis dataKey="date" stroke="rgba(128,128,128,0.2)" tick={{ fill: 'rgba(128,128,128,0.5)', fontSize: 10 }} tickLine={false} axisLine={false} />
                  <YAxis domain={chartDomain} stroke="rgba(128,128,128,0.2)" tick={{ fill: 'rgba(128,128,128,0.5)', fontSize: 10 }} tickLine={false} axisLine={false} width={65}
                    tickFormatter={(v: number) => v >= 1000 ? `$${(v/1000).toFixed(1)}k` : `$${v.toFixed(0)}`}
                  />
                  <Tooltip
                    contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}4d`, borderRadius: 10, fontSize: 12 }}
                    formatter={(value: any, name: string) => {
                      const v = Number(value);
                      const map: Record<string, string> = {
                        price: 'Close', close: 'Close (OHLC)', predicted: 'Forecast', foreHigh: 'Fore. High', foreLow: 'Fore. Low',
                        bb_upper: 'BB Upper', bb_middle: 'BB Mid', bb_lower: 'BB Lower',
                        sma50: 'SMA 50', sma200: 'SMA 200',
                      };
                      return [`$${v.toFixed(2)}`, map[name] ?? name];
                    }}
                    labelStyle={{ opacity: 0.5, fontSize: 11 }}
                  />
                  <Legend wrapperStyle={{ fontSize: '0.65rem', opacity: 0.6, paddingTop: 8 }}
                    formatter={(value) => {
                      const map: Record<string, string> = {
                        price: 'Close', close: 'Close (OHLC)', predicted: 'Forecast', foreHigh: 'Fore. High', foreLow: 'Fore. Low',
                        bb_upper: 'BB Upper', bb_middle: 'BB Mid', bb_lower: 'BB Lower',
                        sma50: 'SMA 50', sma200: 'SMA 200',
                      };
                      return map[value] ?? value;
                    }}
                  />

                  {prediction.modelStats?.sma_20 > 0 && (
                    <ReferenceLine y={prediction.modelStats.sma_20} stroke="#f59e0b" strokeDasharray="4 4" strokeOpacity={0.5}
                      label={{ value: `SMA20 $${prediction.modelStats.sma_20}`, fill: '#f59e0b', fontSize: 9, position: 'insideTopRight' }}
                    />
                  )}

                  {(prediction.indicators?.support ?? []).map((lvl, i) => (
                    <ReferenceLine key={`sup-${i}`} y={lvl} stroke="#00ffa3" strokeDasharray="6 3" strokeOpacity={0.7} strokeWidth={1.2}
                      label={{ value: `S $${lvl}`, fill: '#00ffa3', fontSize: 9, position: 'insideBottomRight' }}
                    />
                  ))}

                  {(prediction.indicators?.resistance ?? []).map((lvl, i) => (
                    <ReferenceLine key={`res-${i}`} y={lvl} stroke="#ff0055" strokeDasharray="6 3" strokeOpacity={0.7} strokeWidth={1.2}
                      label={{ value: `R $${lvl}`, fill: '#ff0055', fontSize: 9, position: 'insideTopRight' }}
                    />
                  ))}

                  {indicators.includes('bb') && <>
                    <Area type="monotone" dataKey="bb_upper"  stroke={primaryColor} strokeWidth={1} strokeDasharray="3 2" strokeOpacity={0.5} fill="url(#bbGrad)" dot={false} connectNulls isAnimationActive={false} />
                    <Line  type="monotone" dataKey="bb_middle" stroke={primaryColor} strokeWidth={1} strokeDasharray="5 3" strokeOpacity={0.4} dot={false} connectNulls isAnimationActive={false} />
                    <Area type="monotone" dataKey="bb_lower"  stroke={primaryColor} strokeWidth={1} strokeDasharray="3 2" strokeOpacity={0.5} fill="transparent" dot={false} connectNulls isAnimationActive={false} />
                  </>}

                  {indicators.includes('sma') && <>
                    <Line type="monotone" dataKey="sma50"  stroke="#f97316" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="sma200" stroke="#a855f7" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                  </>}

                  {chartMode === 'line' && (
                    <Area type="monotone" dataKey="price" stroke={trendColor} strokeWidth={2.5} fill="url(#histGrad)" dot={false} connectNulls={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
                  )}

                  <Area type="monotone" dataKey="foreHigh" stroke="rgba(188,19,254,0.5)" strokeWidth={1.5} strokeDasharray="5 3" fill="url(#foreGrad)" dot={false} connectNulls={false} isAnimationActive={false} />
                  <Area type="monotone" dataKey="foreLow"  stroke="rgba(188,19,254,0.3)" strokeWidth={1}   strokeDasharray="5 3" fill="transparent"    dot={false} connectNulls={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="predicted" stroke="#bc13fe" strokeWidth={2} strokeDasharray="6 3"
                    dot={{ r: 4, fill: '#bc13fe', strokeWidth: 0 }} connectNulls={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>

              {/* Candlestick SVG overlay */}
              {chartMode === 'candle' && chartDomain[0] !== 'auto' && (() => {
                const plotL = clipBox?.l ?? 0;
                const plotT = clipBox?.t ?? 0;
                const plotW = clipBox?.w ?? 0;
                const plotH = clipBox?.h ?? 0;
                if (!plotW || !plotH) return null;
                const [dMin, dMax] = chartDomain as [number, number];
                const pRange  = dMax - dMin;
                const total   = candleChartData.length;
                const slotW   = plotW / total;
                const toY = (p: number) => plotT + (1 - (p - dMin) / pRange) * plotH;
                const toX = (i: number) => plotL + (i + 0.5) * slotW;
                return (
                  <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: CHART_HEIGHT, pointerEvents: 'none' }}>
                    {candleChartData.map((d: any, i: number) => {
                      if (d.close == null || d.open == null) return null;
                      const isUp  = d.close >= d.open;
                      const color = isUp ? '#00ffa3' : '#ff0055';
                      const cx    = toX(i);
                      const hw    = Math.max(slotW * 0.38, 1);
                      const yO    = toY(d.open);
                      const yC    = toY(d.close);
                      return (
                        <g key={i}>
                          <line x1={cx} y1={toY(d.high)} x2={cx} y2={toY(d.low)} stroke={color} strokeWidth={1} opacity={0.75} />
                          <rect x={cx - hw} y={Math.min(yO, yC)} width={hw * 2} height={Math.max(Math.abs(yC - yO), 1)}
                            fill={isUp ? 'transparent' : color} stroke={color} strokeWidth={1.2} />
                        </g>
                      );
                    })}
                  </svg>
                );
              })()}
            </Box>
            <VolumeProfile history={prediction.history.map(h => ({ price: h.price, high: h.high, low: h.low, volume: h.volume }))} isDark={isDark} height={380} />
          </Box>

          {/* MACD sub-chart */}
          {indicators.includes('macd') && macdData.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" sx={{ opacity: 0.4, letterSpacing: 2, display: 'block', mb: 1 }}>MACD (12, 26, 9)</Typography>
              <Box sx={{ height: 120 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={macdData} margin={{ top: 0, right: 10, bottom: 0, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.08)" vertical={false} />
                    <XAxis dataKey="date" hide />
                    <YAxis width={45} tick={{ fill: 'rgba(128,128,128,0.4)', fontSize: 9 }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}33`, borderRadius: 8, fontSize: 11 }}
                      formatter={(v: any, name: string) => [Number(v).toFixed(3), name === 'hist' ? 'Histogram' : name === 'macd' ? 'MACD' : 'Signal']} />
                    <Bar dataKey="hist" isAnimationActive={false}>
                      {macdData.map((entry, i) => (
                        <Cell key={i} fill={(entry.hist ?? 0) >= 0 ? (isDark ? '#00ffa3' : '#16a34a') : (isDark ? '#ff0055' : '#dc2626')} fillOpacity={0.7} />
                      ))}
                    </Bar>
                    <Line type="monotone" dataKey="macd"   stroke={primaryColor} strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="signal" stroke="#f59e0b"      strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </Box>
            </Box>
          )}

          {/* RSI sub-chart */}
          {indicators.includes('rsi') && rsiData.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" sx={{ opacity: 0.4, letterSpacing: 2, display: 'block', mb: 1 }}>RSI (14)</Typography>
              <Box sx={{ height: 100 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={rsiData} margin={{ top: 0, right: 10, bottom: 0, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.08)" vertical={false} />
                    <XAxis dataKey="date" hide />
                    <YAxis domain={[0, 100]} width={30} tick={{ fill: 'rgba(128,128,128,0.4)', fontSize: 9 }} tickLine={false} axisLine={false} ticks={[30, 50, 70]} />
                    <Tooltip contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}33`, borderRadius: 8, fontSize: 11 }}
                      formatter={(v: any) => [Number(v).toFixed(1), 'RSI']} />
                    <ReferenceLine y={70} stroke={isDark ? '#ff0055' : '#dc2626'} strokeDasharray="4 3" strokeOpacity={0.5} />
                    <ReferenceLine y={30} stroke={isDark ? '#00ffa3' : '#16a34a'} strokeDasharray="4 3" strokeOpacity={0.5} />
                    <ReferenceLine y={50} stroke="rgba(128,128,128,0.2)" />
                    <Area type="monotone" dataKey="rsi" stroke="#bc13fe" strokeWidth={2} fill="#bc13fe" fillOpacity={0.1} dot={false} connectNulls isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </Box>
            </Box>
          )}

          {/* Volume sub-chart */}
          {indicators.includes('volume') && volumeData.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" sx={{ opacity: 0.4, letterSpacing: 2, display: 'block', mb: 1 }}>VOLUME</Typography>
              <Box sx={{ height: 80 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={volumeData} margin={{ top: 0, right: 10, bottom: 0, left: 10 }}>
                    <XAxis dataKey="date" hide />
                    <YAxis width={45} tick={{ fill: 'rgba(128,128,128,0.4)', fontSize: 9 }} tickLine={false} axisLine={false}
                      tickFormatter={(v: number) => v >= 1e9 ? `${(v/1e9).toFixed(1)}B` : v >= 1e6 ? `${(v/1e6).toFixed(0)}M` : `${v}`}
                    />
                    <Tooltip contentStyle={{ background: isDark ? '#0d1520' : '#fff', border: `1px solid ${primaryColor}33`, borderRadius: 8, fontSize: 11 }}
                      formatter={(v: any) => [Number(v).toLocaleString(), 'Volume']} />
                    <Bar dataKey="volume" fill={primaryColor} fillOpacity={0.4} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </Box>
          )}
        </>)}
      </CardContent>
    </Card>
  );
}
