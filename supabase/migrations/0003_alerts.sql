-- Feature 9 — Alerts & Notifications: user-defined alert rules + fire history.
--
-- Run once in the Supabase SQL editor (or via the Supabase CLI). Mirrors the
-- holdings table's RLS pattern (migration 0001): every row is owned by a user
-- and Row-Level Security restricts all *user-facing* access to that owner via
-- auth.uid().
--
-- IMPORTANT — the scheduled evaluator (backend/alerts_evaluator.py) reads active
-- rules ACROSS all users and writes fires on their behalf. It does this with the
-- Supabase service-role key, which bypasses RLS. That key is used ONLY by the
-- cron-secret-gated evaluator path, never by a user-facing request handler.

-- ── alert_rules ──────────────────────────────────────────────────────────────
create table if not exists public.alert_rules (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade default auth.uid(),
  symbol     text not null,
  -- Rule type. Drives which live signal the evaluator compares against.
  --   price_cross       — live price above/below `threshold`
  --   rsi_threshold     — 14-period RSI above/below `threshold` (0–100)
  --   pct_move          — abs intraday % move vs prev close ≥ `threshold`
  --   earnings_soon     — next earnings date within `threshold` days (default 1)
  --   forecast_breakout — live price breaks the latest ensemble d1 high/low band
  type       text not null check (type in (
    'price_cross', 'rsi_threshold', 'pct_move', 'earnings_soon', 'forecast_breakout'
  )),
  -- 'above' | 'below' for price_cross / rsi_threshold; null for the others.
  operator   text check (operator is null or operator in ('above', 'below')),
  -- Comparison value. Optional (earnings_soon / forecast_breakout don't need one).
  threshold  numeric,
  active      boolean     not null default true,
  -- Last time this rule fired — drives the cooldown window (see the evaluator).
  last_fired  timestamptz,
  created_at  timestamptz not null default now()
);

create index if not exists alert_rules_user_id_idx on public.alert_rules (user_id);
-- The evaluator's hot path: "all active rules" (service-role, cross-user).
create index if not exists alert_rules_active_idx on public.alert_rules (active) where active;

alter table public.alert_rules enable row level security;

drop policy if exists "own rules" on public.alert_rules;
create policy "own rules" on public.alert_rules
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── alert_fires ──────────────────────────────────────────────────────────────
-- Append-only log of every time a rule fired. user_id is denormalised from the
-- rule so RLS can scope the user's fire history without a join, and so the
-- service-role evaluator can insert rows attributed to the right owner.
create table if not exists public.alert_fires (
  id        uuid primary key default gen_random_uuid(),
  rule_id   uuid not null references public.alert_rules(id) on delete cascade,
  user_id   uuid not null references auth.users(id) on delete cascade default auth.uid(),
  symbol    text not null,
  type      text not null,
  message   text not null,
  value     numeric,
  fired_at  timestamptz not null default now()
);

create index if not exists alert_fires_user_fired_idx on public.alert_fires (user_id, fired_at desc);
create index if not exists alert_fires_rule_idx on public.alert_fires (rule_id);

alter table public.alert_fires enable row level security;

-- Users may read their own fires; inserts are done by the service-role evaluator
-- (which bypasses RLS). A permissive insert policy is still provided so a user
-- could, in principle, record a manual fire under their own id.
drop policy if exists "own fires read" on public.alert_fires;
create policy "own fires read" on public.alert_fires
  for select
  using (auth.uid() = user_id);

drop policy if exists "own fires insert" on public.alert_fires;
create policy "own fires insert" on public.alert_fires
  for insert
  with check (auth.uid() = user_id);
