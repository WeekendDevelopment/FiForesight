'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Box, Card, CardContent, CircularProgress, Container, Skeleton, Stack,
  Tab, Tabs, Typography,
} from '@mui/material';
import { Calendar } from 'lucide-react';
import { useAppShell } from '../../../contexts/AppShellContext';
import type { EarningsEntry, EarningsCalendarResult } from '../../../types';

type Period = 'week' | 'month' | 'nextMonth' | 'all';

const TABS: { value: Period; label: string }[] = [
  { value: 'week',      label: 'This Week'    },
  { value: 'month',     label: 'This Month'   },
  { value: 'nextMonth', label: 'Next Month'   },
  { value: 'all',       label: 'All Upcoming' },
];

// ── Date helpers (midnight-local, no external deps) ──────────────────────────
function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}
function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}
/** Parse a "YYYY-MM-DD" string into a local midnight Date (null if invalid). */
function parseDate(s: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}
function formatDateHeader(d: Date): string {
  return d.toLocaleDateString('en-US', {
    weekday: 'long', month: 'short', day: 'numeric', year: 'numeric',
  });
}
function formatCardDate(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

interface DayGroup {
  date:    Date;
  iso:     string;
  entries: EarningsEntry[];
}

export default function EarningsPage() {
  const { isDark, primaryColor } = useAppShell();
  const router = useRouter();

  const [calendar, setCalendar] = useState<Record<string, EarningsEntry[]> | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  const [period,   setPeriod]   = useState<Period>('week');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/earnings');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: EarningsCalendarResult = await res.json();
        if (!cancelled) setCalendar(json.calendar ?? {});
      } catch {
        if (!cancelled) setError('Could not load the earnings calendar. Please try again later.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Filter + group by the selected period, sorted ascending.
  const groups: DayGroup[] = useMemo(() => {
    if (!calendar) return [];
    const today = startOfDay(new Date());

    let rangeStart = today;
    let rangeEnd: Date | null;
    if (period === 'week') {
      rangeEnd = addDays(today, 7);
    } else if (period === 'month') {
      rangeEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0); // end of this month
    } else if (period === 'nextMonth') {
      rangeStart = new Date(today.getFullYear(), today.getMonth() + 1, 1);
      rangeEnd   = new Date(today.getFullYear(), today.getMonth() + 2, 0); // end of next month
    } else {
      rangeEnd = null; // all upcoming
    }

    const out: DayGroup[] = [];
    for (const [iso, entries] of Object.entries(calendar)) {
      const d = parseDate(iso);
      if (!d) continue;
      if (d < rangeStart) continue;
      if (rangeEnd && d > rangeEnd) continue;
      if (entries.length === 0) continue;
      out.push({ date: d, iso, entries });
    }
    out.sort((a, b) => a.date.getTime() - b.date.getTime());
    return out;
  }, [calendar, period]);

  const borderCol = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
  const hoverBg   = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)';

  return (
    <Container maxWidth="lg" disableGutters>
      {/* Heading */}
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.5 }}>
        <Calendar size={26} color={primaryColor} />
        <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
          Earnings Calendar
        </Typography>
      </Stack>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Upcoming earnings for the largest S&P 500 companies — who reports this week, this month.
      </Typography>

      {/* Period tabs */}
      <Tabs
        value={period}
        onChange={(_, v: Period) => setPeriod(v)}
        sx={{ mb: 3, minHeight: 38, '& .MuiTab-root': { minHeight: 38, textTransform: 'none', fontWeight: 600 } }}
      >
        {TABS.map(t => <Tab key={t.value} value={t.value} label={t.label} />)}
      </Tabs>

      {/* Loading */}
      {loading && (
        <Stack alignItems="center" spacing={2} sx={{ py: 8 }}>
          <CircularProgress />
          <Typography color="text.secondary" sx={{ textAlign: 'center' }}>
            Loading earnings for top S&P 500 stocks…<br />
            <Typography component="span" variant="caption" sx={{ opacity: 0.6 }}>
              (this may take up to 30s on first load)
            </Typography>
          </Typography>
          <Stack spacing={1.5} sx={{ width: '100%', mt: 2 }}>
            {[0, 1, 2].map(i => <Skeleton key={i} variant="rounded" height={120} />)}
          </Stack>
        </Stack>
      )}

      {/* Error */}
      {!loading && error && (
        <Typography color="text.secondary" sx={{ py: 6, textAlign: 'center' }}>{error}</Typography>
      )}

      {/* Empty */}
      {!loading && !error && groups.length === 0 && (
        <Box sx={{ py: 8, textAlign: 'center', opacity: 0.5 }}>
          <Calendar size={44} color={primaryColor} style={{ opacity: 0.5 }} />
          <Typography sx={{ mt: 2 }}>No earnings scheduled for this period</Typography>
        </Box>
      )}

      {/* Calendar grid */}
      {!loading && !error && groups.length > 0 && (
        <Stack spacing={3}>
          {groups.map(group => (
            <Box key={group.iso}>
              <Typography sx={{ fontWeight: 700, fontSize: '0.95rem', mb: 1.25 }}>
                {formatDateHeader(group.date)}
                <Typography component="span" sx={{ opacity: 0.45, fontWeight: 500, ml: 1, fontSize: '0.85rem' }}>
                  · {group.entries.length} {group.entries.length === 1 ? 'company' : 'companies'}
                </Typography>
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5 }}>
                {group.entries.map(e => (
                  <Card
                    key={e.symbol}
                    role="button"
                    tabIndex={0}
                    onClick={() => router.push(`/analysis?symbol=${encodeURIComponent(e.symbol)}`)}
                    onKeyDown={ev => {
                      if (ev.key === 'Enter' || ev.key === ' ') {
                        ev.preventDefault();
                        router.push(`/analysis?symbol=${encodeURIComponent(e.symbol)}`);
                      }
                    }}
                    sx={{
                      cursor: 'pointer', width: 168, border: `1px solid ${borderCol}`,
                      transition: 'background 0.15s ease, border-color 0.15s ease',
                      '&:hover': { background: hoverBg, borderColor: `${primaryColor}66` },
                    }}
                  >
                    <CardContent sx={{ p: '12px !important' }}>
                      <Typography sx={{ fontWeight: 800, fontSize: '0.95rem', color: primaryColor }}>
                        {e.symbol}
                      </Typography>
                      <Typography
                        sx={{
                          fontSize: '0.72rem', opacity: 0.7, mt: 0.25,
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                        }}
                        title={e.name}
                      >
                        {e.name}
                      </Typography>
                      <Typography sx={{ fontSize: '0.66rem', opacity: 0.5, mt: 0.75 }}>
                        {formatCardDate(group.date)}
                      </Typography>
                    </CardContent>
                  </Card>
                ))}
              </Box>
            </Box>
          ))}
        </Stack>
      )}
    </Container>
  );
}
