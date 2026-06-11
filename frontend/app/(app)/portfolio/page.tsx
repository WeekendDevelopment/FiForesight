'use client';

/*
 * "My Portfolio" tab (Feature 10 — Portfolio Manager).
 *
 * Tracks the user's REAL holdings with live P&L, sector allocation, a
 * diversification score, and a portfolio-level forecast. This is distinct from
 * the "Simulator" tab (/simulation), which is a backtest race against the S&P.
 *
 * Auth-gated: signed-out users see an AuthGate. All data flows through
 * lib/holdings.ts → /api/portfolio/* proxies → FastAPI (RLS-scoped by JWT).
 *
 * Out of scope (v1): stock splits, dividends, multi-currency. Cost basis is
 * shown exactly as the user entered it.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Box, Paper, Stack, Typography, Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Button, IconButton, Skeleton, Chip, Tooltip, useMediaQuery, Alert,
} from '@mui/material';
import {
  Wallet, Plus, Trash2, TrendingUp, TrendingDown, Minus, ShieldCheck,
} from 'lucide-react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RTooltip,
} from 'recharts';
import AuthGate from '../../../components/AuthGate';
import AuthModal from '../../../components/AuthModal';
import { useAuth } from '../../../contexts/AuthContext';
import { useAppShell } from '../../../contexts/AppShellContext';
import { fetchPortfolioSummary, addHolding, removeHolding } from '../../../lib/holdings';
import type { PortfolioSummary } from '../../../types';

const SECTOR_COLORS = [
  '#f92aad', '#2ad8f9', '#9b5cf9', '#f9b32a', '#2af98f',
  '#f9572a', '#5c8cf9', '#f92a5c', '#2af9d8', '#c0c0c0',
];

const usd = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
const pct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;

export default function PortfolioPage() {
  const router = useRouter();
  const { user, session } = useAuth();
  const { isDark, primaryColor } = useAppShell();
  const isMobile = useMediaQuery('(max-width:899.95px)');

  const token = session?.access_token ?? '';

  const [summary,   setSummary]   = useState<PortfolioSummary | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [authOpen,  setAuthOpen]  = useState(false);

  // Add-holding form
  const [symbol,    setSymbol]    = useState('');
  const [shares,    setShares]    = useState('');
  const [costBasis, setCostBasis] = useState('');
  const [adding,    setAdding]    = useState(false);
  const [deleting,  setDeleting]  = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPortfolioSummary(token, refresh);
      setSummary(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load your portfolio.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { if (token) load(false); }, [token, load]);

  const handleAdd = async () => {
    const s = symbol.trim().toUpperCase();
    const sh = Number(shares);
    const cb = Number(costBasis);
    if (!s || !Number.isFinite(sh) || sh <= 0 || !Number.isFinite(cb) || cb < 0) {
      setError('Enter a valid symbol, shares > 0, and cost basis ≥ 0.');
      return;
    }
    setAdding(true);
    setError(null);
    try {
      await addHolding(token, s, sh, cb);
      setSymbol(''); setShares(''); setCostBasis('');
      await load(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add holding.');
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeleting(id);
    try {
      await removeHolding(token, id);
      await load(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete holding.');
    } finally {
      setDeleting(null);
    }
  };

  const pieData = useMemo(
    () => (summary?.sectorAllocation ?? []).map(s => ({ name: s.sector, value: s.weightPct })),
    [summary],
  );

  // ── Signed-out gate ────────────────────────────────────────────────────────
  if (!user) {
    return (
      <Box sx={{ maxWidth: 560, mx: 'auto', mt: 6 }}>
        <Header />
        <AuthGate
          title="My Portfolio"
          message="Sign in to track your real holdings, live P&L, and portfolio forecast."
          onSignIn={() => setAuthOpen(true)}
          isDark={isDark}
          primaryColor={primaryColor}
        />
        <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
      </Box>
    );
  }

  const holdings = summary?.holdings ?? [];
  const border = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const pnlColor = (n: number) => (n > 0 ? '#2af98f' : n < 0 ? '#f9572a' : 'text.secondary');

  return (
    <Box sx={{ maxWidth: 1100, mx: 'auto' }}>
      <Header />

      {error && <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}

      {/* Summary cards */}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
        <SummaryCard label="Total Value" border={border}
          value={loading && !summary ? null : usd(summary?.totalMarketValue ?? 0)} />
        <SummaryCard label="Total P&L" border={border}
          value={loading && !summary ? null : usd(summary?.totalPnl ?? 0)}
          sub={summary ? pct(summary.totalPnlPct) : undefined}
          color={summary ? pnlColor(summary.totalPnl) : undefined} />
        <SummaryCard label="Diversification" border={border}
          value={loading && !summary ? null : `${summary?.diversificationScore ?? 0}/100`}
          icon={<ShieldCheck size={16} color={primaryColor} />} />
        <ForecastCard border={border} forecast={summary?.forecast} loading={loading && !summary} />
      </Stack>

      {/* Add holding */}
      <Paper sx={{ p: 2, mb: 3, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'flex-end' }}>
          <TextField label="Symbol" size="small" value={symbol}
            onChange={e => setSymbol(e.target.value.toUpperCase())}
            inputProps={{ maxLength: 15 }} sx={{ width: { xs: '100%', sm: 140 } }} />
          <TextField label="Shares" size="small" type="number" value={shares}
            onChange={e => setShares(e.target.value)} sx={{ width: { xs: '100%', sm: 130 } }} />
          <TextField label="Cost basis ($)" size="small" type="number" value={costBasis}
            onChange={e => setCostBasis(e.target.value)} sx={{ width: { xs: '100%', sm: 150 } }} />
          <Button variant="contained" startIcon={<Plus size={16} />} onClick={handleAdd}
            disabled={adding} sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
            {adding ? 'Adding…' : 'Add holding'}
          </Button>
        </Stack>
      </Paper>

      {/* Body: table + sector pie */}
      {loading && !summary ? (
        <TableSkeleton border={border} />
      ) : holdings.length === 0 ? (
        <EmptyState border={border} />
      ) : (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
          {/* Holdings table */}
          <Paper sx={{ flex: 1, border: `1px solid ${border}`, borderRadius: 3, overflow: 'hidden', background: 'transparent' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  {!isMobile && <TableCell align="right">Shares</TableCell>}
                  {!isMobile && <TableCell align="right">Cost</TableCell>}
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Value</TableCell>
                  <TableCell align="right">P&L</TableCell>
                  {!isMobile && <TableCell align="right">Weight</TableCell>}
                  {!isMobile && <TableCell>Sector</TableCell>}
                  <TableCell align="right" />
                </TableRow>
              </TableHead>
              <TableBody>
                {holdings.map(h => (
                  <TableRow key={h.id} hover sx={{ cursor: 'pointer', '&:last-child td': { border: 0 } }}
                    onClick={() => router.push(`/analysis?symbol=${encodeURIComponent(h.symbol)}`)}>
                    <TableCell>
                      <Typography sx={{ fontWeight: 700, fontSize: 13 }}>{h.symbol}</Typography>
                      {!isMobile && <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: 130, display: 'block' }}>{h.name}</Typography>}
                    </TableCell>
                    {!isMobile && <TableCell align="right">{h.shares}</TableCell>}
                    {!isMobile && <TableCell align="right">{usd(h.costBasis)}</TableCell>}
                    <TableCell align="right">{usd(h.price)}</TableCell>
                    <TableCell align="right">{usd(h.marketValue)}</TableCell>
                    <TableCell align="right" sx={{ color: pnlColor(h.pnl), fontWeight: 600 }}>
                      {usd(h.pnl)}<br />
                      <Typography component="span" variant="caption" sx={{ color: pnlColor(h.pnl) }}>{pct(h.pnlPct)}</Typography>
                    </TableCell>
                    {!isMobile && <TableCell align="right">{h.weightPct.toFixed(1)}%</TableCell>}
                    {!isMobile && <TableCell><Chip size="small" label={h.sector} variant="outlined" sx={{ fontSize: 10 }} /></TableCell>}
                    <TableCell align="right" onClick={e => e.stopPropagation()}>
                      <Tooltip title="Remove holding">
                        <span>
                          <IconButton size="small" disabled={deleting === h.id} onClick={() => handleDelete(h.id)} aria-label={`Remove ${h.symbol}`}>
                            <Trash2 size={15} />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {summary && summary.skipped.length > 0 && (
              <Typography variant="caption" color="text.secondary" sx={{ p: 1.5, display: 'block' }}>
                Live data unavailable for: {summary.skipped.join(', ')} — excluded from totals.
              </Typography>
            )}
          </Paper>

          {/* Sector allocation pie */}
          <Paper sx={{ width: { xs: '100%', md: 300 }, flexShrink: 0, p: 2, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
            <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>Sector Allocation</Typography>
            <Box sx={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={80} paddingAngle={2}>
                    {pieData.map((_, i) => <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />)}
                  </Pie>
                  <RTooltip formatter={(v: number) => `${v.toFixed(1)}%`} contentStyle={{ background: isDark ? '#1a1a2e' : '#fff', border: `1px solid ${border}`, borderRadius: 8 }} />
                </PieChart>
              </ResponsiveContainer>
            </Box>
            <Stack spacing={0.5} sx={{ mt: 1 }}>
              {(summary?.sectorAllocation ?? []).map((s, i) => (
                <Stack key={s.sector} direction="row" alignItems="center" justifyContent="space-between">
                  <Stack direction="row" alignItems="center" spacing={0.75}>
                    <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: SECTOR_COLORS[i % SECTOR_COLORS.length] }} />
                    <Typography variant="caption">{s.sector}</Typography>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">{s.weightPct.toFixed(1)}%</Typography>
                </Stack>
              ))}
            </Stack>
          </Paper>
        </Stack>
      )}

      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
    </Box>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Header() {
  const { primaryColor } = useAppShell();
  return (
    <Stack direction="row" alignItems="center" spacing={1.25} sx={{ mb: 0.5 }}>
      <Wallet size={26} color={primaryColor} />
      <Typography variant="h5" fontWeight={800} letterSpacing="-0.02em">My Portfolio</Typography>
    </Stack>
  );
}

function SummaryCard({ label, value, sub, color, icon, border }: {
  label: string; value: string | null; sub?: string; color?: string; icon?: React.ReactNode; border: string;
}) {
  return (
    <Paper sx={{ flex: 1, p: 2, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.5 }}>
        {icon}
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Typography>
      </Stack>
      {value === null
        ? <Skeleton width={100} height={32} />
        : <Typography variant="h6" fontWeight={800} sx={{ color: color ?? 'text.primary' }}>{value}</Typography>}
      {sub && <Typography variant="caption" sx={{ color: color ?? 'text.secondary' }}>{sub}</Typography>}
    </Paper>
  );
}

function ForecastCard({ forecast, loading, border }: {
  forecast?: PortfolioSummary['forecast']; loading: boolean; border: string;
}) {
  const label = forecast?.label ?? 'Neutral';
  const color = label === 'Bullish' ? '#2af98f' : label === 'Bearish' ? '#f9572a' : '#c0c0c0';
  const Icon  = label === 'Bullish' ? TrendingUp : label === 'Bearish' ? TrendingDown : Minus;
  return (
    <Paper sx={{ flex: 1, p: 2, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 0.5 }}>
        Portfolio Forecast
      </Typography>
      {loading
        ? <Skeleton width={100} height={32} />
        : (
          <Stack direction="row" alignItems="center" spacing={0.75}>
            <Icon size={20} color={color} />
            <Typography variant="h6" fontWeight={800} sx={{ color }}>{label}</Typography>
          </Stack>
        )}
    </Paper>
  );
}

function EmptyState({ border }: { border: string }) {
  return (
    <Paper sx={{ p: 6, textAlign: 'center', border: `1px dashed ${border}`, borderRadius: 3, background: 'transparent' }}>
      <Wallet size={32} style={{ opacity: 0.3 }} />
      <Typography variant="subtitle1" fontWeight={700} sx={{ mt: 1 }}>Add your first holding to start tracking P&L</Typography>
      <Typography variant="body2" color="text.secondary">
        Enter a symbol, share count, and your cost basis above.
      </Typography>
    </Paper>
  );
}

function TableSkeleton({ border }: { border: string }) {
  return (
    <Paper sx={{ p: 2, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} height={44} sx={{ mb: 0.5 }} />
      ))}
    </Paper>
  );
}
