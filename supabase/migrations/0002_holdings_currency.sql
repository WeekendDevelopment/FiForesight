-- 0002_holdings_currency.sql
-- Add a `currency` column to the holdings table.
-- Safe on a populated table: existing rows default to 'USD'.
-- The CHECK constraint mirrors the backend _ALLOWED_CURRENCIES set.

alter table public.holdings
  add column if not exists currency text not null default 'USD';

alter table public.holdings
  drop constraint if exists holdings_currency_check;

alter table public.holdings
  add constraint holdings_currency_check check (
    currency in (
      'USD', 'GBP', 'GBp', 'CAD', 'AUD', 'INR', 'EUR', 'JPY',
      'HKD', 'SGD', 'CHF', 'SEK', 'NOK', 'DKK', 'NZD', 'ZAR',
      'BRL', 'MXN', 'KRW', 'TWD', 'CNY'
    )
  );
