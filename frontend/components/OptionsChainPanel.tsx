'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Chip, CircularProgress, MenuItem, Select, Stack,
  Table, TableBody, TableCell, TableHead, TableRow, ToggleButton,
  ToggleButtonGroup, Typography,
} from '@mui/material';
import { Activity } from 'lucide-react';
import type { OptionsChainResult, OptionContract } from '../types';

type View = 'both' | 'calls' | 'puts';

interface Props {
  /** If provided, the panel fetches /api/options/{symbol} internally. */
  symbol?:         string;
  /** If provided, used directly (backward compat for the analysis tab). */
  data?:           OptionsChainResult;
  isDark:          boolean;
  primaryColor:    string;
  /** Backward-compat callback for the data-fed (analysis) path. */
  onExpiryChange?: (expiry: string) => void;
}

const cell = { fontSize: '0.68rem', py: 0.5, px: 1 };
const HEADERS = ['Strike', 'Last', 'Bid', 'Ask', 'Chg%', 'Vol', 'OI', 'IV%', 'Δ', 'Θ'];

function ContractRow({ c, isDark }: { c: OptionContract; isDark: boolean }) {
  const itm   = c.in_the_money;
  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';
  const grey  = isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.4)';
  const itmBg = c.type === 'call'
    ? (itm ? `${green}10` : 'transparent')
    : (itm ? `${red}10`   : 'transparent');
  // Delta: green when the contract has meaningful directional exposure (|Δ|>0.5),
  // muted grey for near-zero (deep OTM) contracts.
  const deltaColor = Math.abs(c.delta) > 0.5 ? green : grey;

  return (
    <TableRow sx={{ background: itmBg, '&:hover': { opacity: 0.85 } }}>
      <TableCell sx={{ ...cell, fontWeight: itm ? 800 : 400, color: c.type === 'call' ? green : red }}>
        {c.strike.toFixed(2)}
      </TableCell>
      <TableCell sx={cell}>{c.last.toFixed(2)}</TableCell>
      <TableCell sx={cell}>{c.bid.toFixed(2)}</TableCell>
      <TableCell sx={cell}>{c.ask.toFixed(2)}</TableCell>
      <TableCell sx={{ ...cell, color: c.change_pct >= 0 ? green : red }}>
        {c.change_pct >= 0 ? '+' : ''}{c.change_pct.toFixed(2)}%
      </TableCell>
      <TableCell sx={cell}>{c.volume.toLocaleString()}</TableCell>
      <TableCell sx={cell}>{c.open_interest.toLocaleString()}</TableCell>
      <TableCell sx={{ ...cell, fontFamily: 'monospace' }}>{c.implied_vol.toFixed(1)}%</TableCell>
      <TableCell sx={{ ...cell, fontFamily: 'monospace', color: deltaColor, opacity: 0.85 }}>
        {c.delta.toFixed(3)}
      </TableCell>
      <TableCell sx={{ ...cell, fontFamily: 'monospace', opacity: 0.55 }}>
        {c.theta.toFixed(4)}
      </TableCell>
    </TableRow>
  );
}

function ChainTable({ rows, isDark }: { rows: OptionContract[]; isDark: boolean }) {
  return (
    <Box sx={{ overflowX: 'auto', maxHeight: 320, overflowY: 'auto' }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            {HEADERS.map(h => (
              <TableCell
                key={h}
                sx={{
                  ...cell, fontWeight: 700, opacity: 0.5,
                  fontSize: '0.6rem', letterSpacing: '0.05em',
                  background: (theme) => theme.palette.background.default,
                }}
              >
                {h}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((c, i) => <ContractRow key={i} c={c} isDark={isDark} />)}
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={HEADERS.length} sx={{ textAlign: 'center', opacity: 0.4, fontSize: '0.7rem' }}>
                No contracts
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Box>
  );
}

function StatsBar({ stats, isDark }: { stats: NonNullable<OptionsChainResult['stats']>; isDark: boolean }) {
  const green = isDark ? '#00ffa3' : '#16a34a';
  const red   = isDark ? '#ff0055' : '#dc2626';
  const grey  = isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.6)';
  // Put/Call ratio: green ≤ 0.7 (bullish), grey 0.7–1.0, red ≥ 1.0 (bearish).
  const pcr      = stats.put_call_ratio;
  const pcrColor = pcr <= 0.7 ? green : pcr >= 1.0 ? red : grey;

  const item = (label: string, value: string, color?: string) => (
    <Stack direction="row" spacing={0.5} alignItems="baseline">
      <Typography sx={{ fontSize: '0.6rem', opacity: 0.5 }}>{label}:</Typography>
      <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: color ?? 'text.primary', fontFamily: 'monospace' }}>
        {value}
      </Typography>
    </Stack>
  );

  return (
    <Stack
      direction="row" flexWrap="wrap" alignItems="center"
      divider={<Box sx={{ opacity: 0.2, mx: 0.5 }}>|</Box>}
      sx={{ mb: 1.5, gap: 1, rowGap: 0.5 }}
    >
      {item('Put/Call Ratio', pcr.toFixed(2), pcrColor)}
      {item('IV Calls', `${stats.iv_avg_calls.toFixed(1)}%`)}
      {item('IV Puts', `${stats.iv_avg_puts.toFixed(1)}%`)}
      {item('IV Skew', `${stats.iv_skew >= 0 ? '+' : ''}${stats.iv_skew.toFixed(1)}%`,
        stats.iv_skew >= 0 ? red : green)}
    </Stack>
  );
}

export default function OptionsChainPanel({ symbol, data, isDark, primaryColor, onExpiryChange }: Props) {
  const [fetched, setFetched]   = useState<OptionsChainResult | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error,   setError]     = useState<string | null>(null);
  const [view,    setView]      = useState<View>('both');

  // data prop wins (analysis tab). Otherwise use the internally-fetched chain.
  const selfFetch = !data && !!symbol;
  const chain     = data ?? fetched;

  const load = useCallback(async (sym: string, expiry?: string) => {
    setLoading(true);
    setError(null);
    try {
      const qs  = expiry ? `?expiry=${encodeURIComponent(expiry)}` : '';
      const res = await fetch(`/api/options/${encodeURIComponent(sym)}${qs}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: OptionsChainResult = await res.json();
      setFetched(json);
    } catch {
      setFetched(null);
      setError('Could not load options chain.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch when the symbol changes (self-fetch mode only).
  useEffect(() => {
    if (selfFetch && symbol) load(symbol);
  }, [selfFetch, symbol, load]);

  const handleExpiryChange = (expiry: string) => {
    if (selfFetch && symbol) {
      load(symbol, expiry);
    } else {
      onExpiryChange?.(expiry);
    }
  };

  if (selfFetch && loading && !chain) {
    return (
      <Card>
        <CardContent sx={{ p: '16px !important', display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress size={28} />
        </CardContent>
      </Card>
    );
  }

  if (selfFetch && error && !chain) {
    return (
      <Card>
        <CardContent sx={{ p: '16px !important' }}>
          <Typography sx={{ fontSize: '0.8rem', opacity: 0.6 }}>{error}</Typography>
        </CardContent>
      </Card>
    );
  }

  if (!chain) return null;

  return (
    <Card>
      <CardContent sx={{ p: '16px !important' }}>
        {/* Header */}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Activity size={16} color={primaryColor} />
            <Typography variant="overline" sx={{ opacity: 0.5, lineHeight: 1 }}>
              Options Chain
            </Typography>
            {loading && <CircularProgress size={12} />}
          </Stack>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Chip
              label={`$${chain.current_price.toFixed(2)}`}
              size="small"
              sx={{
                fontSize: '0.62rem', fontWeight: 700,
                background: `${primaryColor}18`, color: primaryColor,
                border: `1px solid ${primaryColor}44`,
              }}
            />
            <Select
              value={chain.expiry}
              size="small"
              onChange={e => handleExpiryChange(e.target.value)}
              sx={{ fontSize: '0.65rem', height: 26, '.MuiSelect-select': { py: 0.25, px: 1 } }}
            >
              {chain.expirations.map(exp => (
                <MenuItem key={exp} value={exp} sx={{ fontSize: '0.65rem' }}>{exp}</MenuItem>
              ))}
            </Select>
          </Stack>
        </Stack>

        {/* Aggregate stats */}
        {chain.stats && <StatsBar stats={chain.stats} isDark={isDark} />}

        {/* View toggle */}
        <ToggleButtonGroup
          value={view}
          exclusive
          size="small"
          onChange={(_, v: View | null) => v && setView(v)}
          sx={{ mb: 1.5, '& .MuiToggleButton-root': { fontSize: '0.65rem', py: 0.25, px: 1.5, textTransform: 'none' } }}
        >
          <ToggleButton value="both">Both</ToggleButton>
          <ToggleButton value="calls">Calls ({chain.calls.length})</ToggleButton>
          <ToggleButton value="puts">Puts ({chain.puts.length})</ToggleButton>
        </ToggleButtonGroup>

        {/* Tables — Both shows calls stacked above puts */}
        {(view === 'both' || view === 'calls') && (
          <>
            {view === 'both' && (
              <Typography sx={{ fontSize: '0.62rem', fontWeight: 700, opacity: 0.5, letterSpacing: '0.06em', mb: 0.5 }}>
                CALLS
              </Typography>
            )}
            <ChainTable rows={chain.calls} isDark={isDark} />
          </>
        )}
        {(view === 'both' || view === 'puts') && (
          <>
            {view === 'both' && (
              <Typography sx={{ fontSize: '0.62rem', fontWeight: 700, opacity: 0.5, letterSpacing: '0.06em', mt: 1.5, mb: 0.5 }}>
                PUTS
              </Typography>
            )}
            <ChainTable rows={chain.puts} isDark={isDark} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
