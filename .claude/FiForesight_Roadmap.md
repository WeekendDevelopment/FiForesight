# FiForesight Roadmap

> Source of truth for planned work. Feature-based, free-tier only.
> Last synced: 2026-05-13

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

### 2. Implement `/compare` backend (peer comparison)
Frontend proxy `frontend/app/api/compare/route.ts` exists but backend handler is missing — currently a dead proxy.
Peer comp panel: same-sector tickers, side-by-side P/E, EV/EBITDA, beta, revenue growth.
Depends on #1.

### 3. Cache `fetch_info` in Redis (1h TTL)
Every `/predict` re-hits yfinance for static fundamentals. Redis is already wired.
Independent of #1/#2 — can ship in parallel.

### 4. Earnings calendar markers on chart
`yf.Ticker().calendar` → date marker overlay on `PriceChartCard`. ~30 LOC backend + small frontend.
High UX value for retail users.

### 5. Jury consensus row
Add weighted aggregate verdict + agreement level to `AnalystJuryPanel` ("3/3 Buy, avg confidence 72").
Pure frontend change.

### 6. DCF intrinsic value endpoint
`GET /dcf/{symbol}` — 3-scenario WACC-based valuation card. Pairs with Monte Carlo VaR.
Depends on #1.

### 7. Supabase auth + watchlists
Free tier. Unlocks personalization, persistent watchlists, daily briefings, alerts.
Bigger scope — break into auth-only PR first, watchlist UI second.

### 8. Backend pytest harness
Minimum: tests for `run_monte_carlo`, `run_ensemble_forecast`, `score_headlines`, `fetch_info`.
Block more features until basic coverage exists.

### 9. Position sizing in Trade Setup Card
Use Monte Carlo VaR to suggest % of portfolio to risk. Pure addition to existing endpoint.

### 10. Split `main.py` into routers
1593 lines is unwieldy. Split into `routers/predict.py`, `routers/simulation.py`, `routers/jury.py`, `routers/chat.py`.
Pure refactor — do after auth lands so router auth wiring is single-pass.

---

## Feature Ideas (not yet picked up)

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Morning briefing email/digest | High | Med | Needs auth (#7) |
| "Why did this move?" auto-explainer on >3% gaps | High | Med | News + jury delta |
| Options chain panel | Med | Med | `yf.Ticker().option_chain` is free |
| Sector heatmap (discovery) | Med | Med | Pre-baked sector ETFs |
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
