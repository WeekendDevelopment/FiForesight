'use client';

import { useMemo } from 'react';
import type { PredictionData, ChartStats, IndicatorSignals } from '../types';

export function useIndicatorSignals(
  prediction: PredictionData | null,
  isDark: boolean,
  chartStats: ChartStats | null,
): IndicatorSignals {
  return useMemo(() => {
    if (!prediction) return {} as IndicatorSignals;
    const last    = prediction.history[prediction.history.length - 1];
    const price   = last?.price ?? 0;
    const rsiVal  = parseFloat(prediction.rsi);
    const supports    = prediction.indicators?.support    ?? [];
    const resistances = prediction.indicators?.resistance ?? [];
    const sma20       = prediction.modelStats?.sma_20;
    const vsPct       = prediction.modelStats?.price_vs_sma20_pct;

    const green = isDark ? '#00ffa3' : '#16a34a';
    const red   = isDark ? '#ff0055' : '#dc2626';
    const amber = '#f59e0b';
    const blue  = isDark ? '#00f2ff' : '#0077ff';

    const bbUpper  = last?.bb_upper  ?? null;
    const bbLower  = last?.bb_lower  ?? null;
    const bbMiddle = last?.bb_middle ?? null;

    const sma50  = last?.sma50  ?? null;
    const sma200 = last?.sma200 ?? null;

    const h = prediction.history;
    const macdPrev  = h.length >= 2 ? (h[h.length - 2]?.macd        ?? null) : null;
    const sigPrev   = h.length >= 2 ? (h[h.length - 2]?.macd_signal ?? null) : null;
    const histPrev  = h.length >= 2 ? (h[h.length - 2]?.macd_hist   ?? null) : null;
    const macdNow   = last?.macd        ?? null;
    const sigNow    = last?.macd_signal ?? null;
    const histNow   = last?.macd_hist   ?? null;

    const vols   = prediction.history.slice(-21, -1)
      .filter(p => p.volume != null && Number.isFinite(p.volume))
      .map(p => p.volume as number);
    const avgVol = vols.length ? vols.reduce((a, b) => a + b, 0) / vols.length : 0;
    const lastVol = last?.volume ?? 0;

    return {
      bb: (() => {
        if (!bbUpper || !bbLower) return null;
        if (price >= bbUpper * 0.99) return { text: 'Price touching upper band → overbought risk', color: red };
        if (price <= bbLower * 1.01) return { text: 'Price touching lower band → oversold opportunity', color: green };
        if (bbMiddle && price > bbMiddle) return { text: 'Price above midline → mild bullish bias', color: green };
        return { text: 'Price below midline → mild bearish bias', color: amber };
      })(),
      sma: (() => {
        if (!sma50 || !sma200) return null;
        const cross        = sma50 > sma200;
        const priceAbove50  = price > sma50;
        const priceAbove200 = price > sma200;
        if (cross && priceAbove50)   return { text: `Golden cross active (SMA50 > SMA200). Price above both → strong uptrend`, color: green };
        if (!cross && !priceAbove200) return { text: `Death cross active (SMA50 < SMA200). Price below both → strong downtrend`, color: red };
        if (priceAbove50 && !cross)  return { text: `Price above SMA50 but SMA50 < SMA200 → short-term recovery in downtrend`, color: amber };
        return { text: `Price below SMA50 but above SMA200 → near-term weakness in uptrend`, color: amber };
      })(),
      macd: (() => {
        if (macdNow == null || sigNow == null) return null;
        const justCrossedUp   = macdPrev != null && sigPrev != null && macdPrev < sigPrev && macdNow >= sigNow;
        const justCrossedDown = macdPrev != null && sigPrev != null && macdPrev > sigPrev && macdNow <= sigNow;
        if (justCrossedUp)   return { text: 'Bullish crossover — MACD just crossed above signal line', color: green };
        if (justCrossedDown) return { text: 'Bearish crossover — MACD just crossed below signal line', color: red };
        if (macdNow > sigNow) {
          const growing = histNow != null && histPrev != null && histNow > histPrev;
          return growing
            ? { text: 'MACD above signal & histogram growing → bullish momentum', color: green }
            : { text: 'MACD above signal → bullish bias', color: green };
        }
        if (macdNow < sigNow) {
          const shrinking = histNow != null && histPrev != null && histNow < histPrev;
          return shrinking
            ? { text: 'MACD below signal & histogram shrinking → bearish momentum', color: red }
            : { text: 'MACD below signal → bearish bias', color: red };
        }
        return { text: 'Consolidating — no strong directional signal', color: amber };
      })(),
      rsi: (() => {
        if (isNaN(rsiVal)) return null;
        if (rsiVal >= 80) return { text: `RSI ${rsiVal.toFixed(1)} — severely overbought, reversal likely`, color: red };
        if (rsiVal >= 70) return { text: `RSI ${rsiVal.toFixed(1)} — overbought zone, caution on longs`, color: red };
        if (rsiVal <= 20) return { text: `RSI ${rsiVal.toFixed(1)} — severely oversold, potential bounce`, color: green };
        if (rsiVal <= 30) return { text: `RSI ${rsiVal.toFixed(1)} — oversold zone, watch for reversal up`, color: green };
        if (rsiVal >= 50) return { text: `RSI ${rsiVal.toFixed(1)} — above midline, bullish bias`, color: green };
        return { text: `RSI ${rsiVal.toFixed(1)} — below midline, bearish bias`, color: amber };
      })(),
      volume: (() => {
        if (!avgVol || !lastVol) return null;
        const ratio      = lastVol / avgVol;
        const priceTrend = chartStats?.isUp;
        if (ratio >= 1.5 && priceTrend === true)  return { text: `Vol ${ratio.toFixed(1)}× above avg on up-day → strong bullish conviction`, color: green };
        if (ratio >= 1.5 && priceTrend === false) return { text: `Vol ${ratio.toFixed(1)}× above avg on down-day → strong bearish distribution`, color: red };
        if (ratio < 0.6) return { text: `Vol ${ratio.toFixed(1)}× below avg → low conviction move, may reverse`, color: amber };
        return { text: `Volume near average — normal trading conditions`, color: blue };
      })(),
      sma20: (() => {
        if (!sma20 || vsPct == null) return null;
        if (vsPct > 5)  return { text: `Price ${vsPct.toFixed(1)}% above SMA20 → extended, watch for pullback`, color: amber };
        if (vsPct > 0)  return { text: `Price ${vsPct.toFixed(1)}% above SMA20 → near-term uptrend`, color: green };
        if (vsPct < -5) return { text: `Price ${Math.abs(vsPct).toFixed(1)}% below SMA20 → extended weakness`, color: red };
        return { text: `Price ${Math.abs(vsPct).toFixed(1)}% below SMA20 → near-term downtrend`, color: red };
      })(),
      support: (() => {
        if (!supports.length) return null;
        const nearest = supports.reduce((a, b) => Math.abs(a - price) < Math.abs(b - price) ? a : b);
        if (!nearest || !price) return null;
        const distPct = ((price - nearest) / nearest * 100).toFixed(1);
        return { text: `Nearest support $${nearest} — price is ${distPct}% above. Bounce zone if tested.`, color: green };
      })(),
      resistance: (() => {
        if (!resistances.length) return null;
        const nearest = resistances.reduce((a, b) => Math.abs(a - price) < Math.abs(b - price) ? a : b);
        if (!nearest || !price) return null;
        const distPct = ((nearest - price) / price * 100).toFixed(1);
        return { text: `Nearest resistance $${nearest} — ${distPct}% above current price. Sell pressure zone.`, color: red };
      })(),
    };
  }, [prediction, isDark, chartStats]);
}
