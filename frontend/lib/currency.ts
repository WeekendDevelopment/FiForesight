// frontend/lib/currency.ts — pure helpers for currency-aware price display (F35).
// Never hardcode '$' on a price: render through formatPrice(value, currency) so
// LSE names quoted in GBp (pence) show "516.50p", not a wrong-by-75× "$516.50".

const SYMBOLS: Record<string, string> = {
  USD: '$', EUR: '€', GBP: '£', JPY: '¥', CAD: 'C$',
  AUD: 'A$', CHF: 'CHF ', INR: '₹', HKD: 'HK$',
};

// yfinance minor-unit quote codes (1/100 of the major currency) → display
// suffix + the major currency the FX pair quotes (GBp pence → GBP).
const MINOR_UNITS: Record<string, { suffix: string; major: string }> = {
  GBp: { suffix: 'p', major: 'GBP' },
  ZAc: { suffix: 'c', major: 'ZAR' },
  ILA: { suffix: 'c', major: 'ILS' },
};

/** Prefix/suffix pair for a currency — for chart axis tick affixes. */
export function currencyAffixes(currency?: string | null): { prefix: string; suffix: string } {
  const cur = currency || 'USD';
  const minor = MINOR_UNITS[cur];
  if (minor) return { prefix: '', suffix: minor.suffix };
  const symbol = SYMBOLS[cur];
  if (symbol) return { prefix: symbol, suffix: '' };
  return { prefix: '', suffix: ` ${cur}` }; // unknown ISO code → suffix label
}

/**
 * Format a price in its quote currency. Minor units get a suffix ("516.50p"),
 * known currencies a symbol prefix ("$189.12", "€98.40"), unknown codes a
 * code suffix ("1024.00 SEK"). null/undefined/NaN → "—".
 */
export function formatPrice(
  value: number | null | undefined,
  currency?: string | null,
  opts?: { decimals?: number },
): string {
  if (value == null || Number.isNaN(value)) return '—';
  const { prefix, suffix } = currencyAffixes(currency);
  return `${prefix}${value.toFixed(opts?.decimals ?? 2)}${suffix}`;
}

/** value × fxToUsd (the backend's 1-quote-unit→USD multiplier); null-safe. */
export function convertToUsd(
  value: number | null | undefined,
  fxToUsd: number | null | undefined,
): number | null {
  if (value == null || fxToUsd == null || Number.isNaN(value)) return null;
  return value * fxToUsd;
}

/** Live-rate caption for the USD toggle, in major units: "1 GBP ≈ $1.27". */
export function usdRateCaption(currency: string, fxToUsd: number): string {
  const minor = MINOR_UNITS[currency];
  const majorRate = fxToUsd * (minor ? 100 : 1);
  return `1 ${minor?.major ?? currency} ≈ $${majorRate.toFixed(2)}`;
}
