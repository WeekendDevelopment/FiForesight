"use client";

import React, { useState } from 'react';
import dynamic from 'next/dynamic';
import { Box, Button, CircularProgress, IconButton, Modal, Paper, Typography } from '@mui/material';
import { X } from 'lucide-react';
import type { PlotParams } from 'react-plotly.js';
import { currencyAffixes } from '../lib/currency';

// react-plotly.js exception: Recharts has no 3D surface capability, so this
// component uses Plotly via dynamic import. See CLAUDE.md "Key Decisions" for details.
// Load Plotly only on the client — it doesn't support SSR
const Plot = dynamic<PlotParams>(
  () => import('react-plotly.js').then(m => m.default as React.ComponentType<PlotParams>),
  {
    ssr: false,
    loading: () => (
      <Box sx={{ height: 460, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <CircularProgress size={36} sx={{ color: '#7c4dff' }} />
      </Box>
    ),
  },
);

// ── Types ──────────────────────────────────────────────────────────────────────

export interface PriceRangeDay {
  day: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

interface Props {
  priceRangeByDay: PriceRangeDay[];
  currentPrice: number;
  symbol: string;
  currency?: string | null;  // native quote currency (F35) — axis affix only
}

// ── Gaussian PDF helper ────────────────────────────────────────────────────────

function gaussianPdf(x: number, mean: number, std: number): number {
  if (std <= 0) return 0;
  const z = (x - mean) / std;
  return (1 / (std * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * z * z);
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function MonteCarloProbabilitySurface({
  priceRangeByDay,
  currentPrice,
  symbol,
  currency = 'USD',
}: Props) {
  const [open, setOpen] = useState(false);
  const { prefix: tickPrefix, suffix: tickSuffix } = currencyAffixes(currency);

  // Build 3D surface: X = days, Y = price bins, Z = probability density
  const N_BINS = 40;

  const allP10 = priceRangeByDay.map(d => d.p10);
  const allP90 = priceRangeByDay.map(d => d.p90);
  const yMin   = Math.min(...allP10, currentPrice) * 0.97;
  const yMax   = Math.max(...allP90, currentPrice) * 1.03;
  const yBins  = Array.from({ length: N_BINS }, (_, i) =>
    parseFloat((yMin + (yMax - yMin) * (i / (N_BINS - 1))).toFixed(2)),
  );
  const xDays = priceRangeByDay.map(d => d.day);

  // For each day, approximate the distribution as Gaussian using the 80% interval
  // (p10→p90 spans ≈ 2×1.28σ for a normal distribution).
  // Plotly surface with 1D x/y arrays requires z[row=y][col=x], i.e. [priceBin][day].
  const zData = yBins.map((y) =>
    priceRangeByDay.map((d) => {
      const std = Math.max((d.p90 - d.p10) / 2.56, 1e-9);
      return gaussianPdf(y, d.p50, std);
    }),
  );

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const plotData: any[] = [
    {
      type:       'surface',
      x:          xDays,
      y:          yBins,
      z:          zData,
      colorscale: 'Viridis',
      showscale:  true,
      opacity:    0.92,
      contours: {
        z: {
          show:         true,
          usecolormap:  true,
          highlightcolor: '#00f2ff',
          project:      { z: true },
        },
      },
      colorbar: {
        title:      { text: 'Likelihood', font: { color: '#94a3b8', size: 11 } },
        tickfont:   { color: '#64748b', size: 10 },
        len:        0.6,
      },
    },
  ];

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const layout: Record<string, any> = {
    paper_bgcolor: '#0a0a0a',
    plot_bgcolor:  '#0a0a0a',
    margin:        { l: 0, r: 0, b: 0, t: 10 },
    font:          { color: '#94a3b8', family: 'Inter, Roboto, sans-serif' },
    scene: {
      bgcolor: '#111827',
      xaxis: {
        title:     { text: 'Day', font: { color: '#64748b', size: 11 } },
        tickfont:  { color: '#64748b', size: 10 },
        gridcolor: '#1e293b',
        showbackground: true,
        backgroundcolor: '#0d1117',
      },
      yaxis: {
        title:     { text: `Price (${currency ?? 'USD'})`, font: { color: '#64748b', size: 11 } },
        tickfont:  { color: '#64748b', size: 10 },
        gridcolor: '#1e293b',
        tickprefix: tickPrefix,
        ticksuffix: tickSuffix,
        showbackground: true,
        backgroundcolor: '#0d1117',
      },
      zaxis: {
        title:     { text: 'Likelihood (higher = more probable)', font: { color: '#64748b', size: 11 } },
        tickfont:  { color: '#64748b', size: 10 },
        gridcolor: '#1e293b',
        showbackground: true,
        backgroundcolor: '#0d1117',
      },
      camera: { eye: { x: 1.6, y: -1.6, z: 0.9 } },
    },
  };

  return (
    <>
      <Button
        size="small"
        variant="outlined"
        onClick={() => setOpen(true)}
        sx={{
          fontSize: 11, py: 0.25, px: 1.5,
          borderColor: 'rgba(124,77,255,0.4)',
          color: 'rgba(124,77,255,0.8)',
          '&:hover': {
            borderColor: 'rgba(124,77,255,0.7)',
            background:  'rgba(124,77,255,0.08)',
          },
        }}
      >
        3D Surface
      </Button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2 }}
      >
        <Paper sx={{
          p: 2,
          width:     { xs: '95vw', md: 720 },
          maxHeight: '92vh',
          overflow:  'hidden',
          background: '#0a0a0a',
          border:     '1px solid rgba(124,77,255,0.3)',
          position:   'relative',
          outline:    'none',
        }}>
          <IconButton
            aria-label="Close Monte Carlo probability surface"
            onClick={() => setOpen(false)}
            size="small"
            sx={{ position: 'absolute', top: 8, right: 8, color: 'text.secondary' }}
          >
            <X size={16} />
          </IconButton>

          <Typography
            variant="subtitle2"
            fontWeight={700}
            sx={{ mb: 0.5, color: '#7c4dff' }}
          >
            Monte Carlo Probability Surface — {symbol}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
            Think of each &quot;mountain&quot; as a bell curve on its side — the taller the peak, the
            more likely the price lands there on that day. The surface fans wider over time because
            the further out you look, the less certain the prediction becomes.
          </Typography>
          <Typography variant="caption" sx={{ fontSize: 10, opacity: 0.45, display: 'block', mb: 1.5 }}>
            Drag to rotate · Scroll to zoom · Based on 1,000 simulated price paths
          </Typography>

          <Plot
            data={plotData}
            layout={layout}
            config={{ responsive: true, displaylogo: false, scrollZoom: true }}
            style={{ width: '100%', height: 420 }}
          />

          {/* How to read guide */}
          <Box sx={{ mt: 1.5, display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
            {[
              { dot: '#fde047', label: 'Yellow peak', desc: 'The price the stock is most likely to hit — like the bullseye on a dartboard' },
              { dot: '#4ade80', label: 'Green slopes', desc: 'Prices that are fairly likely — not the best guess, but still reasonable' },
              { dot: '#6366f1', label: 'Blue/purple edges', desc: 'Unlikely but possible prices — rare scenarios, not impossible' },
              { dot: '#f59e0b', label: 'Wider = less certain', desc: 'The further into the future, the harder it is to predict — so the range gets wider' },
            ].map(({ dot, label, desc }) => (
              <Box key={label} sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75, flex: '1 1 45%' }}>
                <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: dot, mt: 0.3, flexShrink: 0 }} />
                <Box>
                  <Typography sx={{ fontSize: 10, fontWeight: 700, color: dot }}>{label}</Typography>
                  <Typography sx={{ fontSize: 10, opacity: 0.55 }}>{desc}</Typography>
                </Box>
              </Box>
            ))}
          </Box>
        </Paper>
      </Modal>
    </>
  );
}
