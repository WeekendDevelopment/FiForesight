'use client';

/*
 * "Alerts" tab (Feature 9 — Alerts & Notifications).
 *
 * Users define alert rules (price cross, RSI threshold, % move, earnings soon,
 * forecast breakout). A scheduled backend evaluator checks them against live
 * data and notifies via Web Push (+ optional email). This page is the rule
 * builder + active-rules manager + fire history + the "enable notifications"
 * subscription flow.
 *
 * Auth-gated: signed-out users see an AuthGate. All data flows through
 * lib/alerts.ts → /api/alerts/* proxies → FastAPI (RLS-scoped by JWT).
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Box, Paper, Stack, Typography, TextField, Button, IconButton, Skeleton,
  Chip, Tooltip, Switch, Alert, Select, MenuItem, FormControl, InputLabel,
  Divider,
} from '@mui/material';
import { Bell, BellRing, Plus, Trash2, Clock } from 'lucide-react';
import AuthGate from '../../../components/AuthGate';
import AuthModal from '../../../components/AuthModal';
import { useAuth } from '../../../contexts/AuthContext';
import { useAppShell } from '../../../contexts/AppShellContext';
import {
  fetchRules, createRule, setRuleActive, deleteRule, fetchFires,
  enablePushNotifications, isPushSubscribed, pushSupported, type NewRule,
} from '../../../lib/alerts';
import type { AlertRule, AlertRuleType, AlertFire } from '../../../types';

interface RuleTypeMeta { value: AlertRuleType; label: string; help: string }

const RULE_TYPES: RuleTypeMeta[] = [
  { value: 'price_cross',       label: 'Price cross',       help: 'Fires when the live price crosses your level.' },
  { value: 'rsi_threshold',     label: 'RSI threshold',     help: 'Fires when 14-period RSI crosses a level (0–100).' },
  { value: 'pct_move',          label: '% move today',      help: "Fires when today's move exceeds your percentage." },
  { value: 'earnings_soon',     label: 'Earnings soon',     help: 'Fires when earnings are within N days.' },
  { value: 'forecast_breakout', label: 'Forecast breakout', help: 'Fires when price breaks the latest forecast band.' },
];

function describeRule(r: AlertRule): string {
  switch (r.type) {
    case 'price_cross':       return `Price ${r.operator} $${r.threshold}`;
    case 'rsi_threshold':     return `RSI ${r.operator} ${r.threshold}`;
    case 'pct_move':
      return r.operator
        ? `Moves ${r.operator === 'above' ? 'up' : 'down'} ≥ ${r.threshold}%`
        : `Moves ≥ ${r.threshold}% (either direction)`;
    case 'earnings_soon':     return `Earnings within ${r.threshold ?? 1} day(s)`;
    case 'forecast_breakout': return 'Breaks the latest forecast band';
    default:                  return r.type;
  }
}

function fmtTime(iso: string): string {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

export default function AlertsPage() {
  const { user, session } = useAuth();
  const { isDark, primaryColor } = useAppShell();
  const token = session?.access_token ?? '';
  const border = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';

  const [rules,   setRules]   = useState<AlertRule[]>([]);
  const [fires,   setFires]   = useState<AlertFire[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [notice,  setNotice]  = useState<string | null>(null);
  const [authOpen, setAuthOpen] = useState(false);

  // Rule builder form
  const [symbol,    setSymbol]    = useState('');
  const [type,      setType]      = useState<AlertRuleType>('price_cross');
  const [operator,  setOperator]  = useState<'' | 'above' | 'below'>('above');
  const [threshold, setThreshold] = useState('');
  const [adding,    setAdding]    = useState(false);
  const [busyId,    setBusyId]    = useState<string | null>(null);

  // Push state
  const [pushOn,   setPushOn]   = useState(false);
  const [pushBusy, setPushBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [r, f] = await Promise.all([fetchRules(token), fetchFires(token)]);
      setRules(r);
      setFires(f);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load your alerts.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { if (token) load(); }, [token, load]);
  useEffect(() => { isPushSubscribed().then(setPushOn).catch(() => {}); }, []);

  // Reset operator sensibly when the rule type changes.
  useEffect(() => {
    if (type === 'price_cross' || type === 'rsi_threshold') setOperator('above');
    else setOperator('');
  }, [type]);

  function buildRule(): NewRule | string {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return 'Enter a symbol.';
    const t = Number(threshold);
    switch (type) {
      case 'price_cross':
        if (operator !== 'above' && operator !== 'below') return 'Choose above or below.';
        if (!Number.isFinite(t) || t <= 0) return 'Enter a price greater than 0.';
        return { symbol: sym, type, operator, threshold: t };
      case 'rsi_threshold':
        if (operator !== 'above' && operator !== 'below') return 'Choose above or below.';
        if (!Number.isFinite(t) || t < 0 || t > 100) return 'RSI must be between 0 and 100.';
        return { symbol: sym, type, operator, threshold: t };
      case 'pct_move':
        if (!Number.isFinite(t) || t <= 0) return 'Enter a percentage greater than 0.';
        return { symbol: sym, type, operator: operator || null, threshold: t };
      case 'earnings_soon': {
        const days = threshold === '' ? 1 : t;
        if (!Number.isFinite(days) || days < 1 || days > 30) return 'Days must be between 1 and 30.';
        return { symbol: sym, type, operator: null, threshold: days };
      }
      case 'forecast_breakout':
        return { symbol: sym, type, operator: null, threshold: null };
      default:
        return 'Unsupported rule type.';
    }
  }

  const handleAdd = async () => {
    const built = buildRule();
    if (typeof built === 'string') { setError(built); return; }
    setAdding(true);
    setError(null);
    try {
      const created = await createRule(token, built);
      setRules(prev => [created, ...prev]);
      setSymbol(''); setThreshold('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create the rule.');
    } finally {
      setAdding(false);
    }
  };

  const handleToggle = async (r: AlertRule) => {
    setBusyId(r.id);
    try {
      const updated = await setRuleActive(token, r.id, !r.active);
      setRules(prev => prev.map(x => (x.id === r.id ? updated : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update the rule.');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id: string) => {
    setBusyId(id);
    try {
      await deleteRule(token, id);
      setRules(prev => prev.filter(x => x.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete the rule.');
    } finally {
      setBusyId(null);
    }
  };

  const handleEnablePush = async () => {
    setPushBusy(true);
    setError(null);
    setNotice(null);
    try {
      await enablePushNotifications(token);
      setPushOn(true);
      setNotice('Browser notifications enabled.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not enable notifications.');
    } finally {
      setPushBusy(false);
    }
  };

  // ── Signed-out gate ────────────────────────────────────────────────────────
  if (!user) {
    return (
      <Box sx={{ maxWidth: 560, mx: 'auto', mt: 6 }}>
        <Header primaryColor={primaryColor} />
        <AuthGate
          title="Alerts & Notifications"
          message="Sign in to create price, RSI, % move, earnings, and forecast-breakout alerts — and get notified by web push."
          onSignIn={() => setAuthOpen(true)}
          isDark={isDark}
          primaryColor={primaryColor}
        />
        <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
      </Box>
    );
  }

  const needsOperatorChoice = type === 'price_cross' || type === 'rsi_threshold' || type === 'pct_move';
  const showThreshold = type !== 'forecast_breakout';
  const thresholdLabel =
    type === 'price_cross' ? 'Price' :
    type === 'rsi_threshold' ? 'RSI (0–100)' :
    type === 'pct_move' ? 'Percent' :
    type === 'earnings_soon' ? 'Within days' : '';

  return (
    <Box sx={{ maxWidth: 980, mx: 'auto' }}>
      <Header primaryColor={primaryColor} />

      {error  && <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
      {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice(null)}>{notice}</Alert>}

      {/* Notifications enable banner */}
      <Paper sx={{ p: 2, mb: 3, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} alignItems={{ sm: 'center' }} justifyContent="space-between" spacing={1.5}>
          <Stack direction="row" alignItems="center" spacing={1.25}>
            {pushOn ? <BellRing size={20} color={primaryColor} /> : <Bell size={20} color={primaryColor} />}
            <Box>
              <Typography sx={{ fontWeight: 700, fontSize: 14 }}>
                {pushOn ? 'Browser notifications are on' : 'Enable browser notifications'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {pushSupported()
                  ? 'Get a web push when one of your rules fires — even when the tab is closed.'
                  : 'This browser does not support web push notifications.'}
              </Typography>
            </Box>
          </Stack>
          <Button
            variant={pushOn ? 'outlined' : 'contained'}
            disabled={!pushSupported() || pushBusy || pushOn}
            onClick={handleEnablePush}
            sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}
          >
            {pushOn ? 'Enabled' : pushBusy ? 'Enabling…' : 'Enable'}
          </Button>
        </Stack>
      </Paper>

      {/* Rule builder */}
      <Paper sx={{ p: 2, mb: 3, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
        <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>New alert rule</Typography>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'flex-end' }} flexWrap="wrap">
          <TextField
            label="Symbol" size="small" value={symbol}
            onChange={e => setSymbol(e.target.value.toUpperCase())}
            inputProps={{ maxLength: 15 }} sx={{ width: { xs: '100%', md: 120 } }}
          />
          <FormControl size="small" sx={{ width: { xs: '100%', md: 180 } }}>
            <InputLabel>Type</InputLabel>
            <Select value={type} label="Type" onChange={e => setType(e.target.value as AlertRuleType)}>
              {RULE_TYPES.map(rt => <MenuItem key={rt.value} value={rt.value}>{rt.label}</MenuItem>)}
            </Select>
          </FormControl>

          {needsOperatorChoice && (
            <FormControl size="small" sx={{ width: { xs: '100%', md: 140 } }}>
              <InputLabel>{type === 'pct_move' ? 'Direction' : 'Condition'}</InputLabel>
              <Select
                value={operator}
                label={type === 'pct_move' ? 'Direction' : 'Condition'}
                onChange={e => setOperator(e.target.value as '' | 'above' | 'below')}
              >
                {type === 'pct_move' ? (
                  [
                    <MenuItem key="any"   value="">Either way</MenuItem>,
                    <MenuItem key="up"    value="above">Up</MenuItem>,
                    <MenuItem key="down"  value="below">Down</MenuItem>,
                  ]
                ) : (
                  [
                    <MenuItem key="above" value="above">Above</MenuItem>,
                    <MenuItem key="below" value="below">Below</MenuItem>,
                  ]
                )}
              </Select>
            </FormControl>
          )}

          {showThreshold && (
            <TextField
              label={thresholdLabel} size="small" type="number" value={threshold}
              onChange={e => setThreshold(e.target.value)}
              placeholder={type === 'earnings_soon' ? '1' : undefined}
              sx={{ width: { xs: '100%', md: 140 } }}
            />
          )}

          <Button
            variant="contained" startIcon={<Plus size={16} />} onClick={handleAdd}
            disabled={adding} sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}
          >
            {adding ? 'Adding…' : 'Add rule'}
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          {RULE_TYPES.find(rt => rt.value === type)?.help}
        </Typography>
      </Paper>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
        {/* Active rules */}
        <Paper sx={{ flex: 1, p: 2, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>Your rules</Typography>
          {loading && rules.length === 0 ? (
            <Stack spacing={1}>{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} height={56} />)}</Stack>
          ) : rules.length === 0 ? (
            <EmptyState
              icon={<Bell size={28} style={{ opacity: 0.3 }} />}
              title="No alert rules yet"
              body="Add your first rule above to start getting notified."
              border={border}
            />
          ) : (
            <Stack divider={<Divider flexItem />} spacing={0}>
              {rules.map(r => (
                <Stack key={r.id} direction="row" alignItems="center" justifyContent="space-between" sx={{ py: 1.25 }}>
                  <Stack direction="row" alignItems="center" spacing={1.25} sx={{ minWidth: 0 }}>
                    <Chip size="small" label={r.symbol} sx={{ fontWeight: 700, fontSize: 11 }} />
                    <Box sx={{ minWidth: 0 }}>
                      <Typography sx={{ fontSize: 13, fontWeight: 600 }} noWrap>{describeRule(r)}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {RULE_TYPES.find(rt => rt.value === r.type)?.label}
                        {r.last_fired ? ` · last fired ${fmtTime(r.last_fired)}` : ''}
                      </Typography>
                    </Box>
                  </Stack>
                  <Stack direction="row" alignItems="center" spacing={0.5}>
                    <Tooltip title={r.active ? 'Active — pause' : 'Paused — activate'}>
                      <span>
                        <Switch
                          size="small" checked={r.active} disabled={busyId === r.id}
                          onChange={() => handleToggle(r)}
                        />
                      </span>
                    </Tooltip>
                    <Tooltip title="Delete rule">
                      <span>
                        <IconButton
                          size="small" color="error" disabled={busyId === r.id}
                          onClick={() => handleDelete(r.id)} aria-label={`Delete ${r.symbol} rule`}
                        >
                          <Trash2 size={16} />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Stack>
                </Stack>
              ))}
            </Stack>
          )}
        </Paper>

        {/* Fire history */}
        <Paper sx={{ width: { xs: '100%', md: 340 }, flexShrink: 0, p: 2, border: `1px solid ${border}`, borderRadius: 3, background: 'transparent' }}>
          <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 1.5 }}>
            <Clock size={16} color={primaryColor} />
            <Typography variant="subtitle2" fontWeight={700}>Recent fires</Typography>
          </Stack>
          {loading && fires.length === 0 ? (
            <Stack spacing={1}>{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} height={48} />)}</Stack>
          ) : fires.length === 0 ? (
            <EmptyState
              icon={<Clock size={28} style={{ opacity: 0.3 }} />}
              title="No fires yet"
              body="When a rule triggers, it shows up here."
              border={border}
            />
          ) : (
            <Stack divider={<Divider flexItem />} spacing={0}>
              {fires.map(f => (
                <Box key={f.id} sx={{ py: 1.1 }}>
                  <Typography sx={{ fontSize: 13 }}>{f.message}</Typography>
                  <Typography variant="caption" color="text.secondary">{fmtTime(f.fired_at)}</Typography>
                </Box>
              ))}
            </Stack>
          )}
        </Paper>
      </Stack>

      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
    </Box>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Header({ primaryColor }: { primaryColor: string }) {
  return (
    <Stack direction="row" alignItems="center" spacing={1.25} sx={{ mb: 2 }}>
      <Bell size={26} color={primaryColor} />
      <Typography variant="h5" fontWeight={800} letterSpacing="-0.02em">Alerts</Typography>
    </Stack>
  );
}

function EmptyState({ icon, title, body, border }: {
  icon: React.ReactNode; title: string; body: string; border: string;
}) {
  return (
    <Box sx={{ p: 3, textAlign: 'center', border: `1px dashed ${border}`, borderRadius: 3 }}>
      {icon}
      <Typography variant="subtitle2" fontWeight={700} sx={{ mt: 1 }}>{title}</Typography>
      <Typography variant="caption" color="text.secondary">{body}</Typography>
    </Box>
  );
}
