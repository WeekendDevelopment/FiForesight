# FiForesight Roadmap

> Source of truth for planned work. Feature-based, free-tier only.
> Last synced: 2026-06-06 — PRs #205 shipped; Features 5–8 planned (prompts written).

---

## Shipped

### Forecasting & Quant
- Ensemble forecast: Prophet + SARIMAX + RandomForest
- Technical indicators: RSI, MACD, Bollinger Bands, SMA50/200, Support/Resistance
- Historical forecast tracking & per-model accuracy/MAE (`ForecastTrackingService`)
- Monte Carlo GBM simulation — 1000 paths, VaR-95, p10/p50/p90, fan chart + 3D surface
- Volume Profile panel

### Intelligence
- 3-model LLM Analyst Jury (Llama 4 Scout, Llama 3.3 70B, Qwen3 32B) via Groq + LangGraph
- VADER sentiment scoring on news headlines
- Stock Chat Agent — SSE streaming via `POST /chat`
- Trade Setup Generator — entry/stop/3 targets + R:R + Groq rationale

### Data & UX
- SerpAPI news + trending sparklines
- Candlestick / line / TradingView toggle
- Dark/light theme, loading skeletons, ticker autocomplete
- Portfolio simulation page (`/simulation/suggest`, `/simulation/performance`, state persistence)
- `page.tsx` decomposed: 423 lines + 13 components in `frontend/components/`
- Jury consensus badge — weighted aggregate verdict + agreement level in `AnalystJuryPanel` (#189)
- DCF intrinsic value — `GET /dcf/{symbol}` 3-scenario WACC valuation card (#190)
- Position sizing (1% rule) — Monte Carlo VaR-based % of portfolio risk in Trade Setup Card (#191)
- Options chain panel — calls/puts table, ITM highlight, expiry selector (#194)
- Morning briefing (Market Pulse strip) — `MorningBriefingPanel`, `GET /briefing` (#205)
- "Why did this move?" explainer — `WhyDidMoveCard`, `predict.py:moveExplanation`, >3% trigger (#205)
- Sector heatmap — `SectorHeatmap`, `GET /sectors`, 11 SPDR ETFs (#205)

### Auth & Backend
- Supabase email/password auth — `AuthContext`, `AuthModal`, watchlist groundwork (#193)
- Backend pytest harness — 22 tests, no network calls (`backend/tests/`) (#192)
- Router split — `main.py` → `routers/predict.py`, `simulation.py`, `trade.py`, `market.py` (#195)

### Infra
- Redis caching layer (`redis_cache.py`)
- InfluxDB OHLCV cache (2Y)
- New Relic APM (backend + frontend)
- HTTPS, Docker multi-stage, Koyeb + Oracle Cloud deploys
- GitHub Actions: PR preview + prod deploy
- FastMCP server (`mcp_server.py`)

---

## Next Up — Features 5–8
> Prompts written (2026-06-06). Implement in order — each feature depends on the previous being merged.

### Feature 5 · App Shell + Landing Page Restructure
**Branch:** `feat/app-shell-navigation`

Introduce a persistent sidebar nav and restructure the app into a multi-tab architecture.
This is the foundational refactor — all subsequent features depend on it.

- Create Next.js route group `frontend/app/(app)/` with shared `AppShellContext`
  (isDark, primaryColor, themeMode)
- **AppShell layout** — fixed left sidebar (collapsible to icon-only, persisted in
  localStorage), bottom nav on mobile. Items: Home · Analysis · Options · Earnings ·
  IPO Tracker · Portfolio
- **New landing page `/`** — lightweight: MorningBriefingPanel + SectorHeatmap +
  TrendingSparklines + large search bar. Search navigates to `/analysis?symbol=X`.
  Market open/closed status badge.
- **`/analysis` page** — current `page.tsx` moved here. Reads `?symbol` param and
  auto-triggers prediction. Theme/auth controls move to sidebar footer.
- **Placeholder pages** — `/options`, `/earnings`, `/ipo` (filled in Features 6–8)
- **No new API calls** — pure structural refactor

**Files:**
```
CREATE  frontend/app/(app)/layout.tsx          ← AppShell + sidebar
CREATE  frontend/app/(app)/page.tsx            ← New landing
CREATE  frontend/app/(app)/analysis/page.tsx   ← Moved from app/page.tsx
CREATE  frontend/app/(app)/options/page.tsx    ← Placeholder
CREATE  frontend/app/(app)/earnings/page.tsx   ← Placeholder
CREATE  frontend/app/(app)/ipo/page.tsx        ← Placeholder
CREATE  frontend/contexts/AppShellContext.tsx
DELETE  frontend/app/page.tsx
```

---

### Feature 6 · Options Chain Tab + Earnings Calendar Tab
**Branch:** `feat/options-earnings-tabs`
**Depends on:** Feature 5

**Options Chain (`/options`):**
- Convert `OptionsChainPanel` from prop-fed → self-fetching (backward-compatible: still
  accepts `data` prop for the analysis tab)
- Add `?expiry=` query param to `GET /options/{symbol}` backend endpoint
- Black-Scholes Greeks (Delta + Theta) per contract via `scipy.stats.norm`
- Aggregate stats: put/call ratio, ATM IV calls/puts, IV skew
- Standalone `/options` page with symbol search — no prediction flow required

**Earnings Calendar (`/earnings`):**
- New `GET /earnings/calendar` backend endpoint in `market.py`
- Fetches `yf.Ticker().calendar` for top 60 S&P 500 stocks (hardcoded list)
- Returns `{ calendar: { "YYYY-MM-DD": [{symbol, name, market_cap}] } }`, top 8 per day
- Redis 6h TTL; 45s asyncio timeout (60 yfinance calls)
- Frontend: "This Week / This Month / Next Month / All" tab filter
- Card grid — clicking any card navigates to `/analysis?symbol=X`

**Files:**
```
MODIFY  backend/routers/market.py              ← Greeks, stats, expiry param, earnings endpoint
MODIFY  frontend/components/OptionsChainPanel.tsx ← Self-fetching + Greeks columns + stats bar
CREATE  frontend/app/(app)/options/page.tsx    ← Replace placeholder
CREATE  frontend/app/(app)/earnings/page.tsx   ← Replace placeholder
CREATE  frontend/app/api/earnings/route.ts
MODIFY  frontend/app/api/options/[symbol]/route.ts ← Forward expiry param
```

---

### Feature 7 · Ticker Analysis Tab Polish
**Branch:** `feat/analysis-tab-polish`
**Depends on:** Features 5 + 6

**A. Dynamic chart time intervals** *(highest priority — in roadmap since last session)*
- New `GET /history?symbol=&period=&interval=` endpoint
- Supported combos: 1D/5m · 5D/15m · 1M/1h · 3M/1d · 6M/1d · 1Y/1d · 2Y/1d
- Returns OHLCV bars + computed metrics: change_pct, period_high, period_low, sma20,
  ann_vol, rsi_series, vwap_series (intraday only)
- Redis TTL: 5 min intraday, 15 min daily
- Segmented button row on `PriceChartCard` — default 2Y (no regression)
- Metric chips update to match selected interval
- VWAP dashed overlay for intraday intervals (1D/5D), toggle button

**B. Persistent symbol in URL**
- After prediction, `router.replace('/analysis?symbol=NVDA', { scroll: false })`
- Reload/share URL preserves the last searched ticker

**C. Watchlist quick-launch**
- Watchlist chip click → triggers prediction AND updates URL

**Files:**
```
CREATE  backend/routers/market.py (or predict.py) ← GET /history endpoint
CREATE  frontend/app/api/history/route.ts
MODIFY  frontend/components/PriceChartCard.tsx    ← Interval selector + VWAP overlay
MODIFY  frontend/app/(app)/analysis/page.tsx      ← URL persistence + watchlist fix
```

---

### Feature 8 · IPO Tracker Tab
**Branch:** `feat/ipo-tracker`
**Depends on:** Features 5 + 6 + 7

- New `GET /ipo/calendar` endpoint in `market.py`
- **Primary source:** Financial Modeling Prep free tier (`FMP_API_KEY` env var, optional)
  → upcoming 90 days + recent 30 days IPOs with symbol, exchange, price range,
  shares offered, estimated market cap, status (expected/priced/withdrawn)
- **Fallback:** SEC EDGAR S-1 filings search (no API key, always available)
- `httpx` for async HTTP (non-blocking — do NOT use `requests` in async context)
- Redis 4h TTL
- Frontend: "Upcoming / Recent" tabs, IPO cards with all details
- Clicking a priced IPO card with known symbol → navigates to `/analysis?symbol=X`
- Graceful degradation: if FMP key absent, shows EDGAR fallback with note explaining
  how to enable full data

**New env var (optional):**
```
FMP_API_KEY=    # Free at financialmodelingprep.com — unlocks IPO calendar
```

**Files:**
```
MODIFY  backend/routers/market.py              ← GET /ipo/calendar
MODIFY  backend/requirements.txt               ← Add httpx if not present
CREATE  frontend/app/(app)/ipo/page.tsx        ← Replace placeholder
CREATE  frontend/app/api/ipo/route.ts
```

---

## Phase A Backlog — More Signal, Same Stack
> Research complete (2026-06-06). Prompt written. No new APIs required.

| Feature | Value | Effort | Notes |
|---|---|---|---|
| ATR (Average True Range) → adaptive stops | High | Low | Replace flat % stops in TradeSetup; `stop = entry ± 2×ATR` |
| RSI + MACD divergence detection | High | Med | `scipy.signal.find_peaks`; annotate chart; inject into jury context |
| Earnings surprise history | High | Low | `yf.Ticker().earnings_history` → last 4Q EPS beat/miss table |
| Options Greeks (Δ, Θ) + IV rank + put/call ratio | High | Med | Black-Scholes via `scipy.stats.norm`; partial in Feature 6 |
| RandomForest feature importance | Med | Low | `rf.feature_importances_` post-fit → top-5 bar chart |

---

## Phase B Backlog — New Data Sources
> Research complete (2026-06-06). Prompt written.

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Insider transactions (SEC EDGAR Form 4) | High | Med | Free, no key — `efts.sec.gov` search; last 10 Form 4 filings |
| FRED macro context → jury prompts | High | Med | `DGS10`, `CPIAUCSL`, `UNRATE`, `FEDFUNDS`, `T10Y2Y`; inject into analyst context |
| Regime detection (HMM via `hmmlearn`) | High | Med | 3-state Gaussian HMM; labels: trending_up / ranging / trending_down; badge on jury panel |
| Jury dissent surfacing | Med | Low | When split 2-1, extract minority rationale → amber "Dissenting View" card |
| VWAP intraday overlay | Med | Low | Partial in Feature 7; standalone: `/history` endpoint already covers this |
| Reddit sentiment (PRAW — free) | Med | High | `r/wallstreetbets` + `r/stocks` mention count + VADER score; needs Reddit API account |
| Google Trends signal (`pytrends`) | Med | Med | Relative search interest for `"{symbol} stock"`; fragile dependency |

---

## Phase C Backlog — New Architecture
> Research complete (2026-06-06). Prompt written.

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Tool-using jury agents (Groq function calling) | High | High | Give agents tools: `get_vix()`, `get_put_call_ratio()`, `get_insider_flow()`, `get_macro_snapshot()` |
| Walk-forward backtester | High | High | Rolling 252-day train → 5-day predict → step 21 days; per-model MAE + directional accuracy |
| Level 2 order book (Alpaca free paper trading) | Med | High | WebSocket → top 10 bid/ask levels; ladder UI; needs Alpaca account |
| Custom alert rule builder | High | High | Needs auth + background worker |
| Isolation Forest anomaly detection | Med | High | Flag statistical outliers in price/volume series |
| Pattern detection (`scipy.signal.find_peaks`) | Med | Med | Head & shoulders, double top/bottom, flag/pennant |

---

## Feature Ideas (longer horizon)

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Walk-forward backtester | High | High | Already in Phase C |
| Watchlist persistent (Supabase) | High | Med | Auth shipped; watchlist UI second pass |
| Daily briefing email / push | High | High | Needs worker + Supabase edge function |
| Multi-ticker overlay comparison | Med | Low | Ratio chart (stock vs SPY); rolling correlation |
| International markets | Med | Med | yfinance supports non-US tickers |
| Macro dashboard (FRED API — standalone page) | Med | Med | GDP, CPI, rates, yield curve as a dedicated `/macro` tab |
| Earnings call transcript sentiment | Med | High | SEC EDGAR free; NLP on 10-Q/8-K text |
| Short interest tracker | Med | Med | FINRA ATS transparency (free weekly data) |

---

## Free-Tier Constraint

All features use free APIs / free tiers / self-hosted:

| Source | Usage | Key Required |
|---|---|---|
| **yfinance** | Market data, history, fundamentals | No |
| **SerpAPI** | News headlines, trending symbols | Yes (free tier) |
| **Groq** | LLM jury (Llama 4 Scout, Llama 3.3 70B, Qwen3 32B) | Yes (free tier) |
| **VADER** | Headline sentiment scoring | No (local) |
| **Supabase** | Auth + watchlist persistence | Yes (free tier) |
| **FRED API** | Macro indicators (GDP, CPI, rates) | No (read-only) |
| **SEC EDGAR** | Form 4 insider filings, S-1 IPO filings | No |
| **FMP** | IPO calendar (Feature 8) | Yes (free tier, 250 req/day) |
| **Alpaca** | Level 2 order book (Phase C) | Yes (free paper trading) |
| **PRAW / Reddit** | Social sentiment (Phase B) | Yes (free dev account) |
| **InfluxDB** | OHLCV time-series cache | Self-hosted (Oracle) |
| **Redis** | Response caching | Self-hosted |
| **Koyeb + Oracle Cloud** | Hosting | Free tiers |
