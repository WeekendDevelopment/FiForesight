# FiForesight — CLAUDE.md

## What This Is
AI-driven quantitative financial forecasting SaaS. Ticker lookup → ensemble ML forecast (48h price range) + technical indicators + Gemini AI analyst note + live news.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript 6, MUI 7, Recharts 3, Tailwind CSS 4, Axios, Lucide React |
| Backend | Python 3.12, FastAPI, Uvicorn |
| ML/Forecasting | Prophet, SARIMAX (statsmodels), RandomForestRegressor (scikit-learn) |
| Market Data | yfinance, SerpAPI (news/trending) |
| AI / LLM Jury | Groq API — Kimi K2, Llama 3.3 70B, Qwen3 32B (3-analyst jury system) |
| Time-Series DB | InfluxDB |
| Observability | New Relic APM (backend + frontend) |
| Package Manager | pnpm (monorepo) |
| Infra | Docker, Terraform, GitHub Actions, Koyeb, Oracle Cloud VM |

---

## Project Structure

```
FiForesight/
├── backend/
│   ├── config.py          # Env var loading (InfluxDB, Groq, SerpAPI)
│   ├── main.py            # Routes (/predict, /health, /debug)
│   ├── models.py          # Pydantic schemas
│   ├── services.py        # yfinance, InfluxDB, SerpAPI calls
│   └── newrelic.ini       # New Relic APM config
├── frontend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── predict/route.ts   # POST proxy → FastAPI /predict
│   │   │   └── compare/route.ts   # GET proxy → FastAPI /compare (stub)
│   │   ├── layout.tsx             # Root layout + New Relic script injection
│   │   └── page.tsx               # Main dashboard (~78KB monolith)
│   ├── public/
│   │   ├── newrelic.live.js       # New Relic browser agent (prod)
│   │   └── newrelic.preview.js    # New Relic browser agent (preview)
│   └── ...config files
├── .claude/
│   └── FiForesight_Roadmap.md     # Source of truth for planned work
├── .github/
│   ├── workflows/
│   │   ├── pull-request.yml       # PR: lint, build, docker, preview deploy
│   │   ├── merge.yml              # Main: version, release, prod deploy
│   │   └── docker-logs.yml        # Manual: fetch container logs
│   ├── actions/                   # Custom composite actions
│   │   ├── deploy-koyeb/          # Deploy to Koyeb
│   │   ├── deploy-oracle/         # Deploy to Oracle Cloud VM
│   │   ├── setup-secrets/         # Secret management
│   │   └── terraform/             # Terraform plan/apply
│   └── scripts/                   # Version generation scripts
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
# Backend
python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload

# Frontend only
pnpm run lint    # ESLint
pnpm run build   # Next.js production build
```

---

## Environment Variables (backend `.env`)

```env
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=
INFLUXDB_ORG=WeekendDevelopment
INFLUXDB_BUCKET=FiForesightBucket
GROQ_API_KEY=            # Required — LLM analyst jury (Kimi K2, Llama 70B, Qwen3 32B)
SERP_API_KEY=            # Optional — news/trending
PORT=8000
```

Frontend env:
- `BACKEND_URL=http://localhost:8000` (optional, has default in `route.ts`)
- `NEXT_PUBLIC_APP_ENV=preview|live` (controls New Relic script loading)

---

## Data Flow

```
User enters ticker
  → Frontend /api/predict (Next.js proxy)
    → FastAPI /predict
      → Check InfluxDB (cached 2Y OHLCV)
        → Fallback: yfinance fetch + store
      → Technical indicators: RSI, MACD, BB, SMA50/200, Support/Resistance
      → Ensemble forecast: Prophet + SARIMAX + RandomForest → high/low/confidence
      → LLM Analyst Jury (3 concurrent Groq calls via asyncio.gather):
        → Kimi K2 (Macro & Risk Lens)
        → Llama 3.3 70B (Growth Lens)
        → Qwen3 32B (Quant Lens)
        → Each returns: verdict, confidence, reasoning, target prices
      → SerpAPI: news headlines + trending symbols
      → Response: history, fundamentals, indicators, forecasts, jury verdicts, news
  → Recharts renders: candlestick/line, RSI panel, MACD panel, BB/SMA overlays
  → AnalystJuryPanel renders 3 analyst cards with ratings
```

---

## Coding Conventions

- **Backend**: Python snake_case, type hints, logging. `asyncio.to_thread()` for blocking calls.
- **Frontend**: TypeScript, camelCase, React functional components + hooks, MUI for UI.
- **Error handling**: Backend services fail gracefully (logged, non-fatal). Global 500 handler returns traceback in dev.
- **API Proxy**: All frontend→backend calls go through `/api/predict` Next.js route (CORS safety).

---

## Roadmap Status

See `.claude/FiForesight_Roadmap.md` for full task list. Jira project: **FIFO** on Atlassian.

**7 Epics** (2 stories Done, 18 To Do):
- **FIFO-5 ML & Forecasting** — Advanced indicators done (FIFO-7), ensemble improvements + forecast tracking pending
- **FIFO-6 News & Sentiment** — SerpAPI integration, sentiment pipeline, AI analyst notes all pending
- **FIFO-32 Infrastructure & DevOps** — HTTPS hardening, CI/CD improvements, monitoring pending
- **FIFO-33 Testing & Quality** — 0% coverage today, target 70%+ (pytest, Vitest, Playwright)
- **FIFO-34 Frontend Architecture** — Component decomposition of 78KB page.tsx, a11y, performance
- **FIFO-35 User Auth** — Supabase auth, watchlists, alerts pending
- **FIFO-101 LLM Analyst Jury** — 3-model jury system done (FIFO-102), self-hosted LLM + fine-tuning pending

---

## Token Efficiency Guidelines

- **Don't re-read files already covered here.** This CLAUDE.md is the project summary — use it instead of re-exploring structure/stack on every task.
- **Read only what's needed.** Use `Grep` to find specific symbols before reading whole files. Use line offsets when only a section is relevant.
- **No speculative reads.** Don't read files "just in case" — read when a task directly requires it.
- **Targeted edits over full rewrites.** Use `Edit` (diff-based) instead of `Write` (full file) unless the change is >50% of the file.
- **Skip re-summarizing.** After making changes, don't restate what was done — the diff is visible.
- **Don't explore what git knows.** Use `git log`, `git diff`, `git blame` for history instead of re-reading files.
- **Roadmap is in `.claude/FiForesight_Roadmap.md`.** Don't ask what's next — check there first.
- **Backend is 4 files.** `config.py`, `main.py`, `models.py`, `services.py` — know this before deciding what to read.
- **Frontend entry point is `frontend/app/page.tsx`.** Components live in `frontend/components/`.

---

## Key Decisions & Gotchas

- No `.env.example` exists — document env vars in README manually.
- InfluxDB is the primary data store; yfinance is fallback only. If InfluxDB is down, data still works but won't persist.
- LLM jury calls are concurrent via `asyncio.gather()` — each analyst falls back gracefully on failure with robust JSON parsing + plain-text extraction fallback.
- `strict: false` in tsconfig — TypeScript is not fully strict.
- pnpm workspace root has no source — all code is in `frontend/` or `backend/`.
- `page.tsx` is ~78KB monolith — decomposition is tracked in Jira (FIFO-58).
- `FINNHUB_API_KEY` and `GOOGLE_GENAI_API_KEY` have been removed — replaced by `GROQ_API_KEY` for the jury system.
- `frontend/app/api/compare/route.ts` exists but backend `/compare` endpoint is not yet implemented.
- New Relic APM is active: `newrelic.ini` for backend, conditional script injection in `layout.tsx` based on `NEXT_PUBLIC_APP_ENV`.
- Deploys: PRs auto-deploy to preview (`fiforesight-preview.duckdns.org`), merges to main deploy to prod (`fiforesight.duckdns.org` + Koyeb).
