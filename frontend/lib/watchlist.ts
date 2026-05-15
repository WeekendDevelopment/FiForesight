/*
 * Supabase watchlist helpers.
 *
 * Required table (run once in Supabase SQL editor):
 *
 *   create table watchlist (
 *     id         uuid default gen_random_uuid() primary key,
 *     user_id    uuid references auth.users(id) on delete cascade not null,
 *     symbol     text not null,
 *     created_at timestamptz default now(),
 *     unique(user_id, symbol)
 *   );
 *   alter table watchlist enable row level security;
 *   create policy "own rows" on watchlist using (auth.uid() = user_id)
 *     with check (auth.uid() = user_id);
 */
import { supabase } from './supabase';

export async function fetchWatchlist(userId: string): Promise<string[]> {
  const { data, error } = await supabase
    .from('watchlist')
    .select('symbol')
    .eq('user_id', userId)
    .order('created_at', { ascending: false });
  if (error) throw error;
  return (data ?? []).map((r: { symbol: string }) => r.symbol);
}

export async function addToWatchlist(userId: string, symbol: string): Promise<void> {
  const { error } = await supabase
    .from('watchlist')
    .insert({ user_id: userId, symbol: symbol.toUpperCase() });
  if (error && error.code !== '23505') throw error; // ignore duplicate
}

export async function removeFromWatchlist(userId: string, symbol: string): Promise<void> {
  const { error } = await supabase
    .from('watchlist')
    .delete()
    .eq('user_id', userId)
    .eq('symbol', symbol.toUpperCase());
  if (error) throw error;
}
