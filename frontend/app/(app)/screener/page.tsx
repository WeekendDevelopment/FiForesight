'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Box, Button, Chip, Container, FormControl, InputLabel, LinearProgress,
  MenuItem, Paper, Select, Stack, Table, TableBody, TableCell, TableContainer,
  TableHead, TablePagination, TableRow, TextField, ToggleButton,
  ToggleButtonGroup, Typography, useMediaQuery, useTheme,
} from '@mui/material';
import { SlidersHorizontal } from 'lucide-react';
import type { ScreenerFilter, ScreenerResult, ScreenerRow } from '../../../types';

// ── Formatting helpers ───────────────────────────────────────────────────────
function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return v.toFixed(digits);
}

function fmtMarketCap(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${v.toFixed(1)}%`;
}

// Parse a text field into a number or undefined (empty / invalid → undefined).
function num(s: string): number | undefined {
  if (s.trim() === '') return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

const SORT_OPTIONS = [
  { value: 'marketCap',     label: 'Market Cap' },
  { value: 'peRatio',       label: 'P/E Ratio' },
  { value: 'rsi',           label: 'RSI' },
  { value: 'dividendYield', label: 'Dividend Yield' },
];

// Local mirror of the editable filter state (strings for text inputs).
interface FilterState {
  sector: string;
  minPE: string; maxPE: string;
  minRSI: string; maxRSI: string;
  minBeta: string; maxBeta: string;
  minDividendYield: string;
  sortBy: string;
  sortDir: 'asc' | 'desc';
}

const EMPTY_FILTERS: FilterState = {
  sector: '', minPE: '', maxPE: '', minRSI: '', maxRSI: '',
  minBeta: '', maxBeta: '', minDividendYield: '',
  sortBy: 'marketCap', sortDir: 'desc',
};

export default function ScreenerPage() {
  const router = useRouter();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [rows, setRows] = useState<ScreenerRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  // Sector dropdown options are derived from the first unfiltered fetch.
  const [allSectors, setAllSectors] = useState<string[]>([]);

  const rowsPerPage = 25;

  const buildPayload = useCallback((f: FilterState): ScreenerFilter => ({
    sector: f.sector || undefined,
    minPE: num(f.minPE), maxPE: num(f.maxPE),
    minRSI: num(f.minRSI), maxRSI: num(f.maxRSI),
    minBeta: num(f.minBeta), maxBeta: num(f.maxBeta),
    minDividendYield: num(f.minDividendYield),
    sortBy: f.sortBy,
    sortDir: f.sortDir,
    limit: 50,
  }), []);

  const runScreen = useCallback(async (payload: ScreenerFilter, collectSectors = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/screener', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ScreenerResult = await res.json();
      setRows(data.results ?? []);
      setTotal(data.total ?? 0);
      setPage(0);
      if (collectSectors) {
        const sectors = Array.from(
          new Set((data.results ?? []).map(r => r.sector).filter(s => s && s !== '—')),
        ).sort();
        setAllSectors(sectors);
      }
    } catch {
      setError('Could not load the screener. Please try again.');
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial unfiltered fetch — populates the table + the sector dropdown.
  useEffect(() => {
    runScreen(buildPayload(EMPTY_FILTERS), true);
  }, [runScreen, buildPayload]);

  const handleApply = () => runScreen(buildPayload(filters));
  const handleReset = () => {
    setFilters(EMPTY_FILTERS);
    runScreen(buildPayload(EMPTY_FILTERS));
  };

  const set = (key: keyof FilterState, value: string) =>
    setFilters(prev => ({ ...prev, [key]: value }));

  const rsiColor = (rsi: number | null) => {
    if (rsi === null || rsi === undefined) return 'text.primary';
    if (rsi < 30) return 'success.main';
    if (rsi > 70) return 'error.main';
    return 'text.primary';
  };

  const pageRows = useMemo(
    () => rows.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage),
    [rows, page],
  );

  // ── Filter sidebar ─────────────────────────────────────────────────────────
  const filterPanel = (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <SlidersHorizontal size={18} color={theme.palette.primary.main} />
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Filters</Typography>
      </Stack>

      <Stack spacing={2}>
        <FormControl size="small" fullWidth>
          <InputLabel id="sector-label">Sector</InputLabel>
          <Select
            labelId="sector-label"
            label="Sector"
            value={filters.sector}
            onChange={e => set('sector', e.target.value)}
          >
            <MenuItem value="">All Sectors</MenuItem>
            {allSectors.map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
          </Select>
        </FormControl>

        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>P/E Ratio</Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
            <TextField size="small" type="number" label="Min" value={filters.minPE} onChange={e => set('minPE', e.target.value)} fullWidth />
            <TextField size="small" type="number" label="Max" value={filters.maxPE} onChange={e => set('maxPE', e.target.value)} fullWidth />
          </Stack>
        </Box>

        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>RSI</Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
            <TextField size="small" type="number" label="Min" value={filters.minRSI} onChange={e => set('minRSI', e.target.value)} fullWidth />
            <TextField size="small" type="number" label="Max" value={filters.maxRSI} onChange={e => set('maxRSI', e.target.value)} fullWidth />
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, opacity: 0.7 }}>
            Oversold &lt; 30, Overbought &gt; 70
          </Typography>
        </Box>

        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Beta</Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
            <TextField size="small" type="number" label="Min" value={filters.minBeta} onChange={e => set('minBeta', e.target.value)} fullWidth />
            <TextField size="small" type="number" label="Max" value={filters.maxBeta} onChange={e => set('maxBeta', e.target.value)} fullWidth />
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, opacity: 0.7 }}>
            &lt; 1 = less volatile than market
          </Typography>
        </Box>

        <TextField
          size="small" type="number" fullWidth
          label="Min Dividend Yield %"
          value={filters.minDividendYield}
          onChange={e => set('minDividendYield', e.target.value)}
        />

        <FormControl size="small" fullWidth>
          <InputLabel id="sortby-label">Sort by</InputLabel>
          <Select
            labelId="sortby-label"
            label="Sort by"
            value={filters.sortBy}
            onChange={e => set('sortBy', e.target.value)}
          >
            {SORT_OPTIONS.map(o => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </Select>
        </FormControl>

        <ToggleButtonGroup
          size="small"
          exclusive
          fullWidth
          value={filters.sortDir}
          onChange={(_, v) => { if (v) set('sortDir', v); }}
          aria-label="Sort direction"
        >
          <ToggleButton value="asc">↑ Asc</ToggleButton>
          <ToggleButton value="desc">↓ Desc</ToggleButton>
        </ToggleButtonGroup>

        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={handleApply} fullWidth disabled={loading}>Apply Filters</Button>
          <Button variant="outlined" onClick={handleReset} fullWidth disabled={loading}>Reset</Button>
        </Stack>

        <Box sx={{ p: 1.25, borderRadius: 1.5, bgcolor: 'action.hover', textAlign: 'center' }}>
          <Typography variant="caption" color="text.secondary">
            Searching <strong>{total}</strong> of 50 stocks
          </Typography>
        </Box>
      </Stack>
    </Paper>
  );

  // ── Results table ──────────────────────────────────────────────────────────
  const resultsTable = (
    <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden' }}>
      {loading && <LinearProgress />}
      <TableContainer sx={{ maxWidth: '100%' }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>Symbol</TableCell>
              {!isMobile && <TableCell sx={{ fontWeight: 700 }}>Name</TableCell>}
              {!isMobile && <TableCell sx={{ fontWeight: 700 }}>Sector</TableCell>}
              <TableCell align="right" sx={{ fontWeight: 700 }}>Price</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>P/E</TableCell>
              {!isMobile && <TableCell align="right" sx={{ fontWeight: 700 }}>Fwd P/E</TableCell>}
              <TableCell align="right" sx={{ fontWeight: 700 }}>Beta</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>RSI</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>Div Yield</TableCell>
              {!isMobile && <TableCell align="right" sx={{ fontWeight: 700 }}>Rev Growth</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {!loading && pageRows.length === 0 && (
              <TableRow>
                <TableCell colSpan={isMobile ? 6 : 10} align="center" sx={{ py: 6 }}>
                  <Typography color="text.secondary">
                    No stocks match your filters — try widening the criteria
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {pageRows.map(row => (
              <TableRow key={row.symbol} hover>
                <TableCell>
                  <Chip
                    label={row.symbol}
                    size="small"
                    color="primary"
                    variant="outlined"
                    clickable
                    onClick={() => router.push(`/analysis?symbol=${encodeURIComponent(row.symbol)}`)}
                    sx={{ fontWeight: 700 }}
                  />
                </TableCell>
                {!isMobile && (
                  <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {row.name}
                  </TableCell>
                )}
                {!isMobile && <TableCell>{row.sector}</TableCell>}
                <TableCell align="right">{row.price !== null ? `$${fmtNum(row.price)}` : '—'}</TableCell>
                <TableCell align="right">{fmtNum(row.peRatio)}</TableCell>
                {!isMobile && <TableCell align="right">{fmtNum(row.forwardPE)}</TableCell>}
                <TableCell align="right">{fmtNum(row.beta)}</TableCell>
                <TableCell align="right" sx={{ color: rsiColor(row.rsi), fontWeight: 600 }}>
                  {fmtNum(row.rsi, 1)}
                </TableCell>
                <TableCell align="right">{fmtPct(row.dividendYield)}</TableCell>
                {!isMobile && <TableCell align="right">{fmtPct(row.revenueGrowth)}</TableCell>}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={rows.length}
        page={page}
        onPageChange={(_, p) => setPage(p)}
        rowsPerPage={rowsPerPage}
        rowsPerPageOptions={[rowsPerPage]}
      />
    </Paper>
  );

  return (
    <Container maxWidth="xl" disableGutters>
      <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '-0.02em', mb: 0.5 }}>
        Equity Screener
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Filter our curated 50-stock universe by sector, valuation, momentum and yield.
      </Typography>

      {error && (
        <Typography color="error.main" sx={{ mb: 2 }}>{error}</Typography>
      )}

      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          gap: { xs: 2, md: 3 },
          alignItems: 'flex-start',
        }}
      >
        <Box sx={{ width: { xs: '100%', md: 280 }, flexShrink: 0, position: { md: 'sticky' }, top: { md: 16 } }}>
          {filterPanel}
        </Box>
        <Box sx={{ flexGrow: 1, minWidth: 0, width: '100%' }}>
          {resultsTable}
        </Box>
      </Box>
    </Container>
  );
}
