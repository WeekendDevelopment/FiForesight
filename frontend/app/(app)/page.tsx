'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Box, Typography, Paper, TextField, Button, Select, MenuItem, Autocomplete,
  Stack, Chip, CircularProgress, Grid,
} from '@mui/material';
import { Search } from 'lucide-react';
import { useAppShell } from '../../contexts/AppShellContext';
import MorningBriefingPanel from '../../components/MorningBriefingPanel';
import SectorHeatmap from '../../components/SectorHeatmap';
import TrendingSparklines from '../../components/TrendingSparklines';

const EXCHANGES = [
  { value: '',       label: 'Auto'         },
  { value: 'NASDAQ', label: 'NASDAQ'       },
  { value: 'NYSE',   label: 'NYSE'         },
  { value: 'LSE',    label: 'London (LSE)' },
  { value: 'FRA',    label: 'Frankfurt'    },
];

const POPULAR_TICKERS = [
  'AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK.B','JPM','V',
  'UNH','MA','XOM','LLY','JNJ','PG','HD','MRK','AVGO','CVX',
  'KO','PEP','ABBV','COST','MCD','CSCO','TMO','WMT','ACN','ABT',
  'SPY','QQQ','DIA','IWM','GLD','SLV','TLT','BTC-USD','ETH-USD',
];

// Curated trending list for the landing page (TrendingSparklines fetches /api/sparklines).
const TRENDING = ['NVDA','AAPL','MSFT','TSLA','AMZN','META','GOOGL','AMD','AVGO','SPY','QQQ','BTC-USD']
  .map(symbol => ({ symbol }));

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
  const [ticker, setTicker]     = useState('');
  const [exchange, setExchange] = useState('');
  const [navigating, setNavigating] = useState(false);

  const market = getMarketStatus();
  const today  = new Date().toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  });

  const handleSearch = () => {
    const sym = ticker.trim().toUpperCase();
    if (!sym) return;
    setNavigating(true);
    const q = exchange ? `${sym}:${exchange}` : sym;
    router.push(`/analysis?symbol=${encodeURIComponent(q)}`);
  };

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
          <Typography variant="h4" sx={{ fontWeight: 800 }}>
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
        <MorningBriefingPanel isDark={isDark} primaryColor={primaryColor} />
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

            <Paper
              sx={{
                p: 0.75, display: 'flex', gap: 1, alignItems: 'center',
                borderRadius: 4, mx: 'auto', width: '100%', maxWidth: 560,
                background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
              }}
            >
              <Autocomplete
                freeSolo
                options={POPULAR_TICKERS}
                value={ticker}
                onInputChange={(_, v) => setTicker(v.toUpperCase())}
                onChange={(_, v) => v && setTicker(String(v).toUpperCase())}
                sx={{ flexGrow: 1 }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    placeholder="Search a ticker…"
                    variant="standard"
                    onKeyDown={e => e.key === 'Enter' && handleSearch()}
                    InputProps={{ ...params.InputProps, disableUnderline: true, sx: { px: 2, fontWeight: 700 } }}
                  />
                )}
              />
              <Select
                value={exchange}
                onChange={e => setExchange(e.target.value)}
                variant="standard"
                disableUnderline
                sx={{ minWidth: 100, fontWeight: 600, fontSize: '0.8rem' }}
              >
                {EXCHANGES.map(ex => <MenuItem key={ex.value} value={ex.value}>{ex.label}</MenuItem>)}
              </Select>
              <Button
                variant="contained"
                onClick={handleSearch}
                disabled={navigating}
                sx={{ borderRadius: 3, minWidth: 50, py: 1, boxShadow: `0 0 20px ${primaryColor}4d` }}
              >
                {navigating ? <CircularProgress size={20} color="inherit" /> : <Search size={20} />}
              </Button>
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
            <TrendingSparklines tickers={TRENDING} isDark={isDark} />
          </Paper>
        </Grid>
      </Grid>

      {/* ── Sector heatmap (self-fetching) ─────────────────────────────── */}
      <Box sx={{ mt: 3 }}>
        <SectorHeatmap isDark={isDark} primaryColor={primaryColor} />
      </Box>
    </Box>
  );
}
