# FiForesight — CLAUDE.md

## What This Is
AI-driven quantitative financial forecasting SaaS. Ticker lookup → ensemble ML forecast (48h price range) + technical indicators + 3-model LLM analyst jury + VADER sentiment + live news. Includes DCF valuation, options chain, trade setup with position sizing, portfolio simulation, and Supabase auth.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript 6, MUI 7, Recharts 3, Tailwind CSS 4, Axios, Lucide React |
| Backend | Python 3.12, FastAPI, Uvicorn, LangGraph, FastMCP |
| ML/Forecasting | Prophet, SARIMAX (statsmodels), RandomForestRegressor (scikit-learn) |
| Market Data | yfinance, SerpAPI (news/trending) |
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
│   │   ├── market.py           # /dcf /options /ipo/calendar /earnings/calendar /sectors /briefing /orderbook
│   │   ├── analytics.py        # /analytics/accuracy/{symbol} /analytics/sentiment/{symbol}
│   │   ├── portfolio.py        # /portfolio/holdings (GET/POST/DELETE) /portfolio/summary (auth-gated)
│   │   └── alerts.py           # /alerts/rules (CRUD) /alerts/fires /alerts/subscribe /alerts/evaluate [cron] (Feature 9)
│   ├── config.py               # Env var loading (InfluxDB, Groq, SerpAPI, Supabase)
│   ├── models.py               # Pydantic schemas + run_monte_carlo
│   ├── services.py             # YFinanceService, InfluxService, SerpService, SentimentService, AnalystJuryService
│   ├── supabase_rest.py        # RLS-scoped holdings CRUD via the caller's forwarded JWT (Feature 10)
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
│   │   │   └── alerts/{rules,rules/[id],fires,subscribe,unsubscribe,vapid-public-key}/route.ts  # → /alerts/*
│   │   ├── (app)/insights/page.tsx           # Insights tab — accuracy + sentiment dashboard (Recharts)
│   │   ├── (app)/portfolio/page.tsx          # "My Portfolio" tab — real holdings + live P&L (Feature 10)
│   │   ├── (app)/alerts/page.tsx             # "Alerts" tab — rule builder + fires + Web Push (Feature 9)
│   │   ├── simulation/page.tsx               # "Simulator" tab — backtest race vs S&P (NOT real holdings)
│   │   ├── layout.tsx                        # Root layout (ClientProviders + New Relic)
│   │   └── page.tsx                          # Main dashboard
│   ├── components/
│   │   ├── AnalystJuryPanel.tsx              # 3-analyst verdict cards + consensus badge
│   │   ├── AuthModal.tsx                     # Supabase sign-in / sign-up MUI dialog
│   │   ├── ClientProviders.tsx               # 'use client' wrapper for AuthProvider
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
│   ├── lib/supabase.ts                       # createClient with env-var fallbacks
│   ├── lib/holdings.ts                        # Portfolio holdings client → /api/portfolio proxies
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
      → Ensemble forecast: Prophet + SARIMAX + RandomForest → high/low/confidence
      → Monte Carlo: 1 000 paths, seed=42 → P10/P50/P90, VaR-95, prob_gain
      → SerpAPI: news headlines + trending symbols
      → VADER SentimentService: compound [-1,1] + label (Bullish/Bearish/Neutral)
      → LangGraph StateGraph parallel fan-out (Groq):
          Llama 4 Scout (Macro & Risk) · Llama 3.3 70B (Growth) · Llama 3.1 8B Instant (Quant)
          Each isolated — failures degrade to Hold/25, not 500
      → Response: history, fundamentals, indicators, forecasts, jury verdicts, news, sentiment, monte carlo

      → Fire-and-forget: write_sentiment_score (sentiment_score measurement) — only if ≥1 headline scored

  → Fire-and-forget (non-blocking, after predict resolves):
      GET /api/dcf/{symbol}     → DCFCard (3-scenario WACC)
      GET /api/options/{symbol} → OptionsChainPanel (calls/puts)
      POST /api/trade-setup     → TradeSetupCard (entry/stop/targets + position size)

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
| Security hardening (rate limits, auth enforcement, CORS, input validation) | pending |
| Forecast accuracy & sentiment dashboard (Insights tab) | #244 |
| Portfolio Manager — real holdings + live P&L ("My Portfolio" tab) | #249 |
| Alerts & Notifications — rule builder + scheduled evaluator + Web Push ("Alerts" tab) | pending |

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
- **Security model** — `dependencies.py` holds the `limiter` singleton and all auth helpers. `require_user` dependency raises HTTP 401 when no valid Bearer token is present; applied to `/trade-setup` and `/jury/reanalyze`. `/predict` uses a single rate limit keyed by user ID (authed) or IP (anon) via `_user_rate_key`. `/chat` message is capped at 500 chars with control-char sanitization on all context values. CORS is restricted to `ALLOWED_ORIGINS`. Symbol inputs are validated with `[A-Za-z0-9.\-:]{1,15}` on `/predict`, `/dcf/{symbol}`, `/options/{symbol}`, and history. JWT verification picks the verifier by the token's `alg`: **ES256/RS256** (Supabase's default signing-key tokens) are verified against the project **JWKS** (`SUPABASE_URL`, or `SUPABASE_JWKS_URL`); legacy **HS256** tokens use `SUPABASE_JWT_SECRET`. JWKS-only (ES256) is a valid secure production config — the shared secret is not required when a JWKS URL is set. The backend fails closed when **neither** a JWKS URL nor a secret is configured (or decodes unsigned only when `ALLOW_INSECURE_JWT=true`, dev-only; logged at startup). All frontend auth API routes forward the `Authorization` header.
