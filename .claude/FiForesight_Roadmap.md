# FiForesight Roadmap

> Source of truth for planned work. Feature-based, free-tier only.
> Last synced: 2026-05-18 — All "Next Up" items shipped; moving to Feature Ideas backlog.

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

## Next Up (ordered by signal-per-effort)

### 1. Extend `fetch_info` with quant fundamentals
Pull beta, EV/EBITDA, P/B, forwardPE, PEG, FCF, revenueGrowth, totalDebt, industry from yfinance.
Unblocks peer comps + DCF. ~½ day, single function edit.
**File:** `backend/services.py:802`
✅ **Shipped** — `services.py:864-884`

### 2. Implement `/compare` backend (peer comparison)
Frontend proxy `frontend/app/api/compare/route.ts` exists but backend handler is missing — currently a dead proxy.
Peer comp panel: same-sector tickers, side-by-side P/E, EV/EBITDA, beta, revenue growth.
Depends on #1.
✅ **Shipped** — `routers/predict.py:1284` + `PeerComparisonPanel.tsx`

### 3. Cache `fetch_info` in Redis (1h TTL)
Every `/predict` re-hits yfinance for static fundamentals. Redis is already wired.
Independent of #1/#2 — can ship in parallel.
✅ **Shipped** — `routers/predict.py:741-764` (1h TTL, also in `/compare`)

### 4. Earnings calendar markers on chart
`yf.Ticker().calendar` → date marker overlay on `PriceChartCard`. ~30 LOC backend + small frontend.
High UX value for retail users.
✅ **Shipped** — `services.py:900`, `predict.py:1023`, `PriceChartCard.tsx:505` (yellow dashed markers)

### 5. Jury consensus row
Add weighted aggregate verdict + agreement level to `AnalystJuryPanel` ("3/3 Buy, avg confidence 72").
Pure frontend change.
✅ **Shipped** — PR #189

### 6. DCF intrinsic value endpoint
`GET /dcf/{symbol}` — 3-scenario WACC-based valuation card. Pairs with Monte Carlo VaR.
Depends on #1.
✅ **Shipped** — PR #190

### 7. Supabase auth + watchlists
Free tier. Unlocks personalization, persistent watchlists, daily briefings, alerts.
Bigger scope — break into auth-only PR first, watchlist UI second.
✅ **Shipped** (auth) — PR #193

### 8. Backend pytest harness
Minimum: tests for `run_monte_carlo`, `run_ensemble_forecast`, `score_headlines`, `fetch_info`.
Block more features until basic coverage exists.
✅ **Shipped** — PR #192

### 9. Position sizing in Trade Setup Card
Use Monte Carlo VaR to suggest % of portfolio to risk. Pure addition to existing endpoint.
✅ **Shipped** — PR #191

### 10. Split `main.py` into routers
1593 lines is unwieldy. Split into `routers/predict.py`, `routers/simulation.py`, `routers/jury.py`, `routers/chat.py`.
Pure refactor — do after auth lands so router auth wiring is single-pass.
✅ **Shipped** — PR #195

---

## Next Up

### 1. Dynamic chart time intervals + contextual metrics
Chart currently always shows 2Y daily data. Add a 1D / 5D / 1M / 3M / 6M / 1Y / 2Y selector that:
- Re-fetches history at the appropriate yfinance `period` + `interval` (e.g. 1D → `period="1d", interval="5m"`)
- Updates **CHANGE**, **PERIOD HIGH**, **PERIOD LOW**, **SMA 20**, **ANN. VOL** to match the selected window
- Recalculates RSI series, MACD, Bollinger Bands for the active interval
- Frontend: segmented button row on `PriceChartCard`; backend: add `period` + `interval` params to `/predict` (or new `/history?symbol=&period=&interval=` endpoint to avoid re-running ML)

**Files:** `frontend/components/PriceChartCard.tsx`, `backend/routers/predict.py` (or new `GET /history`)

---

## Feature Ideas (not yet picked up)

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Morning briefing (in-app Market Pulse panel) | High | Med | ✅ Shipped — PR #205 (`MorningBriefingPanel`, `/briefing`) |
| ~~"Why did this move?" auto-explainer on >3% gaps~~ | ~~High~~ | ~~Med~~ | ✅ Shipped — PR #205 (`WhyDidMoveCard`, `predict.py:moveExplanation`) |
| ~~Options chain panel~~ | ~~Med~~ | ~~Med~~ | ✅ Shipped — PR #194 |
| ~~Sector heatmap (discovery)~~ | ~~Med~~ | ~~Med~~ | ✅ Shipped — PR #205 (`SectorHeatmap`, `/sectors`) |
| Custom alert rule builder | High | High | Needs auth + worker |
| Reddit/X sentiment delta | Med | High | PRAW free, X is paid → Reddit only |
| Walk-forward backtester | High | High | Validate jury historically |
| Pattern detection (`scipy.signal.find_peaks`) | Med | High | |
| Isolation Forest anomaly detection | Med | High | |
| Macro dashboard (FRED API — free) | Med | Med | GDP, CPI, rates |
| International markets | Med | Med | yfinance supports |
| Multi-ticker overlay comparison | Med | Low | |

---

## Free-Tier Constraint

All features use free APIs / free tiers / self-hosted:
- **Market data:** yfinance (free, unlimited)
- **News:** SerpAPI free tier
- **LLM:** Groq free tier (Llama 4 Scout, Llama 3.3 70B, Qwen3 32B)
- **Sentiment:** VADER (local, free)
- **Auth (planned):** Supabase free tier
- **Macro (planned):** FRED API (free)
- **Hosting:** Koyeb free + Oracle Always Free
- **Time-series DB:** InfluxDB (self-hosted on Oracle)
