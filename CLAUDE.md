# FiForesight — CLAUDE.md

## What This Is
AI-driven quantitative financial forecasting SaaS. Ticker lookup → ensemble ML forecast (48h price range) + technical indicators + Gemini AI analyst note + live news.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, TypeScript, MUI 5.15, Recharts 2.12, Tailwind CSS, Axios |
| Backend | Python 3.12, FastAPI, Uvicorn |
| ML/Forecasting | Prophet, SARIMAX (statsmodels), RandomForestRegressor (scikit-learn) |
| Market Data | yfinance, SerpAPI (news/trending) |
| AI | Google GenAI SDK — Gemini 2.5 Flash |
| Time-Series DB | InfluxDB |
| Package Manager | pnpm (monorepo) |
| Infra | Docker, Terraform, GitHub Actions |

---

## Project Structure

```
FiForesight/
├── backend/          # FastAPI engine
│   ├── config.py     # Env var loading
│   ├── main.py       # Routes (/predict, /health, etc.)
│   ├── models.py     # Pydantic schemas
│   └── services.py   # yfinance, InfluxDB, Gemini, SerpAPI calls
├── frontend/
│   ├── app/          # Next.js App Router
│   │   ├── api/predict/route.ts  # Proxy to FastAPI :8000/predict
│   │   ├── layout.tsx
│   │   └── page.tsx  # Main dashboard
│   ├── components/   # React components (charts, panels, etc.)
│   └── ...config files
├── .claude/
│   └── FiForesight_Roadmap.md  # Source of truth for planned work
├── terraform/        # Prod infra
├── terraform-preview/# Staging infra
├── dockerfile        # Multi-stage Docker build
└── start_backend.js  # Cross-platform dev launcher
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
FINNHUB_API_KEY=         # Required — market data
GOOGLE_GENAI_API_KEY=    # Required — Gemini analyst notes
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=
INFLUXDB_ORG=WeekendDevelopment
INFLUXDB_BUCKET=FiForesightBucket
SERP_API_KEY=            # Optional — news/trending
PORT=8000
```

Frontend: `BACKEND_URL=http://localhost:8000` (optional, has default in `route.ts`)

---

## Data Flow

```
User enters ticker
  → Frontend /api/predict (Next.js proxy)
    → FastAPI /predict
      → Check InfluxDB (cached 2Y OHLCV)
        → Fallback: yfinance fetch + store
      → Ensemble forecast: Prophet + SARIMAX + RandomForest → high/low/confidence
      → Gemini: analyst note (RSI, closes, forecast)
      → SerpAPI: news headlines + trending symbols
      → Response: 90-day history, fundamentals, indicators, news
  → Recharts renders: candlestick/line, RSI panel, MACD panel, BB/SMA overlays
```

---

## Coding Conventions

- **Backend**: Python snake_case, type hints, logging. `asyncio.to_thread()` for blocking calls.
- **Frontend**: TypeScript, camelCase, React functional components + hooks, MUI for UI.
- **Error handling**: Backend services fail gracefully (logged, non-fatal). Global 500 handler returns traceback in dev.
- **API Proxy**: All frontend→backend calls go through `/api/predict` Next.js route (CORS safety).

---

## Roadmap Status

See `.claude/FiForesight_Roadmap.md` for full task list. Summary:

**Track 1 — UX/Indicators**: 7/10 done.
- Pending: Candlestick chart mode, Multi-ticker comparison, Price alert system

**Track 2 — Data Expansion**: 0/8 done.
- News sentiment, Earnings markers, Options chain, Macro dashboard, Volume panel, Sector comparison, Social sentiment, International markets

**Track 3 — Intelligence**: 0/9 done.
- Support/resistance (DBSCAN), Pattern detection, Backtesting, Anomaly detection, LLM chat panel, Portfolio P&L, Risk metrics (Sharpe/Sortino/Beta), Custom alerts

**Sequencing**: Track 1 → Track 2 → Track 3 (in order, Track 3 tasks build on each other)

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
- Gemini calls are non-blocking — analyst note falls back to empty string on failure.
- `strict: false` in tsconfig — TypeScript is not fully strict.
- pnpm workspace root has no source — all code is in `frontend/` or `backend/`.
