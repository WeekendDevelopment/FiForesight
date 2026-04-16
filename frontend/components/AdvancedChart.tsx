'use client';

/**
 * AdvancedChart — TradingView Lightweight Charts wrapper.
 * Stacked interactive panes (price+overlays, volume, RSI, MACD) with
 * synced time axis. Free, MIT-licensed (lightweight-charts).
 */

import { useEffect, useRef } from 'react';
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  AreaSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';

export type IndicatorKey = 'bb' | 'sma' | 'macd' | 'rsi' | 'volume';

export interface AdvHistoryPoint {
  date: string;
  price: number;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
  bb_upper?: number | null;
  bb_middle?: number | null;
  bb_lower?: number | null;
  sma50?: number | null;
  sma200?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
}

export interface AdvForecastPoint {
  date: string;
  predicted: number;
  high: number;
  low: number;
}

interface Props {
  history: AdvHistoryPoint[];
  forecast?: AdvForecastPoint[];
  rsiSeries?: number[];
  indicators: IndicatorKey[];
  mode: 'line' | 'candle';
  isDark: boolean;
  primaryColor: string;
  trendColor: string;
  support?: number[];
  resistance?: number[];
}

/**
 * Convert an array of MM/DD date strings (from the backend payload) into
 * UTC timestamps. The backend strips the year, so we reconstruct it by
 * walking the array in reverse from today: whenever the month jumps forward
 * (e.g., "01/05" after "12/28") we subtract one year, giving each entry a
 * deterministic calendar date without relying on Date.now() drift.
 */
function buildTimestamps(
  allDates: string[],
  histLen: number
): { histTimes: UTCTimestamp[]; foreTimes: UTCTimestamp[] } {
  const now = new Date();
  let year = now.getUTCFullYear();
  const times: UTCTimestamp[] = new Array(allDates.length);

  // Walk backward so we can detect year rollovers (month jumps forward).
  let prevMonth = -1;
  for (let i = allDates.length - 1; i >= 0; i--) {
    const [mm, dd] = allDates[i].split('/').map(Number);
    if (prevMonth !== -1 && mm > prevMonth) {
      // Month jumped forward going backward → crossed a year boundary
      year -= 1;
    }
    prevMonth = mm;
    const ms = Date.UTC(year, mm - 1, dd);
    times[i] = Math.floor(ms / 1000) as UTCTimestamp;
  }

  return {
    histTimes: times.slice(0, histLen),
    foreTimes: times.slice(histLen),
  };
}

export default function AdvancedChart({
  history,
  forecast = [],
  rsiSeries = [],
  indicators,
  mode,
  isDark,
  primaryColor,
  trendColor,
  support = [],
  resistance = [],
}: Props) {
  const priceRef   = useRef<HTMLDivElement>(null);
  const volumeRef  = useRef<HTMLDivElement>(null);
  const rsiRef     = useRef<HTMLDivElement>(null);
  const macdRef    = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!priceRef.current || history.length === 0) return;

    const allDates = [
      ...history.map(h => h.date),
      ...forecast.map(f => f.date),
    ];
    const { histTimes, foreTimes } = buildTimestamps(allDates, history.length);

    const bg          = isDark ? '#0d1520' : '#ffffff';
    const textColor   = isDark ? 'rgba(220,220,220,0.75)' : 'rgba(20,30,50,0.75)';
    const gridColor   = isDark ? 'rgba(128,128,128,0.08)' : 'rgba(128,128,128,0.12)';
    const upColor     = isDark ? '#00ffa3' : '#16a34a';
    const downColor   = isDark ? '#ff0055' : '#dc2626';

    const baseOptions = {
      layout: { background: { type: ColorType.Solid, color: bg }, textColor, fontSize: 11, attributionLogo: false },
      grid:   { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: gridColor },
      timeScale: { borderColor: gridColor, timeVisible: false, secondsVisible: false },
      autoSize: true,
    };

    const priceChart = createChart(priceRef.current, baseOptions);
    const charts: IChartApi[] = [priceChart];

    // Helper — map over history with index, filter nulls, build {time,value}.
    const histPoints = (pick: (h: AdvHistoryPoint) => number | null | undefined) =>
      history
        .map((h, i) => ({ time: histTimes[i], value: pick(h) }))
        .filter((p): p is { time: UTCTimestamp; value: number } =>
          p.value != null && Number.isFinite(p.value as number)
        );

    // ── Main price series ─────────────────────────────────────────
    if (mode === 'candle') {
      const candles = priceChart.addSeries(CandlestickSeries, {
        upColor, downColor, wickUpColor: upColor, wickDownColor: downColor,
        borderVisible: false,
      });
      candles.setData(
        history
          .map((h, i) => ({
            time: histTimes[i],
            open: (h.open ?? h.price) as number,
            high: (h.high ?? h.price) as number,
            low:  (h.low  ?? h.price) as number,
            close: h.price,
          }))
          .filter(c => Number.isFinite(c.open) && Number.isFinite(c.close))
      );
    } else {
      const area = priceChart.addSeries(AreaSeries, {
        lineColor: trendColor,
        topColor: trendColor + '55',
        bottomColor: trendColor + '05',
        lineWidth: 2,
      });
      area.setData(histPoints(h => h.price));
    }

    // Bollinger Bands
    if (indicators.includes('bb')) {
      const bbU = priceChart.addSeries(LineSeries, { color: primaryColor, lineWidth: 1, lineStyle: 2 });
      const bbM = priceChart.addSeries(LineSeries, { color: primaryColor, lineWidth: 1, lineStyle: 1 });
      const bbL = priceChart.addSeries(LineSeries, { color: primaryColor, lineWidth: 1, lineStyle: 2 });
      bbU.setData(histPoints(h => h.bb_upper));
      bbM.setData(histPoints(h => h.bb_middle));
      bbL.setData(histPoints(h => h.bb_lower));
    }

    // SMA 50 / 200
    if (indicators.includes('sma')) {
      const sma50  = priceChart.addSeries(LineSeries, { color: '#f97316', lineWidth: 2 });
      const sma200 = priceChart.addSeries(LineSeries, { color: '#a855f7', lineWidth: 2 });
      sma50 .setData(histPoints(h => h.sma50));
      sma200.setData(histPoints(h => h.sma200));
    }

    // Forecast line + band
    if (forecast.length) {
      const foreLine = priceChart.addSeries(LineSeries, { color: '#bc13fe', lineWidth: 2, lineStyle: 2 });
      foreLine.setData(forecast.map((f, i) => ({ time: foreTimes[i], value: f.predicted })));

      const hi = priceChart.addSeries(LineSeries, { color: 'rgba(188,19,254,0.6)', lineWidth: 1, lineStyle: 2 });
      const lo = priceChart.addSeries(LineSeries, { color: 'rgba(188,19,254,0.4)', lineWidth: 1, lineStyle: 2 });
      hi.setData(forecast.map((f, i) => ({ time: foreTimes[i], value: f.high })));
      lo.setData(forecast.map((f, i) => ({ time: foreTimes[i], value: f.low  })));
    }

    // Support / resistance as price lines
    {
      const anchor = priceChart.addSeries(LineSeries, { color: 'transparent', lastValueVisible: false, priceLineVisible: false });
      anchor.setData(histPoints(h => h.price));
      support.forEach(lvl => anchor.createPriceLine({
        price: lvl, color: upColor, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `S ${lvl}`,
      }));
      resistance.forEach(lvl => anchor.createPriceLine({
        price: lvl, color: downColor, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `R ${lvl}`,
      }));
    }

    // ── Volume pane ───────────────────────────────────────────────
    if (indicators.includes('volume') && volumeRef.current) {
      const volumeChart = createChart(volumeRef.current, baseOptions);
      charts.push(volumeChart);
      const volSeries = volumeChart.addSeries(HistogramSeries, { color: primaryColor, priceFormat: { type: 'volume' } });
      volSeries.setData(
        history
          .map((h, i) => {
            if (h.volume == null) return null;
            const up = (h.open ?? h.price) <= h.price;
            return {
              time: histTimes[i],
              value: h.volume as number,
              color: up ? upColor + '99' : downColor + '99',
            };
          })
          .filter((x): x is NonNullable<typeof x> => x !== null)
      );
    }

    // ── RSI pane ──────────────────────────────────────────────────
    if (indicators.includes('rsi') && rsiRef.current && rsiSeries.length) {
      const rsiChart = createChart(rsiRef.current, baseOptions);
      charts.push(rsiChart);
      const r = rsiChart.addSeries(LineSeries, { color: '#bc13fe', lineWidth: 2 });
      r.setData(
        history
          .map((h, i) => ({ time: histTimes[i], value: rsiSeries[i] }))
          .filter(p => p.value != null && Number.isFinite(p.value))
      );
      r.createPriceLine({ price: 70, color: downColor, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '70' });
      r.createPriceLine({ price: 30, color: upColor,   lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '30' });
      r.createPriceLine({ price: 50, color: textColor, lineWidth: 1, lineStyle: 1, axisLabelVisible: false, title: '' });
    }

    // ── MACD pane ─────────────────────────────────────────────────
    if (indicators.includes('macd') && macdRef.current) {
      const macdChart = createChart(macdRef.current, baseOptions);
      charts.push(macdChart);
      const hist = macdChart.addSeries(HistogramSeries, { priceFormat: { type: 'price', precision: 3, minMove: 0.001 } });
      hist.setData(
        history
          .map((h, i) => {
            if (h.macd_hist == null) return null;
            return {
              time: histTimes[i],
              value: h.macd_hist as number,
              color: (h.macd_hist as number) >= 0 ? upColor + '99' : downColor + '99',
            };
          })
          .filter((x): x is NonNullable<typeof x> => x !== null)
      );
      const line = macdChart.addSeries(LineSeries, { color: primaryColor, lineWidth: 2 });
      const sig  = macdChart.addSeries(LineSeries, { color: '#f97316',   lineWidth: 2 });
      line.setData(histPoints(h => h.macd));
      sig .setData(histPoints(h => h.macd_signal));
    }

    // ── Sync time scales across all panes ─────────────────────────
    const syncing = { current: false };
    const handlers: Array<() => void> = [];
    charts.forEach(source => {
      const fn = (range: { from: Time; to: Time } | null) => {
        if (syncing.current || !range) return;
        syncing.current = true;
        charts.forEach(target => {
          if (target !== source) target.timeScale().setVisibleRange(range);
        });
        syncing.current = false;
      };
      source.timeScale().subscribeVisibleTimeRangeChange(fn);
      handlers.push(() => source.timeScale().unsubscribeVisibleTimeRangeChange(fn));
    });

    priceChart.timeScale().fitContent();

    return () => {
      handlers.forEach(h => h());
      charts.forEach(c => c.remove());
    };
  }, [history, forecast, rsiSeries, indicators, mode, isDark, primaryColor, trendColor, support, resistance]);

  const paneBorder = isDark ? '1px solid rgba(255,255,255,0.05)' : '1px solid rgba(0,0,0,0.08)';
  const labelStyle: React.CSSProperties = {
    position: 'absolute', top: 6, left: 10, zIndex: 2,
    fontSize: 10, fontWeight: 800, letterSpacing: 1.5,
    color: isDark ? 'rgba(220,220,220,0.55)' : 'rgba(20,30,50,0.55)',
    pointerEvents: 'none', textTransform: 'uppercase',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
      <div style={{ position: 'relative', height: 380, border: paneBorder, borderRadius: 8, overflow: 'hidden' }}>
        <span style={labelStyle}>Price</span>
        <div ref={priceRef} style={{ position: 'absolute', inset: 0 }} />
      </div>

      {indicators.includes('volume') && (
        <div style={{ position: 'relative', height: 110, border: paneBorder, borderRadius: 8, overflow: 'hidden' }}>
          <span style={labelStyle}>Volume</span>
          <div ref={volumeRef} style={{ position: 'absolute', inset: 0 }} />
        </div>
      )}

      {indicators.includes('rsi') && (
        <div style={{ position: 'relative', height: 130, border: paneBorder, borderRadius: 8, overflow: 'hidden' }}>
          <span style={labelStyle}>RSI (14)</span>
          <div ref={rsiRef} style={{ position: 'absolute', inset: 0 }} />
        </div>
      )}

      {indicators.includes('macd') && (
        <div style={{ position: 'relative', height: 150, border: paneBorder, borderRadius: 8, overflow: 'hidden' }}>
          <span style={labelStyle}>MACD (12, 26, 9)</span>
          <div ref={macdRef} style={{ position: 'absolute', inset: 0 }} />
        </div>
      )}
    </div>
  );
}
