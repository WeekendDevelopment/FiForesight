# FiForesight — CLAUDE.md

## What This Is
AI-driven quantitative financial forecasting SaaS. Ticker lookup → ensemble ML forecast (48h price range) + technical indicators + 3-model LLM analyst jury + VADER sentiment + live news. Includes DCF valuation, options chain, trade setup with position sizing, portfolio simulation, and Supabase auth.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript 6, MUI 7, Recharts 3, Tailwind CSS 4, Axios, Lucide React |
| Backend | Python 3.12, FastAPI, Uvicorn, LangGraph, FastMCP |
| ML/Forecasting | Prophet, SARIMAX (statsmodels), RandomForestRegressor (scikit-learn), scipy (`signal.find_peaks` — RSI/MACD divergence), hmmlearn (3-state Gaussian HMM — market regime, F16) |
| Market Data | yfinance, SerpAPI (news/trending), FRED (macro CSV — keyless), SEC EDGAR (Form 4 insider — keyless), FINRA (weekly short volume — keyless) |
| Sentiment | VADER (vaderSentiment) — headline scoring, compound score + label |
| AI / LLM Jury | Groq API — Llama 4 Scout, Llama 3.3 70B, Llama 3.1 8B (3-analyst jury via LangGraph) |
| Time-Series DB | InfluxDB |
| Auth | Supabase (email/password, free tier) |
| Observability | New Relic APM (backend + frontend) |
| Package Manager | pnpm (monorepo) |
| Infra | Docker, Terraform, GitHub Actions, Koyeb, Oracle Cloud VM |

---

## Project Structure

```
FiForesight/
├── backend/
│   ├── main.py                 # ~50-line entry point (lifespan + include_router × 9)
│   ├── dependencies.py         # Service singletons shared across routers
│   ├── routers/
│   │   ├── predict.py          # /health /debug /predict /sparklines /compare
│   │   ├── simulation.py       # /simulation/suggest /simulation/performance /simulation/state
│   │   ├── trade.py            # /trade-setup /chat
│   │   ├── market.py           # /dcf /options /ipo/calendar /earnings/calendar /sectors /sectors/heatmap (F23) /briefing /orderbook /macro/snapshot /insider/{symbol} (F15)
│   │   ├── analytics.py        # /analytics/accuracy/{symbol} /analytics/sentiment/{symbol}
│   │   ├── portfolio.py        # /portfolio/holdings (GET/POST/DELETE) /portfolio/summary (auth-gated)
│   │   ├── alerts.py           # /alerts/rules (CRUD) /alerts/fires /alerts/subscribe /alerts/evaluate [cron] (Feature 9)
│   │   └── watchlist.py        # /watchlist (GET/POST/DELETE) — Feature 13
│   ├── config.py               # Env var loading (InfluxDB, Groq, SerpAPI, FRED, Supabase)
│   ├── models.py               # Pydantic schemas + run_monte_carlo
│   ├── services.py             # YFinanceService, InfluxService, SerpService, SentimentService, AnalystJuryService, FREDService/InsiderService/ShortInterestService (F15), RegimeService (F16)
│   ├── supabase_rest.py        # RLS-scoped holdings + watchlist CRUD via caller's forwarded JWT
│   ├── alerts_store.py         # Alerts/fires/push-subs storage — user-JWT (RLS) + service-role (evaluator) (Feature 9)
│   ├── alerts_evaluator.py     # Scheduled rule evaluator + daily digest (pure evaluate_rule + orchestrator) (Feature 9)
│   ├── notifications.py        # Web Push (pywebpush/VAPID) + optional Resend email delivery (Feature 9)
│   ├── jury_graph.py           # LangGraph StateGraph for parallel analyst fan-out
│   ├── simulation_service.py   # Simulator "race" engine (suggest + performance) — NOT real holdings
│   ├── portfolio_service.py    # Portfolio Manager summary (live P&L, sector alloc, HHI, forecast)
│   ├── mcp_server.py           # FastMCP server — predict/sparklines/health as MCP tools
│   ├── tests/                  # pytest harness — 189 tests, no network calls
│   └── newrelic.ini            # New Relic APM config
├── frontend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── predict/route.ts
│   │   │   ├── compare/route.ts
│   │   │   ├── dcf/[symbol]/route.ts
│   │   │   ├── options/[symbol]/route.ts
│   │   │   ├── analytics/accuracy/[symbol]/route.ts   # → /analytics/accuracy
│   │   │   ├── analytics/sentiment/[symbol]/route.ts  # → /analytics/sentiment
│   │   │   ├── simulation/{suggest,performance,state}/route.ts
│   │   │   ├── portfolio/{holdings,holdings/[id],summary}/route.ts  # → /portfolio/*
│   │   │   ├── alerts/{rules,rules/[id],fires,subscribe,unsubscribe,vapid-public-key}/route.ts  # → /alerts/*
│   │   │   └── watchlist/{route.ts,[symbol]/route.ts}  # → /watchlist (Feature 13)
│   │   ├── (app)/insights/page.tsx           # Insights tab — accuracy + sentiment dashboard (Recharts)
│   │   ├── (app)/portfolio/page.tsx          # "My Portfolio" tab — real holdings + live P&L (Feature 10)
│   │   ├── (app)/alerts/page.tsx             # "Alerts" tab — rule builder + fires + Web Push (Feature 9)
│   │   ├── simulation/page.tsx               # "Simulator" tab — backtest race vs S&P (NOT real holdings)
│   │   ├── layout.tsx                        # Root layout + sidebar WatchlistPanel + MobileWatchlistBar (F13)
│   │   └── page.tsx                          # Main dashboard
│   ├── components/
│   │   ├── AnalystJuryPanel.tsx              # 3-analyst verdict cards + consensus badge
│   │   ├── AuthModal.tsx                     # Supabase sign-in / sign-up MUI dialog
│   │   ├── ClientProviders.tsx               # 'use client' wrapper (AuthProvider + WatchlistProvider)
│   │   ├── DCFCard.tsx                       # 3-scenario DCF valuation (bear/base/bull)
│   │   ├── FundamentalsPanel.tsx             # Extended metrics panel
│   │   ├── MonteCarloFanChart.tsx            # P10/P50/P90 fan chart (Recharts)
│   │   ├── MonteCarloProbabilitySurface.tsx  # 3D surface (react-plotly.js)
│   │   ├── OptionsChainPanel.tsx             # Calls/puts table, ITM highlight, expiry selector
│   │   ├── PeerComparisonPanel.tsx           # Side-by-side peer fundamentals
│   │   ├── PriceChartCard.tsx                # Candlestick/line + overlays + sub-panels
│   │   ├── StockChatPanel.tsx                # Groq streaming chat
│   │   ├── TradeSetupCard.tsx                # Entry/stop/targets + position sizing row
│   │   └── TrendingSparklines.tsx
│   ├── contexts/AuthContext.tsx              # AuthProvider + useAuth (Supabase session)
│   ├── contexts/WatchlistContext.tsx         # WatchlistProvider + useWatchlistContext (Feature 13)
│   ├── hooks/useWatchlist.ts                 # Thin wrapper over WatchlistContext (backward-compat API)
│   ├── lib/supabase.ts                       # createClient with env-var fallbacks
│   ├── lib/holdings.ts                       # Portfolio holdings client → /api/portfolio proxies
│   ├── lib/watchlist.ts                      # Watchlist client → /api/watchlist proxies (Feature 13)
│   └── ...config files
├── .claude/
│   └── FiForesight_Roadmap.md     # Source of truth for planned work
├── .github/workflows/             # pull-request.yml, merge.yml, docker-logs.yml
├── terraform/                     # Prod infra (Oracle, Koyeb)
├── terraform-preview/             # Staging infra
├── dockerfile                     # Multi-stage Docker build
└── start_backend.js               # Cross-platform dev launcher
```

---

## Dev Commands

```bash
# Recommended — runs both concurrently
pnpm run app:dev

# Individual
cd frontend && pnpm run dev     # Next.js on :3000
python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload

# Tests
python -m pytest backend/tests/ -v   # 189 tests, ~7s
ruff check backend/                   # linter

# Frontend
pnpm run lint    # ESLint
pnpm run build   # Next.js production build
```

---

## Environment Variables

Backend `backend/.env`:

```env
GROQ_API_KEY=            # Required — LLM analyst jury
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=
INFLUXDB_ORG=WeekendDevelopment
INFLUXDB_BUCKET=FiForesightBucket
SERP_API_KEY=            # Optional — news/trending
FRED_API_KEY=            # Optional (Feature 15) — FRED macro CSV works keyless; a key only raises the rate limit
PORT=8000
APP_ENV=local            # Optional — env tag on sentiment_score writes (local|preview|live)

# Security hardening (Feature 11)
SUPABASE_JWT_SECRET=     # Required in prod — JWT signature verification (warn-only if unset)
SUPABASE_URL=            # Supabase project URL — JWKS verification + Portfolio holdings REST
SUPABASE_ANON_KEY=       # Supabase anon key — `apikey` header for holdings PostgREST (Feature 10)
ALLOWED_ORIGINS=https://fiforesight.duckdns.org,https://fiforesight-preview.duckdns.org,http://localhost:3000
RATE_LIMIT_PREDICT_AUTH=10/minute   # per authenticated user
RATE_LIMIT_CHAT=20/minute
RATE_LIMIT_JURY=10/minute
RATE_LIMIT_TRADE=15/minute
RATE_LIMIT_BACKTEST=5/minute
RATE_LIMIT_READONLY=60/minute       # DCF, options, earnings, IPO, sectors, briefing, orderbook, analytics
RATE_LIMIT_PORTFOLIO=30/minute          # Portfolio holdings CRUD (per user)
RATE_LIMIT_PORTFOLIO_SUMMARY=15/minute  # Portfolio summary (yfinance fan-out, per user)

# Alerts & Notifications (Feature 9)
SUPABASE_SERVICE_ROLE_KEY=   # Evaluator only — bypasses RLS to read all users' rules. Never user-facing.
CRON_SECRET=                 # Guards POST /alerts/evaluate + /alerts/digest (X-Cron-Secret). Fail-closed.
ALERT_COOLDOWN_HOURS=6       # Min hours between re-fires of the same rule
VAPID_PUBLIC_KEY=            # Web Push — `npx web-push generate-vapid-keys`
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:alerts@fiforesight.duckdns.org
ALERT_EMAIL_ENABLED=false    # Optional email fallback (Resend free tier); web-push works without it
RESEND_API_KEY=
ALERT_EMAIL_FROM=FiForesight Alerts <alerts@fiforesight.duckdns.org>
RATE_LIMIT_ALERTS=30/minute  # Alerts rule CRUD + push subscribe (per user)
```

Frontend `frontend/.env.local`:

```env
BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co   # Optional
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key                 # Optional
NEXT_PUBLIC_APP_ENV=preview|live                             # New Relic
```

---

## Data Flow

```
User enters ticker
  → Frontend /api/predict (Next.js proxy)
    → FastAPI /predict (routers/predict.py)
      → InfluxDB (cached 2Y OHLCV) → fallback: yfinance
      → Technical indicators: RSI, MACD, BB, SMA50/200, EMA20/50, Support/Resistance, Earnings dates
      → Advanced signals (Feature 14): ATR-14, Stochastic %K/%D, ADX/+DI/−DI, OBV (last 30),
        RSI/MACD divergence (scipy find_peaks), earnings surprise (last 4Q), RF feature importance (top-5)
      → Market regime (Feature 16): RegimeService 3-state Gaussian HMM on last 60 bars →
        {regime, confidence, bars_in_current_regime} (trending_up/ranging/trending_down/unknown), Redis-cached 4h
      → Ensemble forecast: Prophet + SARIMAX + RandomForest → high/low/confidence
        (weights regime-tilted: SARIMA↑ in trending, RF↑ in ranging, confidence-scaled — F16)
      → Monte Carlo: 1 000 paths, seed=42 → P10/P50/P90, VaR-95, prob_gain
      → SerpAPI: news headlines + trending symbols
      → VADER SentimentService: compound [-1,1] + label (Bullish/Bearish/Neutral)
      → Alternative data (Feature 15) — all fired concurrently, bounded 12s, never block:
          FREDService.get_macro_snapshot()    → macro line injected into jury ctx (NOT in /predict response)
          InsiderService.get_insider_transactions(symbol) → insiderTransactions[] (SEC EDGAR Form 4)
          ShortInterestService.get_short_interest(symbol) → shortInterest {short %, days-to-cover}
      → LangGraph StateGraph parallel fan-out (Groq):
          Llama 4 Scout (Macro & Risk) · Llama 3.3 70B (Growth) · Llama 3.1 8B Instant (Quant)
          Each isolated — failures degrade to Hold/25, not 500. Jury ctx now carries the live FRED macro line
          + the live regime line (F16); detect_dissent surfaces the minority view on a 2-1 split.
      → Response: history, fundamentals, indicators, forecasts, jury verdicts, news, sentiment, monte carlo,
        insiderTransactions[], shortInterest (F15), regime + modelWeights (regime-tilted) + juryDissent (F16)
        (indicators payload also carries: atr_14, stoch_k/stoch_d, adx_14/plus_di/minus_di, obv_history,
         divergences {rsi_bullish, rsi_bearish, macd_bullish, macd_bearish}, rf_feature_importance, earnings_surprise)

      → Fire-and-forget: write_sentiment_score (sentiment_score measurement) — only if ≥1 headline scored
      → Fire-and-forget: write_market_regime (market_regime measurement) — only when regime ≠ unknown (F16)

  → Fire-and-forget (non-blocking, after predict resolves):
      GET /api/dcf/{symbol}     → DCFCard (3-scenario WACC)
      GET /api/options/{symbol} → OptionsChainPanel (calls/puts)
      POST /api/trade-setup     → TradeSetupCard (entry/stop/targets + position size)

Macro flow (Feature 15 — /macro tab, public, no auth):
  GET /api/macro/snapshot → FRED snapshot {dgs10,cpiaucsl,unrate,fedfunds,t10y2y}×{value,delta_30d}
                            + inverted bool + t10y2y_trend (31 pts) + fetched_at. Redis-cached 1h,
                            warmed on startup. {} when FRED unreachable (frontend empty state).
  GET /api/insider/{symbol} → last 10 SEC EDGAR Form 4 filings (also embedded in /predict). 30/min.

Insights flow (/insights tab — read-only, Redis-cached 15min, samples:0 empty state):
  GET /api/analytics/accuracy/{symbol}  → model MAE ranking, ensemble MAE by horizon d1–d5,
                                          directional accuracy %, forecast-vs-actual (from
                                          model_accuracy + forecast_record + price_outcome)
  GET /api/analytics/sentiment/{symbol} → 30-day VADER compound trend (from sentiment_score)

Simulator flow (/simulation page — "Simulator" tab, backtest RACE vs S&P, NOT real holdings):
  POST /api/simulation/suggest     → ticker suggestions by risk level
  POST /api/simulation/performance → historical P&L time-series
  GET/POST /api/simulation/state   → InfluxDB persistence

Portfolio Manager flow (/portfolio page — "My Portfolio" tab, REAL holdings + live P&L; auth-gated):
  GET    /api/portfolio/holdings       → list user's holdings (Supabase, RLS by JWT)
  POST   /api/portfolio/holdings       → add/update a holding (upsert by symbol)
  DELETE /api/portfolio/holdings/{id}  → remove (ownership enforced by RLS)
  GET    /api/portfolio/summary        → live P&L per holding + totals, sector allocation,
                                         diversification score (HHI), portfolio forecast
                                         (yfinance fan-out, Redis-cached 15min, skips bad symbols)

Alerts & Notifications flow (/alerts page — "Alerts" tab, auth-gated; Feature 9):
  GET    /api/alerts/rules             → list user's rules (Supabase, RLS by JWT)
  POST   /api/alerts/rules             → create a rule (validated per type)
  PATCH  /api/alerts/rules/{id}        → toggle active / update threshold
  DELETE /api/alerts/rules/{id}        → delete (ownership enforced by RLS)
  GET    /api/alerts/fires             → recent fire history
  GET    /api/alerts/vapid-public-key  → VAPID public key for the browser subscribe
  POST   /api/alerts/subscribe         → store a Web-Push subscription (upsert on endpoint)
  POST   /api/alerts/unsubscribe       → remove a Web-Push subscription

  Scheduled evaluator (NO sleep loop — driven by an external scheduler):
  POST /alerts/evaluate  [X-Cron-Secret] → every 15 min during market hours. Loads ALL active
       rules (service-role, cross-user), groups by symbol (one fetch each), evaluates each rule
       type (price_cross / rsi_threshold / pct_move / earnings_soon / forecast_breakout). On a
       fire outside its 6h cooldown: records an alert_fire, stamps last_fired, and delivers a
       Web Push (pywebpush/VAPID) + optional email (Resend). One bad symbol never aborts the batch.
  POST /alerts/digest    [X-Cron-Secret] → once daily. Reuses /briefing market data + each user's
       holdings movers, pushed/emailed to everyone with a push subscription.

Watchlist flow (Feature 13 — auth-gated writes, anon read = []):
  GET    /api/watchlist        → list saved symbols [{id, symbol, added_at}]; [] for anon
  POST   /api/watchlist        → add symbol (upsert; no 409 on duplicate); auth required
  DELETE /api/watchlist/{sym}  → remove symbol; 204 success, 404 not found; auth required
  (backed by Supabase `watchlists` table with RLS `auth.uid() = user_id`; GET Redis-cached 60s per user)

Sparklines intraday flow (Feature 13 — updated shape):
  GET /api/sparklines?tickers=AAPL,MSFT&extra=NVDA
    → List[{symbol, price, change_pct, bars: [{t, c}]}]
    → fetches yfinance 1d/5m per symbol; strips pre/post-market (09:30–16:00 ET)
    → per-symbol Redis cache 5min; partial failures skipped (other symbols still returned)
    → ?extra= merges watchlist symbols; deduplication; max 24 symbols total
```

---

## Coding Conventions

- **Backend**: Python snake_case, type hints on all functions, logging. `asyncio.to_thread()` for blocking yfinance/pandas calls. `asyncio.wait_for(timeout=12)` on external fetches.
- **Frontend**: TypeScript, camelCase, React functional components + hooks, MUI for UI.
- **Error handling**: Backend services fail gracefully (logged, non-fatal). Global 500 handler in `main.py` returns `{"detail": "An internal server error occurred."}` — never exposes tracebacks to clients.
- **API Proxy**: All frontend→backend calls go through Next.js `/api/*` routes for CORS safety.
- **Security**: Never yield raw exception messages to SSE streams or HTTP responses.

---

## Roadmap Status

See `.claude/FiForesight_Roadmap.md`. Recently shipped:

| Feature | PR |
|---------|-----|
| Jury consensus badge | #189 |
| DCF intrinsic value | #190 |
| Position sizing (1% rule) | #191 |
| pytest harness (99 tests) | #192 |
| Supabase email auth | #193 |
| Options chain panel | #194 |
| Router split (main.py → routers/) | #195 |
| IPO tracker tab | #229 |
| Free IPO calendar (Nasdaq → EDGAR; FMP removed) | #231 |
| Security hardening (rate limits, auth enforcement, CORS, input validation) | #235 |
| Forecast accuracy & sentiment dashboard (Insights tab) | #244 |
| Portfolio Manager — real holdings + live P&L ("My Portfolio" tab) | #249 |
| Alerts & Notifications — rule builder + scheduled evaluator + Web Push ("Alerts" tab) | #254 |
| Watchlist persistence + intraday sparklines + responsive design (F13) | pending |
| Advanced Technical Signals — ATR stops, divergence, earnings surprise, RF importance, Stoch/ADX/OBV (F14) | #260 |
| Alternative Data — FRED macro snapshot + jury injection + /macro tab, SEC EDGAR insider, FINRA short interest (F15) | pending |
| Sector Heatmap tab — 11 GICS sector ETFs, 1D/5D color-coded grid, click-to-load (F23) | pending |

---

## Token Efficiency Guidelines

- **Don't re-read files already covered here.** Use this CLAUDE.md instead of re-exploring structure on every task.
- **Read only what's needed.** Grep for symbols before reading whole files. Use line offsets for large files.
- **No speculative reads.**
- **Targeted edits over full rewrites.** Use `Edit` unless change is >50% of file.
- **Backend entry points**: `main.py` (thin), `routers/predict.py`, `routers/trade.py`, `routers/market.py`, `routers/simulation.py`, `dependencies.py`, `services.py`, `models.py`.
- **Frontend entry point**: `frontend/app/page.tsx`. Components in `frontend/components/`.

---

## Key Decisions & Gotchas

- InfluxDB is primary store; yfinance is fallback only.
- LLM jury runs via **LangGraph** (`jury_graph.py`) — parallel StateGraph fan-out. Each analyst node isolated so failures → Hold/25, not 500.
- **Llama 4 Scout** (`meta-llama/llama-4-scout-17b-16e-instruct`) is the Macro & Risk analyst. Kimi K2 was deprecated; GPT-OSS-20B was replaced (reasoning model with 1K RPD burned out).
- **Llama 3.1 8B Instant** (`llama-3.1-8b-instant`) is the Quant Lens analyst — chosen for its **14,400 RPD** free-tier limit (14.4× more than any other model). Rate limits: 30 RPM | 6K TPM | 14.4K RPD.
- **VADER sentiment** (`SentimentService` in `services.py`) scores headlines before the jury runs; compound score + label passed in each analyst's context. Each `/predict` also persists the compound score (fire-and-forget) to the **`sentiment_score`** InfluxDB measurement (tags: `symbol`, `env=Config.APP_ENV`; fields: `compound` float, `label` string) — only when ≥1 headline was scored. `query_sentiment_history` reads it for the Insights tab's 30-day trend.
- **Analytics / Insights** (`routers/analytics.py`) — read-only tier (60/min), 15-min Redis cache, 12s timeout. `/analytics/accuracy/{symbol}` is pure-transform over existing InfluxDB data (`query_model_accuracy` + `query_ensemble_mae` + `query_forecast_records` + `query_price_outcomes`): per-model MAE + best_model, ensemble MAE by horizon d1–d5, directional accuracy (`sign(pred−last)` vs `sign(actual−last)`, skips the `0.0` missing-prediction sentinel), and forecast-vs-actual (de-duped to one point per resolved date). Insufficient history → **`200` with `samples:0` + empty arrays** (NOT 404). `/analytics/sentiment/{symbol}` returns the 30-day trend + `current`. Frontend tab at `frontend/app/(app)/insights/page.tsx` (5 Recharts views, reads `isDark`/`primaryColor` from `AppShellContext`).
- **FastMCP server** — `fastmcp dev backend/mcp_server.py` exposes predict/sparklines/health as Claude Code tools.
- **Backend router split** — `main.py` is now ~50 lines; all routes live in `backend/routers/`. Service singletons in `dependencies.py`.
- **Supabase auth** — `frontend/lib/supabase.ts` + `frontend/contexts/AuthContext.tsx`. Falls back to placeholder strings if env vars not set (build succeeds without them).
- **Portfolio Manager (Feature 10)** — the **"My Portfolio"** tab (`frontend/app/(app)/portfolio/page.tsx`, `/portfolio`) tracks a user's **real holdings + live P&L**. This is DISTINCT from the **"Simulator"** tab (`/simulation`, formerly mislabeled "Portfolio"), which is a backtest **race vs the S&P** — endpoints (`/portfolio/*` vs `/simulation/*`) and tab labels are kept clearly separate. Holdings live in the Supabase **`holdings`** table (`id, user_id, symbol, shares, cost_basis, opened_at`; `unique(user_id, symbol)`) with a single RLS "own rows" policy `auth.uid() = user_id` — migration at `supabase/migrations/0001_holdings.sql` (mirrors the watchlist pattern). All `/portfolio/*` endpoints (`routers/portfolio.py`) are **auth-gated via `require_user`** (401 anon). The backend reads/writes holdings through Supabase **PostgREST** (`supabase_rest.py`) forwarding the caller's **own JWT** as Bearer + `SUPABASE_ANON_KEY` as `apikey`, so RLS scopes every query — **no service-role key** (free-tier safe). `GET /portfolio/summary` (`portfolio_service.py`) fans out to yfinance per holding (`asyncio.gather`, per-call `wait_for`, semaphore 6), computing per-holding market value/P&L/weight + sector, totals, **sector allocation**, a **diversification score** (`(1 − Σwᵢ²)×100`, HHI-based 0–100), and a **portfolio forecast** = market-value-weighted mean of a lightweight per-holding trend signal (SMA20 vs price, SMA20 vs SMA50, ~1-mo momentum) — NOT the full Prophet/SARIMAX/RF ensemble or jury (too expensive per holding). A holding whose data can't be fetched is **skipped (reported in `skipped`), never 500s**. Summary is Redis-cached 15min per user, invalidated on mutation. **Out of scope v1**: stock splits, dividends, multi-currency — cost basis is shown as the user entered it.
- **Alerts & Notifications (Feature 9)** — the **"Alerts"** tab (`frontend/app/(app)/alerts/page.tsx`, `/alerts`, auth-gated) lets users define rules of five types: **price_cross** (price above/below a level), **rsi_threshold** (14-period RSI above/below), **pct_move** (today's move ≥ %, optional up/down), **earnings_soon** (earnings within N days), **forecast_breakout** (price breaks the latest ensemble d1 high/low band). Rules + fire history + push subscriptions live in Supabase tables **`alert_rules`**, **`alert_fires`**, **`push_subscriptions`** (migrations `0003_alerts.sql` + `0004_push_subscriptions.sql`), each with a single RLS "own rows" policy on `auth.uid()`. User-facing CRUD (`routers/alerts.py`, all `require_user`) reads/writes via the caller's forwarded JWT through `alerts_store.py` (PostgREST + RLS — same model as holdings). **The scheduled evaluator is the one place that needs elevated access**: `alerts_evaluator.evaluate_alerts()` loads ALL active rules across users (service-role key, **bypasses RLS** — never used by a user request), groups by symbol (one yfinance/Influx fetch each), runs the pure `evaluate_rule()` per type, and on a fire outside its **`ALERT_COOLDOWN_HOURS`** (default 6h) window records an `alert_fire`, stamps `last_fired`, and delivers. Delivery (`notifications.py`): **Web Push** via `pywebpush` + a server **VAPID** key pair (free, no third-party — keys via `npx web-push generate-vapid-keys`; browser subscribes through a service worker at `frontend/public/sw.js`), plus an **optional** email fallback (Resend free tier, gated by `ALERT_EMAIL_ENABLED`). One bad symbol never aborts the batch (logged + continue). **Scheduling has NO sleep loop**: `POST /alerts/evaluate` (every 15 min) and `POST /alerts/digest` (once daily) are internal endpoints guarded by a shared **`X-Cron-Secret`** header (env `CRON_SECRET`, fail-closed → 503 when unset); drive them from a GitHub Actions cron, a Supabase scheduled Edge Function, or any cron+curl. Both also 503 without `SUPABASE_SERVICE_ROLE_KEY`. The daily digest reuses `/briefing` market data + each user's holdings movers.
- **react-plotly.js exception** — `MonteCarloProbabilitySurface.tsx` is the only component using react-plotly.js (3D surface). All 2D charts remain Recharts.
- `strict: false` in tsconfig.
- pnpm workspace root has no source — all code in `frontend/` or `backend/`.
- Deploys: PRs → preview (`fiforesight-preview.duckdns.org`), main → prod (`fiforesight.duckdns.org` + Koyeb).
- `/compare` frontend route exists; backend endpoint is implemented in `routers/predict.py`.
- **IPO calendar** (`GET /ipo/calendar` in `market.py`) — **no API key**. Free **Nasdaq** calendar (`api.nasdaq.com/api/ipo/calendar`, needs a browser User-Agent; the default) → **SEC EDGAR** S-1 search (keyless last resort, recent filings only, no upcoming). Response carries `source: "nasdaq"|"edgar"`. `?refresh=true` bypasses the 4h Redis cache. Nasdaq dedup is upcoming-first (a scheduled deal also appears in priced/withdrawn tables). FMP was dropped — it retired its *free* IPO calendar on 2025-08-31.
- **Watchlist (Feature 13)** — `watchlists` Supabase table (`id, user_id, symbol, added_at`; `unique(user_id, symbol)`); RLS `auth.uid() = user_id`; migration at `supabase/migrations/0006_watchlist.sql`. Router at `backend/routers/watchlist.py`. GET is public (anon → `[]`); POST/DELETE are `require_user`-gated. Same PostgREST forwarding pattern as holdings — caller's JWT + anon key, no service-role. Backend Redis caches GET 60s per user; invalidated on write. Frontend: `WatchlistContext` (`frontend/contexts/WatchlistContext.tsx`) is the source of truth — wraps `AuthProvider` in `ClientProviders.tsx`, fetches on auth-state change, exposes `{watchlist, isLoading, isWatched, add, remove, reload}`. `frontend/hooks/useWatchlist.ts` is a thin backward-compat wrapper over `useWatchlistContext()`. `lib/watchlist.ts` was rewritten to proxy through `/api/watchlist*` (NOT direct Supabase SDK calls). The sidebar shows a collapsible **Watchlist** section below nav items; mobile gets a fixed bottom chip bar. The old `watchlist` (singular) Supabase table from `AuthContext` groundwork is superseded by `watchlists` (plural) via backend proxy.
- **Intraday sparklines (Feature 13)** — `/sparklines` response shape changed from `Dict[str, List[float]]` (old flat prices) to `List[{symbol, price, change_pct, bars: [{t, c}]}]`. `TrendingSparklines` now accepts `tickers: string[]` (not `{symbol}[]`). The `?extra=` param appends watchlist symbols to the base list; deduplicated to max 24. Each symbol cached 5min in Redis independently. `_fetch_intraday_bars` strips pre/post-market (keeps 09:30–16:00 ET via tz_convert), returns `{}` on any failure.
- **Responsive design (Feature 13)** — breakpoints: 320px (xs, mobile), 768px (sm, tablet), 1280px (md, desktop), 2560px (4K). Key fixes: PriceChart height 220/300/400px via `useMediaQuery`; DCFCard + TradeSetupCard 3-column grids stack on xs; FundamentalsPanel grid xs:6/sm:4/md:3; Earnings/IPO responsive CSS grid; sidebar `maxWidth: 280` cap at 4K; Shell content `maxWidth: 1600` for 4K; MobileNav tap targets `minHeight: 44`. MorningBriefingPanel + SectorHeatmap use `overflowX: auto` / `flexWrap: wrap` — fine at 320px. OptionsChainPanel table has `overflowX: auto` wrapper. Portfolio table hides columns on mobile via `isMobile` (`useMediaQuery`).
- **Security model** — `dependencies.py` holds the `limiter` singleton and all auth helpers. `require_user` dependency raises HTTP 401 when no valid Bearer token is present; applied to `/trade-setup` and `/jury/reanalyze`. `/predict` uses a single rate limit keyed by user ID (authed) or IP (anon) via `_user_rate_key`. `/chat` message is capped at 500 chars with control-char sanitization on all context values. CORS is restricted to `ALLOWED_ORIGINS`. Symbol inputs are validated with `[A-Za-z0-9.\-:]{1,15}` on `/predict`, `/dcf/{symbol}`, `/options/{symbol}`, and history. JWT verification picks the verifier by the token's `alg`: **ES256/RS256** (Supabase's default signing-key tokens) are verified against the project **JWKS** (`SUPABASE_URL`, or `SUPABASE_JWKS_URL`); legacy **HS256** tokens use `SUPABASE_JWT_SECRET`. JWKS-only (ES256) is a valid secure production config — the shared secret is not required when a JWKS URL is set. The backend fails closed when **neither** a JWKS URL nor a secret is configured (or decodes unsigned only when `ALLOW_INSECURE_JWT=true`, dev-only; logged at startup). All frontend auth API routes forward the `Authorization` header.
- **Advanced Technical Signals (Feature 14)** — five signal upgrades shipped together. Indicator helpers live in `models.py` (`calculate_atr`, `calculate_stochastic`, `calculate_adx`, `calculate_obv`, `detect_divergences`), each self-contained and returning `None`/all-false on failure so a bad indicator never aborts `/predict`. `routers/predict.py` computes them at Step 4b# and adds them to the **`indicators`** payload (`atr_14`, `stoch_k/stoch_d`, `adx_14/plus_di/minus_di`, `obv_history` = last 30, `divergences`, `rf_feature_importance` = RF top-5, `earnings_surprise` = last 4Q). **ATR-based adaptive stop** (`routers/trade.py`): when the frontend passes `atr_14`, the stop is `entry ∓ k×ATR` (k=2.0, or 2.5 when `conservative:true`) instead of a flat %, **hard-capped at 8%** from entry; falls back to the S/R % stop when ATR is absent (legacy/anon callers). Response adds `atr_14` + `atr_multiplier`. **Divergence** (`detect_divergences`, scipy `find_peaks` on price & indicator troughs/peaks ≥5 bars apart over the last 20 bars; all-false under 30 bars) is also injected into the jury context and each analyst's system prompt. **RF feature importance** is threaded out of `_rf_forecast` (now returns `(forecast_array, importances)` — `backtest.py` takes `[0]`) through `run_ensemble_forecast`. **Earnings surprise** comes from `YFinanceService.fetch_earnings_surprise` (yfinance `earnings_history`, Redis-cached 24h, `[]` on failure). Frontend: ATR annotation in `TradeSetupCard`, earnings-surprise Accordion in `FundamentalsPanel`, `ModelFeatureImportanceBar.tsx` below `ModelWeightBar`, and `SignalPanels.tsx` (Stoch/ADX gauges with ref lines, OBV area chart, divergence badges) below the chart in `PriceChartCard` — sub-panel visibility persisted in `localStorage` (`fiforesight:subpanels`), default hidden. Stoch/ADX are latest-value gauges (backend sends scalars, not per-bar series); OBV uses the 30-value history.
- **Alternative Data Sources (Feature 15)** — three free, **keyless** feeds added as services in `services.py` (registered in `dependencies.py`). **`FREDService`** pulls 5 macro series (`DGS10`, `CPIAUCSL`, `UNRATE`, `FEDFUNDS`, `T10Y2Y`) from the public `fredgraph.csv?id=…` endpoint, concurrently (`asyncio.gather`, 10s/series). **Gotcha**: a `cosd` (≈1150-day) start-date window is REQUIRED — without it the daily series (DGS10/T10Y2Y) download their full multi-decade history (~16k rows) and time out, silently dropping from the snapshot. Returns per-series `{value, delta_30d}` (delta = last − first of the last 31 points; for monthly series that's ~31 months, not literally 30 days), plus `inverted` (t10y2y<0), `t10y2y_trend` (31 pts for the chart), and `fetched_at`. Redis-cached 1h (`fred:snapshot`), **warmed on startup** via the `main.py` lifespan. `FRED_API_KEY` is optional (CSV works keyless; a key only raises the rate limit). The macro snapshot is injected as a one-line `Macro (FRED): …` block into the jury ctx in `routers/predict.py::_run_analyst_jury` (param `macro=`), and each persona's system prompt got a one-sentence macro directive (Scout→DGS10/inversion/UNRATE, 70B→CPI→margins, 8B→FEDFUNDS→discount rate). **`InsiderService`** queries the keyless SEC EDGAR full-text index (`efts.sec.gov/LATEST/search-index`, `forms=4`, last 30d) → up to 10 `{filer, type, shares, price, date, sec_link}`. Caveat: the FTS index reliably carries filer/date/link but NOT transaction code/shares/price (those live in the Form 4 XML), so `type` often defaults to `"Filing"` and shares/price to `null` on real data — the card handles this gracefully (grey chip, "—"). Redis-cached 6h per symbol. **`ShortInterestService`** downloads the most recent FINRA weekly short-volume file (`cdn.finra.org/equity/regsho/weekly/CNMSshvol{YYYYMMDD}.txt`, pipe-delimited, tries the last 8 days), parses `{symbol:{short_volume,total_volume}}`, caches the blob in Redis 24h (`finra:short:{date}`), and per symbol returns `{short_volume, total_volume, short_ratio, days_to_cover, report_date}` where `days_to_cover = short_volume / yf averageVolume`; **`None`** for symbols absent from the file (non-US/OTC). All three are fired concurrently in `/predict` (via `_safe_fetch`, 12s bound) and resolved before the response — EDGAR/FINRA/FRED latency never blocks. Endpoints `GET /macro/snapshot` (60/min) + `GET /insider/{symbol}` (30/min) live in `routers/market.py`. Frontend: `/macro` page (`frontend/app/(app)/macro/page.tsx`, **"Macro"** sidebar nav, `Globe` icon, public) with 5 stat cards (delta arrows colour-coded: rising rate/CPI/fed-funds=red, unemployment=amber, spread down=red), a T10Y2Y trend `LineChart`, a 30d-delta `BarChart`, an inversion banner, and 60-min + `visibilitychange` auto-refresh; `InsiderTransactionsCard.tsx` (Accordion on the analysis page, default-open when any purchase exists, green/red/grey type chips, per-row SEC link); short interest ("SHORT % VOL", "DAYS TO COVER" red >5) added to the `FundamentalsPanel` grid. Types `MacroSnapshot`/`MacroSeries`/`InsiderTransaction`/`ShortInterest` in `frontend/types/index.ts`; proxies at `frontend/app/api/{macro/snapshot,insider/[symbol]}/route.ts`. 21 new backend tests in `test_alternative_data.py`.
- **Sector Heatmap tab (Feature 23)** — interactive sector grid, **distinct from** the legacy `/sectors` overview (`SectorHeatmap.tsx` on the landing page, list-of-tuples `SECTOR_ETFS`, 1D-only). New endpoint `GET /sectors/heatmap` (`routers/market.py`, readonly rate limit, cache key `sectors:heatmap:f23` — kept separate from the legacy `sectors:heatmap`) batch-downloads all 11 GICS sector ETFs in **one** `yf.download(..., group_by="ticker")` call (constant `SECTOR_ETF_MAP`, full sector name → ETF), returns `[{sector, etf, price, return1d, return5d}]` (a bad/empty ETF is skipped, never aborts; 502 only on a total fetch failure/timeout), Redis-cached 15 min. Frontend: `SectorHeatmapPanel.tsx` (props `{onSelectTicker}`, self-fetches `/api/sectors/heatmap` on mount + every 5 min, **1D/5D** `ToggleButtonGroup`, color-coded cells via `useTheme` palette — error.dark/.main / grey[700] / success.main/.dark by return magnitude, click loads the ETF) hosted on the **`/sectors`** page (`frontend/app/(app)/sectors/page.tsx`, **"Sectors"** sidebar nav, `Grid2X2` icon) which routes a click to `/analysis?symbol=ETF` (the analysis page auto-forecasts on `?symbol=` change). Responsive grid `xs:6/sm:4/md:3/lg:2` (2→3→4→6 per row). Type `SectorRow` in `frontend/types/index.ts`; proxy at `frontend/app/api/sectors/heatmap/route.ts`. Tests in `test_sector_heatmap.py`.
- **Market Regime Intelligence (Feature 16)** — `RegimeService` (`services.py`, singleton `regime_svc` in `dependencies.py`) fits a **3-state Gaussian HMM** (`hmmlearn`, `covariance_type="full"`, `n_iter=100`, `random_state=42`) per ticker on the **last 60 bars**. Two features per bar — daily **log return** + a **5-day realised-vol proxy** (rolling std of log returns, mean-normalised) — `StandardScaler`-standardised. States are mapped to stable labels by ascending mean log return (`np.argsort(means_[:,0])`: lowest→`trending_down`, middle→`ranging`, highest→`trending_up`). Returns `{regime, confidence (=predict_proba()[-1].max()), state_means, bars_in_current_regime (trailing run length)}`. **Robustness**: `<30` bars → `{"regime":"unknown","confidence":0.0}`; the entire fit is wrapped so any hmmlearn/numeric failure (incl. hmmlearn not installed) degrades to the unknown fallback + logs WARNING — **never raises from `/predict`**. Redis-cached 4h (`regime:{symbol}:{date}`); the unknown fallback is **not** cached (so a transient failure self-heals). hmmlearn needs a build toolchain on a Python with no prebuilt wheel (e.g. 3.14) — production/Docker is 3.12 (prebuilt wheel), and the graceful fallback keeps `/predict` working even if the wheel is missing. **Dynamic ensemble weights**: `adjust_weights_for_regime(base, regime, confidence)` (`models.py`) tilts weights — base `{prophet:0.30, sarima:0.40, rf:0.30}` (`BASE_ENSEMBLE_WEIGHTS`) × per-regime multipliers (`REGIME_WEIGHT_MULTIPLIERS`: trending → SARIMA×1.4/RF×0.7/Prophet×1.0; ranging → RF×1.4/SARIMA×0.7/Prophet×1.0; unknown → unchanged), formula `adjusted = base + (regime_weight − base) × confidence`, renormalised to sum 1.0 (low confidence ⇒ gentler tilt; e.g. trending@1.0 → SARIMA ≈ 0.52). `run_ensemble_forecast` applies this as a **final tilt on the RL/realtime-blended weights** (so RL and regime co-exist; a failed model stays at 0 since its ×multiplier keeps it 0) — the exposed `modelWeights` are the tilted weights, which flow live into `ModelWeightBar`. The regime is injected into the jury ctx (`regime_line` in `_run_analyst_jury`, param `regime=`) + a one-sentence directive in each persona's system prompt (Scout→risk stance, 70B→momentum reliability, 8B→weights already tilted). Persisted fire-and-forget to the new **`market_regime`** InfluxDB measurement (tags `symbol`,`env`; fields `regime` str, `confidence` float) via `InfluxService.write_market_regime`, only when regime ≠ unknown. **Jury dissent** (`detect_dissent` in `jury_graph.py`): on a clean **2-1 split** (sign buckets bull/hold/bear) it returns the lone minority's `{analyst, verdict, rationale}`; `None` when unanimous, a 1-1-1 split, incomplete, or any analyst failed (model=`error`). Added to `/predict` (`regime`, `juryDissent`) and `/jury/reanalyze` (`juryDissent`). Frontend: `RegimeBadge.tsx` (MUI Chip + lucide icon — `TrendingUp`/`Minus`/`TrendingDown`/`HelpCircle`, green/amber/red/grey) shown in the `AnalystJuryPanel` header + a one-line "weight increased to favour {model}" explanation, an amber `Alert` "Dissenting View" card below the analyst cards (computed client-side from `liveAnalysts`, mirroring `detect_dissent`, so it stays reactive after a tool re-analysis), and a regime subtitle on `MonteCarloFanChart`. Types `RegimeInfo`/`JuryDissent` + `regime`/`juryDissent` on `PredictionData`. 16 new backend tests in `test_regime.py` (the real-HMM test is `importorskip`-gated on hmmlearn).
