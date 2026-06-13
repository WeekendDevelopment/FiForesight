-- Feature 13: Watchlist Persistence
--
-- Apply in Supabase SQL Editor (Dashboard → SQL Editor → New query).
-- Mirrors the holdings (0001) and alerts (0003) RLS pattern.

create table if not exists public.watchlists (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade default auth.uid(),
  symbol     text not null,
  added_at   timestamptz not null default now(),
  unique(user_id, symbol)
);

create index if not exists watchlists_user_id_idx on public.watchlists (user_id);

alter table public.watchlists enable row level security;

drop policy if exists "users manage own watchlist" on public.watchlists;
create policy "users manage own watchlist"
  on public.watchlists for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- PostgREST requires explicit grants; the authenticated role owns rows via RLS.
grant select, insert, update, delete on table public.watchlists to authenticated;
grant select on table public.watchlists to anon;

-- Reload PostgREST schema cache so the new table is immediately visible.
notify pgrst, 'reload schema';
