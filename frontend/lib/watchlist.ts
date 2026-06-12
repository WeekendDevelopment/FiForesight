/*
 * Watchlist client (Feature 13).
 *
 * Routes through the Next.js /api/watchlist proxies → FastAPI backend, which
 * reads/writes the Supabase `watchlists` table via PostgREST using the caller's
 * own JWT. Supabase RLS enforces per-user ownership — no service-role key needed.
 *
 * Migration: supabase/migrations/0006_watchlist.sql
 */
import type { WatchlistItem } from '../types';

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

async function parseOrThrow(res: Response): Promise<unknown> {
  let body: unknown = null;
  try { body = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = (body as { detail?: string } | null)?.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return body;
}

export async function fetchWatchlist(token: string): Promise<WatchlistItem[]> {
  const res  = await fetch('/api/watchlist', { headers: authHeaders(token) });
  const body = await parseOrThrow(res) as { watchlist?: WatchlistItem[] };
  return body.watchlist ?? [];
}

export async function addToWatchlist(token: string, symbol: string): Promise<WatchlistItem> {
  const res  = await fetch('/api/watchlist', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body:    JSON.stringify({ symbol: symbol.toUpperCase() }),
  });
  const body = await parseOrThrow(res) as { item?: WatchlistItem };
  if (!body.item) throw new Error('Malformed response: missing item.');
  return body.item;
}

export async function removeFromWatchlist(token: string, symbol: string): Promise<void> {
  const res = await fetch(`/api/watchlist/${encodeURIComponent(symbol.toUpperCase())}`, {
    method:  'DELETE',
    headers: authHeaders(token),
  });
  if (!res.ok && res.status !== 204) {
    await parseOrThrow(res);
  }
}
