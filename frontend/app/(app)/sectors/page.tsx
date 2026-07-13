'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Container, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import SectorHeatmapPanel from '../../../components/SectorHeatmapPanel';
import MarketTreemap from '../../../components/MarketTreemap';

const VIEW_KEY = 'fiforesight:sectors:view';
type SectorsView = 'sectors' | 'map';

function loadView(): SectorsView {
  if (typeof window === 'undefined') return 'sectors';
  try {
    return window.localStorage.getItem(VIEW_KEY) === 'map' ? 'map' : 'sectors';
  } catch {
    return 'sectors';
  }
}

export default function SectorsPage() {
  const router = useRouter();
  const [view, setView] = useState<SectorsView>(loadView);

  // Clicking a sector ETF or a treemap stock loads it in the main predict flow.
  // The analysis page auto-triggers a forecast when the ?symbol= query changes.
  const handleSelectTicker = (ticker: string) => {
    router.push(`/analysis?symbol=${encodeURIComponent(ticker)}`);
  };

  const handleViewChange = (_: unknown, v: SectorsView | null) => {
    if (!v) return;
    setView(v);
    try { window.localStorage.setItem(VIEW_KEY, v); } catch { /* private mode */ }
  };

  return (
    <Container maxWidth="lg" disableGutters>
      <Stack
        direction="row"
        alignItems="flex-start"
        justifyContent="space-between"
        flexWrap="wrap"
        gap={1}
        sx={{ mb: 0.5 }}
      >
        <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
          {view === 'map' ? 'Market Map' : 'Sector Heatmap'}
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={view}
          onChange={handleViewChange}
          aria-label="Sector view"
        >
          <ToggleButton value="sectors" aria-label="Sector ETF heatmap">Sectors</ToggleButton>
          <ToggleButton value="map" aria-label="Stock-level market map">Map</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        {view === 'map'
          ? 'Every stock in the curated universe — tile size is market cap, colour is today’s move. Click a tile to run a full forecast.'
          : '1D / 5D performance across all 11 GICS sector ETFs. Click a sector to run a full forecast on its ETF.'}
      </Typography>
      {view === 'map' ? (
        <MarketTreemap onSelectTicker={handleSelectTicker} />
      ) : (
        <SectorHeatmapPanel onSelectTicker={handleSelectTicker} />
      )}
    </Container>
  );
}
