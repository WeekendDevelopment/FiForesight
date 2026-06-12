-- Feature 9 — Alerts & Notifications: Web Push (VAPID) subscriptions.
--
-- Run once in the Supabase SQL editor (or via the Supabase CLI). One row per
-- browser/device push subscription. The backend sends notifications with
-- `pywebpush` using these credentials + the server VAPID key pair.
--
-- RLS scopes user-facing access to the owner (auth.uid()). The scheduled
-- evaluator reads subscriptions across users via the service-role key (which
-- bypasses RLS) only on the cron-secret-gated delivery path.

create table if not exists public.push_subscriptions (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade default auth.uid(),
  -- The Push Service endpoint URL (unique per subscription). Re-subscribing the
  -- same browser yields the same endpoint, so we upsert on it.
  endpoint   text not null,
  -- Keys from the browser PushSubscription (used to encrypt the payload).
  p256dh     text not null,
  auth       text not null,
  created_at timestamptz not null default now(),
  constraint push_subscriptions_endpoint_unique unique (endpoint)
);

create index if not exists push_subscriptions_user_id_idx on public.push_subscriptions (user_id);

alter table public.push_subscriptions enable row level security;

drop policy if exists "own push subscriptions" on public.push_subscriptions;
create policy "own push subscriptions" on public.push_subscriptions
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
