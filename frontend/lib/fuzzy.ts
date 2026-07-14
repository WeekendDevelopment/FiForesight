/**
 * Tiny dependency-free fuzzy matcher for the command palette (Feature 33).
 *
 * Ranking tiers (higher = better):
 *   3 — text starts with the query            ("aap" → "AAPL")
 *   2 — some word in the text starts with it  ("pla" → "Meta Platforms")
 *   1 — query is a subsequence of the text    ("amzn" → "Amazon.com")
 *   0 — no match
 *
 * Pure functions, case-insensitive, no allocation-heavy scoring — callers
 * combine tiers however they like (e.g. weight symbol matches over names).
 */

export type MatchTier = 0 | 1 | 2 | 3;

/** True when every char of `query` appears in `text` in order. */
export function isSubsequence(query: string, text: string): boolean {
  let qi = 0;
  for (let ti = 0; ti < text.length && qi < query.length; ti++) {
    if (text[ti] === query[qi]) qi++;
  }
  return qi === query.length;
}

/** Rank how well `query` matches `text` (both compared case-insensitively). */
export function matchTier(query: string, text: string): MatchTier {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (!q || !t) return 0;
  if (t.startsWith(q)) return 3;
  if (t.split(/[\s\-./]+/).some(word => word.startsWith(q))) return 2;
  if (isSubsequence(q, t)) return 1;
  return 0;
}

/**
 * Filter + rank `items` by `score` descending (0 drops the item).
 * Array.prototype.sort is stable, so equal scores keep input order.
 */
export function rankBy<T>(items: readonly T[], score: (item: T) => number): T[] {
  return items
    .map(item => ({ item, s: score(item) }))
    .filter(({ s }) => s > 0)
    .sort((a, b) => b.s - a.s)
    .map(({ item }) => item);
}
