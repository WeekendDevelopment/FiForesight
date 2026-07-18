'use client';

import { useRouter } from 'next/navigation';
import {
  Box, Typography, Paper, Stack, Chip, Grid,
} from '@mui/material';
import { Search } from 'lucide-react';
import { useAppShell } from '../../contexts/AppShellContext';
import { useWatchlistContext } from '../../contexts/WatchlistContext';
import MorningBriefingPanel from '../../components/MorningBriefingPanel';
import SectorHeatmapPanel from '../../components/SectorHeatmapPanel';
import TrendingSparklines from '../../components/TrendingSparklines';
// Ticker search lives in the command palette (Ctrl+K / the hero trigger
// below) — the old inline Autocomplete + exchange dropdown are gone (F33).
import { openCommandPalette, Kbd } from '../../components/CommandPalette';

// Curated trending list for the landing page (TrendingSparklines fetches /api/sparklines).
const TRENDING = ['NVDA','AAPL','MSFT','TSLA','AMZN','META','GOOGL','AMD','AVGO','SPY','QQQ','BTC-USD'];

function getMarketStatus(): { open: boolean; label: string } {
  const now = new Date();
  const nyNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const day = nyNow.getDay(); // 0=Sun, 6=Sat
  const h = nyNow.getHours();
  const m = nyNow.getMinutes();
  const minutes = h * 60 + m;
  const isWeekday = day >= 1 && day <= 5;
  const open = isWeekday && minutes >= 570 && minutes < 960; // 9:30–16:00
  return { open, label: open ? 'Market Open' : 'Market Closed' };
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function LandingPage() {
  const router = useRouter();
  const { isDark, primaryColor } = useAppShell();
  const { watchlist } = useWatchlistContext();

  const market = getMarketStatus();
  const today  = new Date().toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  });

  return (
    <Box sx={{ maxWidth: 1400, mx: 'auto' }}>
      {/* ── Greeting + market status ───────────────────────────────────── */}
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        spacing={1}
        sx={{ mb: 3 }}
      >
        <Box>
          <Typography sx={{ fontWeight: 800, fontSize: { xs: '1.25rem', sm: '2.125rem' }, lineHeight: 1.2 }}>
            {getGreeting()}. Markets are {market.open ? 'open' : 'closed'}.
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.6, mt: 0.5 }}>
            {today}
          </Typography>
        </Box>
        <Chip
          label={market.label}
          sx={{
            fontWeight: 700,
            bgcolor: market.open
              ? (isDark ? 'rgba(0,255,163,0.15)' : 'rgba(22,163,74,0.12)')
              : (isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'),
            color: market.open ? (isDark ? '#00ffa3' : '#16a34a') : 'text.secondary',
          }}
        />
      </Stack>

      {/* ── Morning briefing (self-fetching) ───────────────────────────── */}
      <Box sx={{ mb: 3 }}>
        <MorningBriefingPanel
          isDark={isDark}
          primaryColor={primaryColor}
          onSelect={(t) => router.push(`/analysis?symbol=${encodeURIComponent(t)}`)}
        />
      </Box>

      <Grid container spacing={3}>
        {/* ── Search ───────────────────────────────────────────────────── */}
        <Grid size={{ xs: 12, md: 7 }}>
          <Paper
            sx={{
              p: { xs: 3, md: 5 }, height: '100%',
              display: 'flex', flexDirection: 'column', justifyContent: 'center',
              borderRadius: 4,
              background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.015)',
            }}
          >
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 0.5, textAlign: 'center' }}>
              Search a ticker
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.6, mb: 3, textAlign: 'center' }}>
              Run a full AI-driven forecast and analysis.
            </Typography>

            {/* Palette trigger (F33) — the old inline Autocomplete + exchange
                dropdown were consolidated into the command palette's live
                multi-exchange symbol search. */}
            <Paper
              onClick={openCommandPalette}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCommandPalette(); } }}
              role="button"
              tabIndex={0}
              aria-label="Search any ticker (opens the command palette)"
              data-testid="home-search-trigger"
              sx={{
                p: 0.75, display: 'flex', gap: 1, alignItems: 'center',
                borderRadius: 4, mx: 'auto', width: '100%', maxWidth: 560,
                background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                cursor: 'pointer', border: '1px solid transparent',
                '&:hover': { borderColor: `${primaryColor}55` },
              }}
            >
              <Box sx={{ pl: 1.5, display: 'flex', alignItems: 'center' }}>
                <Search size={18} color={primaryColor} />
              </Box>
              <Typography sx={{ flexGrow: 1, px: 1, py: 1, fontWeight: 700, color: 'text.secondary' }}>
                Search any ticker…
              </Typography>
              <Box sx={{ pr: 1, display: { xs: 'none', md: 'block' } }}>
                <Kbd>Ctrl K</Kbd>
              </Box>
            </Paper>
          </Paper>
        </Grid>

        {/* ── Trending (self-fetching via /api/sparklines) ─────────────── */}
        <Grid size={{ xs: 12, md: 5 }}>
          <Paper
            sx={{
              p: 2.5, height: '100%', borderRadius: 4,
              background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.015)',
            }}
          >
            <TrendingSparklines
              tickers={TRENDING}
              isDark={isDark}
              extraSymbols={watchlist.map(w => w.symbol)}
              onSelect={(s) => router.push(`/analysis?symbol=${encodeURIComponent(s)}`)}
            />
          </Paper>
        </Grid>
      </Grid>

      {/* ── Sector overview (self-fetching, interactive) ───────────────── */}
      <Box sx={{ mt: 3 }}>
        <SectorHeatmapPanel
          variant="overview"
          onSelectTicker={(etf) => router.push(`/analysis?symbol=${encodeURIComponent(etf)}`)}
          onViewAll={() => router.push('/sectors')}
        />
      </Box>
    </Box>
  );
}
