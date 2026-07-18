'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Box, Button, Checkbox, Chip, IconButton, ListItemText, Menu, MenuItem,
  Paper, Skeleton, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TableSortLabel, Typography, useMediaQuery, useTheme,
} from '@mui/material';
import { Columns3, Star, X } from 'lucide-react';
import { useWatchlistContext } from '../../../contexts/WatchlistContext';
import { useAuth } from '../../../contexts/AuthContext';
import AuthModal from '../../../components/AuthModal';
import type { WatchlistMetricRow } from '../../../types';
import { formatPrice } from '../../../lib/currency';

const COLS_KEY = 'fiforesight:watchlist:cols';

type ColumnKey = 'price' | 'changePct' | 'peRatio' | 'rsi' | 'pctFrom52wHigh' | 'marketCap' | 'nextEarnings';

const COLUMNS: { key: ColumnKey; label: string; mobileHidden?: boolean }[] = [
  { key: 'price',          label: 'Price' },
  { key: 'changePct',      label: '% Chg' },
  { key: 'peRatio',        label: 'P/E', mobileHidden: true },
  { key: 'rsi',            label: 'RSI' },
  { key: 'pctFrom52wHigh', label: '% from 52wk High' },
  { key: 'marketCap',      label: 'Mkt Cap', mobileHidden: true },
  { key: 'nextEarnings',   label: 'Next Earnings', mobileHidden: true },
];

const ALL_KEYS = COLUMNS.map(c => c.key);

function loadVisibleCols(): Record<ColumnKey, boolean> {
  const defaults = Object.fromEntries(ALL_KEYS.map(k => [k, true])) as Record<ColumnKey, boolean>;
  if (typeof window === 'undefined') return defaults;
  try {
    const raw = window.localStorage.getItem(COLS_KEY);
    if (!raw) return defaults;
    const saved = JSON.parse(raw) as ColumnKey[];
    if (!Array.isArray(saved)) return defaults;
    return Object.fromEntries(ALL_KEYS.map(k => [k, saved.includes(k)])) as Record<ColumnKey, boolean>;
  } catch {
    return defaults;
  }
}

function saveVisibleCols(cols: Record<ColumnKey, boolean>) {
  if (typeof window === 'undefined') return;
  const enabled = ALL_KEYS.filter(k => cols[k]);
  window.localStorage.setItem(COLS_KEY, JSON.stringify(enabled));
}

// Label prices in the row's own quote currency (F35) — LSE rows quote GBp
// (pence), so a hardcoded '$' would be wrong-symbol AND ~75× off.
function fmtPrice(v: number | null, currency?: string | null): string {
  return v === null || v === undefined ? '—' : formatPrice(v, currency);
}

function fmtPct(v: number | null): string {
  return v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function fmtNum(v: number | null, digits = 1): string {
  return v === null || v === undefined ? '—' : v.toFixed(digits);
}

function fmtCap(v: number | null): string {
  if (v === null || v === undefined) return '—';
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  return v.toFixed(0);
}

export default function WatchlistPage() {
  const router = useRouter();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const { watchlist, isLoading: wlLoading, remove } = useWatchlistContext();
  const { session } = useAuth();
  const [authOpen, setAuthOpen] = useState(false);

  const [metrics, setMetrics] = useState<WatchlistMetricRow[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [sortKey, setSortKey] = useState<ColumnKey | 'symbol'>('symbol');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [visibleCols, setVisibleCols] = useState<Record<ColumnKey, boolean>>(
    () => Object.fromEntries(ALL_KEYS.map(k => [k, true])) as Record<ColumnKey, boolean>,
  );
  const [colMenuAnchor, setColMenuAnchor] = useState<HTMLElement | null>(null);

  useEffect(() => { setVisibleCols(loadVisibleCols()); }, []);

  const symbolKey = useMemo(
    () => [...new Set(watchlist.map(i => i.symbol))].slice(0, 30).join(','),
    [watchlist],
  );

  const fetchMetrics = useCallback(async () => {
    if (!symbolKey) { setMetrics([]); return; }
    setMetricsLoading(true);
    try {
      const res  = await fetch(`/api/watchlist/metrics?symbols=${encodeURIComponent(symbolKey)}`);
      const data = await res.json() as WatchlistMetricRow[];
      setMetrics(Array.isArray(data) ? data : []);
    } catch {
      // non-fatal — table falls back to empty metric cells
    } finally {
      setMetricsLoading(false);
    }
  }, [symbolKey]);

  useEffect(() => { void fetchMetrics(); }, [fetchMetrics]);

  useEffect(() => {
    const id = setInterval(() => { void fetchMetrics(); }, 60_000);
    return () => clearInterval(id);
  }, [fetchMetrics]);

  const metricsMap = useMemo(() => {
    const m: Record<string, WatchlistMetricRow> = {};
    metrics.forEach(row => { m[row.symbol] = row; });
    return m;
  }, [metrics]);

  const toggleCol = (key: ColumnKey) => {
    setVisibleCols(prev => {
      const next = { ...prev, [key]: !prev[key] };
      saveVisibleCols(next);
      return next;
    });
  };

  const handleSort = (key: ColumnKey | 'symbol') => {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sortedRows = useMemo(() => {
    const rows = watchlist.map(item => ({
      item,
      row: metricsMap[item.symbol] ?? null,
    }));
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (sortKey === 'symbol') {
        return a.item.symbol.localeCompare(b.item.symbol) * dir;
      }
      const av = a.row?.[sortKey];
      const bv = b.row?.[sortKey];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === 'string' || typeof bv === 'string') {
        return String(av).localeCompare(String(bv)) * dir;
      }
      return (av - bv) * dir;
    });
  }, [watchlist, metricsMap, sortKey, sortDir]);

  const rsiColor = (rsi: number | null) => {
    if (rsi === null || rsi === undefined) return 'text.primary';
    if (rsi < 30) return 'success.main';
    if (rsi > 70) return 'error.main';
    return 'text.primary';
  };

  const chgColor = (v: number | null) => {
    if (v === null || v === undefined) return 'text.primary';
    return v >= 0 ? 'success.main' : 'error.main';
  };

  if (!session) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 260, gap: 2, textAlign: 'center' }}>
        <Star size={36} color={theme.palette.text.disabled} />
        <Typography color="text.secondary">Sign in to save and view your watchlist.</Typography>
        <Button variant="outlined" size="small" onClick={() => setAuthOpen(true)}>Sign In</Button>
        <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
      </Box>
    );
  }

  if (wlLoading) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} variant="rectangular" height={44} sx={{ borderRadius: 1 }} />
        ))}
      </Box>
    );
  }

  if (!watchlist.length) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 260, gap: 1.5, textAlign: 'center' }}>
        <Star size={36} color={theme.palette.text.disabled} />
        <Typography color="text.secondary">Your watchlist is empty.</Typography>
        <Typography variant="caption" color="text.secondary">
          Tap ☆ on any Analysis page to add a stock.
        </Typography>
      </Box>
    );
  }

  const visibleColumns = COLUMNS.filter(c => visibleCols[c.key] && !(isMobile && c.mobileHidden));
  const colSpan = visibleColumns.length + 2; // symbol + remove

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Watchlist · {watchlist.length} {watchlist.length === 1 ? 'symbol' : 'symbols'}
        </Typography>
        <IconButton
          size="small"
          onClick={e => setColMenuAnchor(e.currentTarget)}
          aria-label="Choose columns"
        >
          <Columns3 size={18} />
        </IconButton>
        <Menu anchorEl={colMenuAnchor} open={!!colMenuAnchor} onClose={() => setColMenuAnchor(null)}>
          {COLUMNS.map(c => (
            <MenuItem key={c.key} onClick={() => toggleCol(c.key)} dense>
              <Checkbox size="small" checked={visibleCols[c.key]} />
              <ListItemText primary={c.label} />
            </MenuItem>
          ))}
        </Menu>
      </Box>

      <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden' }}>
        <TableContainer sx={{ maxWidth: '100%', overflowX: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>
                  <TableSortLabel
                    active={sortKey === 'symbol'}
                    direction={sortKey === 'symbol' ? sortDir : 'asc'}
                    onClick={() => handleSort('symbol')}
                  >
                    Symbol
                  </TableSortLabel>
                </TableCell>
                {visibleColumns.map(c => (
                  <TableCell key={c.key} align="right" sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortKey === c.key}
                      direction={sortKey === c.key ? sortDir : 'asc'}
                      onClick={() => handleSort(c.key)}
                    >
                      {c.label}
                    </TableSortLabel>
                  </TableCell>
                ))}
                <TableCell align="right" sx={{ fontWeight: 700 }} />
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedRows.map(({ item, row }) => (
                <TableRow key={item.id} hover>
                  <TableCell>
                    <Chip
                      label={item.symbol}
                      size="small"
                      color="primary"
                      variant="outlined"
                      clickable
                      onClick={() => router.push(`/analysis?symbol=${encodeURIComponent(item.symbol)}`)}
                      sx={{ fontWeight: 700 }}
                    />
                  </TableCell>
                  {visibleColumns.map(c => {
                    const val = row ? row[c.key] : null;
                    if (metricsLoading && !row) {
                      return <TableCell key={c.key} align="right"><Skeleton width={40} sx={{ ml: 'auto' }} /></TableCell>;
                    }
                    switch (c.key) {
                      case 'price':
                        return <TableCell key={c.key} align="right">{fmtPrice(val as number | null, row?.currency)}</TableCell>;
                      case 'changePct':
                        return (
                          <TableCell key={c.key} align="right" sx={{ color: chgColor(val as number | null), fontWeight: 600 }}>
                            {fmtPct(val as number | null)}
                          </TableCell>
                        );
                      case 'peRatio':
                        return <TableCell key={c.key} align="right">{fmtNum(val as number | null, 1)}</TableCell>;
                      case 'rsi':
                        return (
                          <TableCell key={c.key} align="right" sx={{ color: rsiColor(val as number | null), fontWeight: 600 }}>
                            {fmtNum(val as number | null, 1)}
                          </TableCell>
                        );
                      case 'pctFrom52wHigh':
                        return <TableCell key={c.key} align="right">{fmtPct(val as number | null)}</TableCell>;
                      case 'marketCap':
                        return <TableCell key={c.key} align="right">{fmtCap(val as number | null)}</TableCell>;
                      case 'nextEarnings':
                        return <TableCell key={c.key} align="right">{(val as string | null) ?? '—'}</TableCell>;
                      default:
                        return <TableCell key={c.key} align="right">—</TableCell>;
                    }
                  })}
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      onClick={() => remove(item.symbol)}
                      aria-label={`Remove ${item.symbol}`}
                    >
                      <X size={14} />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
              {sortedRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={colSpan} align="center" sx={{ py: 4 }}>
                    <Typography color="text.secondary">No symbols yet.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
}
