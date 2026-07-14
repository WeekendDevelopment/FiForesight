/**
 * Shared ticker suggestion source (Feature 33).
 *
 * Single source of truth for the curated "popular tickers" universe that was
 * previously duplicated inline on the analysis and options pages. Both page
 * Autocompletes AND the command palette import from here — edit the list in
 * this file only.
 */

import { matchTier, rankBy } from './fuzzy';

export interface TickerEntry {
  symbol: string;
  name:   string;
}

export const TICKER_UNIVERSE: TickerEntry[] = [
  { symbol: 'AAPL',    name: 'Apple' },
  { symbol: 'MSFT',    name: 'Microsoft' },
  { symbol: 'GOOGL',   name: 'Alphabet (Google)' },
  { symbol: 'AMZN',    name: 'Amazon' },
  { symbol: 'NVDA',    name: 'NVIDIA' },
  { symbol: 'META',    name: 'Meta Platforms' },
  { symbol: 'TSLA',    name: 'Tesla' },
  { symbol: 'BRK.B',   name: 'Berkshire Hathaway' },
  { symbol: 'JPM',     name: 'JPMorgan Chase' },
  { symbol: 'V',       name: 'Visa' },
  { symbol: 'UNH',     name: 'UnitedHealth Group' },
  { symbol: 'MA',      name: 'Mastercard' },
  { symbol: 'XOM',     name: 'Exxon Mobil' },
  { symbol: 'LLY',     name: 'Eli Lilly' },
  { symbol: 'JNJ',     name: 'Johnson & Johnson' },
  { symbol: 'PG',      name: 'Procter & Gamble' },
  { symbol: 'HD',      name: 'Home Depot' },
  { symbol: 'MRK',     name: 'Merck' },
  { symbol: 'AVGO',    name: 'Broadcom' },
  { symbol: 'CVX',     name: 'Chevron' },
  { symbol: 'KO',      name: 'Coca-Cola' },
  { symbol: 'PEP',     name: 'PepsiCo' },
  { symbol: 'ABBV',    name: 'AbbVie' },
  { symbol: 'COST',    name: 'Costco' },
  { symbol: 'MCD',     name: "McDonald's" },
  { symbol: 'CSCO',    name: 'Cisco Systems' },
  { symbol: 'TMO',     name: 'Thermo Fisher Scientific' },
  { symbol: 'WMT',     name: 'Walmart' },
  { symbol: 'ACN',     name: 'Accenture' },
  { symbol: 'ABT',     name: 'Abbott Laboratories' },
  { symbol: 'AMD',     name: 'Advanced Micro Devices' },
  { symbol: 'NFLX',    name: 'Netflix' },
  { symbol: 'SPY',     name: 'SPDR S&P 500 ETF' },
  { symbol: 'QQQ',     name: 'Invesco QQQ (Nasdaq-100)' },
  { symbol: 'DIA',     name: 'SPDR Dow Jones ETF' },
  { symbol: 'IWM',     name: 'iShares Russell 2000 ETF' },
  { symbol: 'GLD',     name: 'SPDR Gold Shares' },
  { symbol: 'SLV',     name: 'iShares Silver Trust' },
  { symbol: 'TLT',     name: 'iShares 20+ Yr Treasury ETF' },
  { symbol: 'BTC-USD', name: 'Bitcoin' },
  { symbol: 'ETH-USD', name: 'Ethereum' },
];

/** Plain symbol list — the shape the page Autocompletes consume. */
export const POPULAR_TICKERS: string[] = TICKER_UNIVERSE.map(t => t.symbol);

/**
 * Fuzzy-search the universe by symbol + company name.
 * Symbol matches dominate name matches (a symbol prefix always outranks any
 * name-only match); ties keep universe order (stable sort).
 */
export function searchTickers(query: string, cap = 8): TickerEntry[] {
  const q = query.trim();
  if (!q) return [];
  return rankBy(TICKER_UNIVERSE, ({ symbol, name }) =>
    matchTier(q, symbol) * 10 + matchTier(q, name),
  ).slice(0, cap);
}

/** Random entry from the universe — the palette's "Random ticker" action. */
export function randomTicker(): TickerEntry {
  return TICKER_UNIVERSE[Math.floor(Math.random() * TICKER_UNIVERSE.length)];
}

/** A live search hit from GET /api/symbols/search (Yahoo, keyless) — carries
 * the exchange so multi-listing names (BP NYSE vs BP.L London) are pickable. */
export interface SymbolSearchResult extends TickerEntry {
  exchange: string;
  type:     string;
}

/** Anything the /predict symbol validator would accept (sans ":EXCHANGE"). */
export const ANALYZABLE_SYMBOL_RE = /^[A-Za-z0-9.\-]{1,15}$/;

/**
 * Live symbol search across exchanges. Debounce + abort are the caller's job.
 * Resolves [] on any failure so callers can degrade to the static universe.
 */
export async function searchSymbolsRemote(
  query: string,
  signal?: AbortSignal,
): Promise<SymbolSearchResult[]> {
  const q = query.trim();
  if (q.length < 2) return [];
  try {
    const res = await fetch(`/api/symbols/search?q=${encodeURIComponent(q)}`, { signal });
    if (!res.ok) return [];
    const rows = (await res.json()) as unknown;
    return Array.isArray(rows) ? (rows as SymbolSearchResult[]) : [];
  } catch {
    return [];
  }
}
