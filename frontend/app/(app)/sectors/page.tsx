'use client';

import { useRouter } from 'next/navigation';
import { Container, Typography } from '@mui/material';
import SectorHeatmapPanel from '../../../components/SectorHeatmapPanel';

export default function SectorsPage() {
  const router = useRouter();

  // Clicking a sector loads its ETF in the main predict flow. The analysis page
  // auto-triggers a forecast when the ?symbol= query changes.
  const handleSelectTicker = (etf: string) => {
    router.push(`/analysis?symbol=${encodeURIComponent(etf)}`);
  };

  return (
    <Container maxWidth="lg" disableGutters>
      <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em', mb: 0.5 }}>
        Sector Heatmap
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        1D / 5D performance across all 11 GICS sector ETFs. Click a sector to run a full forecast on its ETF.
      </Typography>
      <SectorHeatmapPanel onSelectTicker={handleSelectTicker} />
    </Container>
  );
}
