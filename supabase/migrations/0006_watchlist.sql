-- Feature 13: Watchlist Persistence
-- Creates the watchlists table with RLS so each user only sees their own rows.
-- Apply this migration in the Supabase SQL editor (Dashboard → SQL Editor → New query).

create table if not exists watchlists (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  symbol     text not null,
  added_at   timestamptz default now(),
  unique(user_id, symbol)
);

alter table watchlists enable row level security;

create policy "users manage own watchlist"
  on watchlists for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
