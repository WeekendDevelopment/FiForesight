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
│   ├── main.py                 # ~50-line entry point (lifespan + include_router × 4)
│   ├── dependencies.py         # Service singletons shared across routers
│   ├── routers/
│   │   ├── predict.py          # /health /debug /predict /sparklines /compare
│   │   ├── simulation.py       # /simulation/suggest /simulation/performance /simulation/state
│   │   ├── trade.py            # /trade-setup /chat
│   │   └── market.py           # /dcf /options /ipo/calendar /earnings/calendar /sectors /briefing /orderbook
│   ├── config.py               # Env var loading (InfluxDB, Groq, SerpAPI)
│   ├── models.py               # Pydantic schemas + run_monte_carlo
│   ├── services.py             # YFinanceService, InfluxService, SerpService, SentimentService, AnalystJuryService
│   ├── jury_graph.py           # LangGraph StateGraph for parallel analyst fan-out
│   ├── simulation_service.py   # Portfolio simulation engine (suggest + performance)
│   ├── mcp_server.py           # FastMCP server — predict/sparklines/health as MCP tools
│   ├── tests/                  # pytest harness — 22 tests, no network calls
│   └── newrelic.ini            # New Relic APM config
├── frontend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── predict/route.ts
│   │   │   ├── compare/route.ts
│   │   │   ├── dcf/[symbol]/route.ts
│   │   │   ├── options/[symbol]/route.ts
│   │   │   └── simulation/{suggest,performance,state}/route.ts
│   │   ├── simulation/page.tsx               # Portfolio simulation page
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
python -m pytest backend/tests/ -v   # 99 tests, ~5s
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

# Security hardening (Feature 11)
SUPABASE_JWT_SECRET=     # Required in prod — JWT signature verification (warn-only if unset)
ALLOWED_ORIGINS=https://fiforesight.duckdns.org,https://fiforesight-preview.duckdns.org,http://localhost:3000
RATE_LIMIT_PREDICT_AUTH=10/minute   # per authenticated user
RATE_LIMIT_CHAT=20/minute
RATE_LIMIT_JURY=10/minute
RATE_LIMIT_TRADE=15/minute
RATE_LIMIT_BACKTEST=5/minute
RATE_LIMIT_READONLY=60/minute       # DCF, options, earnings, IPO, sectors, briefing, orderbook
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

  → Fire-and-forget (non-blocking, after predict resolves):
      GET /api/dcf/{symbol}     → DCFCard (3-scenario WACC)
      GET /api/options/{symbol} → OptionsChainPanel (calls/puts)
      POST /api/trade-setup     → TradeSetupCard (entry/stop/targets + position size)

Simulation flow (/simulation page):
  POST /api/simulation/suggest     → ticker suggestions by risk level
  POST /api/simulation/performance → historical P&L time-series
  GET/POST /api/simulation/state   → InfluxDB persistence
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
| pytest harness (22 tests) | #192 |
| Supabase email auth | #193 |
| Options chain panel | #194 |
| Router split (main.py → routers/) | #195 |
| IPO tracker tab | #229 |
| Free IPO calendar (Nasdaq → EDGAR; FMP removed) | #231 |
| Security hardening (rate limits, auth enforcement, CORS, input validation) | pending |

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
- **VADER sentiment** (`SentimentService` in `services.py`) scores headlines before the jury runs; compound score + label passed in each analyst's context.
- **FastMCP server** — `fastmcp dev backend/mcp_server.py` exposes predict/sparklines/health as Claude Code tools.
- **Backend router split** — `main.py` is now ~50 lines; all routes live in `backend/routers/`. Service singletons in `dependencies.py`.
- **Supabase auth** — `frontend/lib/supabase.ts` + `frontend/contexts/AuthContext.tsx`. Falls back to placeholder strings if env vars not set (build succeeds without them).
- **react-plotly.js exception** — `MonteCarloProbabilitySurface.tsx` is the only component using react-plotly.js (3D surface). All 2D charts remain Recharts.
- `strict: false` in tsconfig.
- pnpm workspace root has no source — all code in `frontend/` or `backend/`.
- Deploys: PRs → preview (`fiforesight-preview.duckdns.org`), main → prod (`fiforesight.duckdns.org` + Koyeb).
- `/compare` frontend route exists; backend endpoint is implemented in `routers/predict.py`.
- **IPO calendar** (`GET /ipo/calendar` in `market.py`) — **no API key**. Free **Nasdaq** calendar (`api.nasdaq.com/api/ipo/calendar`, needs a browser User-Agent; the default) → **SEC EDGAR** S-1 search (keyless last resort, recent filings only, no upcoming). Response carries `source: "nasdaq"|"edgar"`. `?refresh=true` bypasses the 4h Redis cache. Nasdaq dedup is upcoming-first (a scheduled deal also appears in priced/withdrawn tables). FMP was dropped — it retired its *free* IPO calendar on 2025-08-31.
- **Security model** — `dependencies.py` holds the `limiter` singleton and all auth helpers. `require_user` dependency raises HTTP 401 when no valid Bearer token is present; applied to `/trade-setup` and `/jury/reanalyze`. `/predict` uses a single rate limit keyed by user ID (authed) or IP (anon) via `_user_rate_key`. `/chat` message is capped at 500 chars with control-char sanitization on all context values. CORS is restricted to `ALLOWED_ORIGINS`. Symbol inputs are validated with `[A-Za-z0-9.\-:]{1,15}` on `/predict`, `/dcf/{symbol}`, `/options/{symbol}`, and history. `SUPABASE_JWT_SECRET` controls JWT verification — unset is dev-mode (logs startup WARNING). All frontend auth API routes forward the `Authorization` header.
