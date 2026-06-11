-- Feature 10 — Portfolio Manager: user holdings table.
--
-- Run once in the Supabase SQL editor (or via the Supabase CLI). Mirrors the
-- watchlist table's RLS pattern: every row is owned by a user and Row-Level
-- Security restricts all access to that owner via auth.uid().
--
-- Scope (v1): stock splits, dividends, and multi-currency are NOT handled.
-- cost_basis is stored exactly as the user entered it (per-share, holding's
-- currency). A later migration can add corporate-action adjustment.

create table if not exists public.holdings (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade default auth.uid(),
  symbol     text not null,
  shares     numeric not null check (shares > 0),
  cost_basis numeric not null check (cost_basis >= 0),
  opened_at  timestamptz not null default now(),
  -- One row per (user, symbol) so POST /portfolio/holdings can upsert
  -- (merge-duplicates) instead of creating duplicate positions.
  constraint holdings_user_symbol_unique unique (user_id, symbol)
);

create index if not exists holdings_user_id_idx on public.holdings (user_id);

alter table public.holdings enable row level security;

-- Single "own rows" policy covering select / insert / update / delete.
drop policy if exists "own rows" on public.holdings;
create policy "own rows" on public.holdings
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
