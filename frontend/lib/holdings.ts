/*
 * Portfolio holdings client (Feature 10 — "My Portfolio" tab).
 *
 * Mirrors the shape of lib/watchlist.ts, but routes through the Next.js
 * /api/portfolio proxies → FastAPI backend instead of hitting Supabase
 * directly. The backend re-validates input (F11 symbol regex, shares > 0,
 * cost_basis >= 0) and reads/writes the `holdings` table with the caller's
 * forwarded JWT, so Supabase RLS still enforces per-user ownership.
 *
 * Every call forwards the Supabase access token as a Bearer header; without it
 * the backend returns 401.
 *
 * The Supabase `holdings` table + RLS policy is defined in
 * supabase/migrations/0001_holdings.sql.
 */
import type { Holding, PortfolioSummary } from '../types';

function authHeaders(token: string): HeadersInit {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
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

export async function fetchHoldings(token: string): Promise<Holding[]> {
  const res = await fetch('/api/portfolio/holdings', { headers: authHeaders(token) });
  const body = await parseOrThrow(res) as { holdings?: Holding[] };
  return body.holdings ?? [];
}

export async function addHolding(
  token: string,
  symbol: string,
  shares: number,
  costBasis: number,
): Promise<Holding> {
  const res = await fetch('/api/portfolio/holdings', {
    method:  'POST',
    headers: authHeaders(token),
    body:    JSON.stringify({ symbol: symbol.toUpperCase(), shares, cost_basis: costBasis }),
  });
  const body = await parseOrThrow(res) as { holding?: Holding };
  if (!body.holding) throw new Error('Malformed response: missing holding.');
  return body.holding;
}

export async function removeHolding(token: string, id: string): Promise<void> {
  const res = await fetch(`/api/portfolio/holdings/${encodeURIComponent(id)}`, {
    method:  'DELETE',
    headers: authHeaders(token),
  });
  await parseOrThrow(res);
}

export async function fetchPortfolioSummary(
  token: string,
  refresh = false,
): Promise<PortfolioSummary> {
  const qs = refresh ? '?refresh=true' : '';
  const res = await fetch(`/api/portfolio/summary${qs}`, { headers: authHeaders(token) });
  const body = await parseOrThrow(res) as Partial<PortfolioSummary>;
  if (!Array.isArray(body.holdings)) throw new Error('Malformed portfolio summary response.');
  return body as PortfolioSummary;
}
