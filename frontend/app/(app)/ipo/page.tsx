'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Box, Card, CardContent, Chip, Container, Skeleton, Stack, Tab, Tabs, Typography,
} from '@mui/material';
import {
  Rocket, Calendar, DollarSign, Package, Briefcase, ExternalLink,
} from 'lucide-react';
import { useAppShell } from '../../../contexts/AppShellContext';
import type { IpoEntry, IpoCalendarResult } from '../../../types';

type View = 'upcoming' | 'recent';

// ── Formatting helpers ───────────────────────────────────────────────────────
function formatMarketCap(n: number | null): string {
  if (!n) return 'N/A';
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}

function formatShares(n: number | null): string | null {
  if (!n) return null;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B shares offered`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M shares offered`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K shares offered`;
  return `${n.toLocaleString()} shares offered`;
}

function formatPriceRange(low: number | null, high: number | null): string {
  if (low == null && high == null) return 'Price TBD';
  if (low != null && high != null) {
    return low === high ? `$${low} per share` : `$${low} – $${high} per share`;
  }
  return `$${low ?? high} per share`;
}

/** Render a "YYYY-MM-DD" string as e.g. "Jun 15, 2025" (local, no deps). */
function formatIpoDate(s: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return s || 'Date TBD';
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

type ChipColor = 'info' | 'success' | 'error' | 'default';

function statusChip(actions: string, status: string): { label: string; color: ChipColor } {
  const a = (actions || '').toLowerCase();
  if (a.includes('priced'))    return { label: 'Priced',    color: 'success' };
  if (a.includes('withdrawn')) return { label: 'Withdrawn', color: 'error'   };
  if (a.includes('s-1'))       return { label: 'S-1 Filed', color: 'default' };
  if (a.includes('expected') || status === 'upcoming') return { label: 'Expected', color: 'info' };
  return { label: actions || 'Recent', color: 'default' };
}

function edgarUrl(company: string, symbol: string): string {
  const c = encodeURIComponent(company || symbol);
  return symbol
    ? `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${c}&type=S-1&dateb=&owner=include&count=10`
    : `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${c}&type=S-1`;
}

const TABS: { value: View; label: string }[] = [
  { value: 'upcoming', label: 'Upcoming IPOs' },
  { value: 'recent',   label: 'Recent IPOs'   },
];

export default function IpoPage() {
  const { isDark, primaryColor } = useAppShell();
  const router = useRouter();

  const [data,    setData]    = useState<IpoCalendarResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(false);
  const [view,    setView]    = useState<View>('upcoming');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/ipo');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: IpoCalendarResult = await res.json();
        if (!cancelled) setData(json);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const borderCol = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
  const hoverBg   = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)';
  const metaCol   = isDark ? 'rgba(255,255,255,0.55)' : 'rgba(0,0,0,0.55)';

  const sourceLabel = data?.source === 'fmp' ? 'Powered by FMP' : 'Powered by SEC EDGAR';
  const entries = data ? (view === 'upcoming' ? data.upcoming : data.recent) : [];

  // ── IPO card ───────────────────────────────────────────────────────────────
  const renderCard = (ipo: IpoEntry, idx: number) => {
    const chip = statusChip(ipo.actions, ipo.status);
    const sharesLabel = formatShares(ipo.shares);
    const clickable = Boolean(ipo.symbol);
    const goToAnalysis = () => {
      if (clickable) router.push(`/analysis?symbol=${encodeURIComponent(ipo.symbol)}`);
    };

    return (
      <Card
        key={`${ipo.symbol || ipo.company}-${ipo.date}-${idx}`}
        role={clickable ? 'button' : undefined}
        tabIndex={clickable ? 0 : undefined}
        onClick={clickable ? goToAnalysis : undefined}
        onKeyDown={clickable ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goToAnalysis(); }
        } : undefined}
        sx={{
          border: `1px solid ${borderCol}`,
          cursor: clickable ? 'pointer' : 'default',
          transition: 'background 0.15s ease, border-color 0.15s ease',
          '&:hover': clickable
            ? { background: hoverBg, borderColor: `${primaryColor}66` }
            : undefined,
        }}
      >
        <CardContent sx={{ p: '16px !important' }}>
          {/* Header: ticker / company + exchange */}
          <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
            <Box sx={{ minWidth: 0 }}>
              {ipo.symbol && (
                <Typography sx={{ fontWeight: 800, fontSize: '1rem', color: primaryColor, lineHeight: 1.2 }}>
                  {ipo.symbol}
                </Typography>
              )}
              <Typography
                sx={{
                  fontSize: ipo.symbol ? '0.82rem' : '0.95rem',
                  fontWeight: ipo.symbol ? 500 : 700,
                  opacity: ipo.symbol ? 0.8 : 1,
                  mt: ipo.symbol ? 0.25 : 0,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
                title={ipo.company}
              >
                {ipo.company || 'Unknown'}
              </Typography>
            </Box>
            {ipo.exchange && (
              <Chip
                label={ipo.exchange}
                size="small"
                variant="outlined"
                sx={{ flexShrink: 0, fontSize: '0.68rem', height: 22, borderColor: borderCol }}
              />
            )}
          </Stack>

          <Box sx={{ borderTop: `1px solid ${borderCol}`, my: 1.5 }} />

          {/* Detail rows */}
          <Stack spacing={0.85}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Calendar size={15} color={metaCol} />
              <Typography sx={{ fontSize: '0.8rem' }}>{formatIpoDate(ipo.date)}</Typography>
            </Stack>
            <Stack direction="row" alignItems="center" spacing={1}>
              <DollarSign size={15} color={metaCol} />
              <Typography sx={{ fontSize: '0.8rem' }}>
                {formatPriceRange(ipo.price_low, ipo.price_high)}
              </Typography>
            </Stack>
            {sharesLabel && (
              <Stack direction="row" alignItems="center" spacing={1}>
                <Package size={15} color={metaCol} />
                <Typography sx={{ fontSize: '0.8rem' }}>{sharesLabel}</Typography>
              </Stack>
            )}
            {ipo.market_cap != null && (
              <Stack direction="row" alignItems="center" spacing={1}>
                <Briefcase size={15} color={metaCol} />
                <Typography sx={{ fontSize: '0.8rem' }}>
                  Est. market cap: {formatMarketCap(ipo.market_cap)}
                </Typography>
              </Stack>
            )}
          </Stack>

          <Box sx={{ mt: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
            <Chip label={chip.label} size="small" color={chip.color} sx={{ fontSize: '0.7rem', height: 22 }} />
            <Box
              component="a"
              href={edgarUrl(ipo.company, ipo.symbol)}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              sx={{
                display: 'inline-flex', alignItems: 'center', gap: 0.5,
                fontSize: '0.72rem', color: primaryColor, textDecoration: 'none',
                '&:hover': { textDecoration: 'underline' },
              }}
            >
              View on SEC EDGAR
              <ExternalLink size={13} />
            </Box>
          </Box>
        </CardContent>
      </Card>
    );
  };

  return (
    <Container maxWidth="lg" disableGutters>
      {/* Heading */}
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.5 }}>
        <Rocket size={26} color={primaryColor} />
        <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
          IPO Tracker
        </Typography>
        {!loading && !error && data && (
          <Chip
            label={sourceLabel}
            size="small"
            variant="outlined"
            sx={{ ml: 1, fontSize: '0.68rem', height: 22, borderColor: borderCol, color: 'text.secondary' }}
          />
        )}
      </Stack>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Upcoming and recent public offerings
      </Typography>

      {/* View tabs */}
      <Tabs
        value={view}
        onChange={(_, v: View) => setView(v)}
        sx={{ mb: 3, minHeight: 38, '& .MuiTab-root': { minHeight: 38, textTransform: 'none', fontWeight: 600 } }}
      >
        {TABS.map(t => <Tab key={t.value} value={t.value} label={t.label} />)}
      </Tabs>

      {/* Loading — skeleton grid */}
      {loading && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
          {[0, 1, 2, 3, 4, 5].map(i => <Skeleton key={i} variant="rounded" height={200} />)}
        </Box>
      )}

      {/* Error — surfaces optional FMP config gracefully */}
      {!loading && error && (
        <Box sx={{ py: 8, textAlign: 'center', opacity: 0.7 }}>
          <Rocket size={44} color={primaryColor} style={{ opacity: 0.5 }} />
          <Typography sx={{ mt: 2, fontWeight: 600 }}>IPO data temporarily unavailable.</Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: 460, mx: 'auto' }}>
            To enable full IPO tracking, add a free FMP API key to your backend <code>.env</code>.
          </Typography>
        </Box>
      )}

      {/* Empty */}
      {!loading && !error && entries.length === 0 && (
        <Box sx={{ py: 8, textAlign: 'center', opacity: 0.5 }}>
          <Rocket size={44} color={primaryColor} style={{ opacity: 0.5 }} />
          <Typography sx={{ mt: 2 }}>
            {view === 'upcoming'
              ? 'No IPOs currently scheduled in the next 90 days.'
              : 'No recent IPOs in the last 30 days.'}
          </Typography>
        </Box>
      )}

      {/* Card grid */}
      {!loading && !error && entries.length > 0 && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
          {entries.map(renderCard)}
        </Box>
      )}
    </Container>
  );
}
