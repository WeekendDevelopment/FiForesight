# FiForesight

[![Build](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/pull-request.yml/badge.svg)](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/pull-request.yml)
[![Build and Deploy](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/merge.yml/badge.svg)](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/merge.yml)

AI-driven quantitative financial forecasting SaaS. Enter any ticker and get an ensemble ML forecast, full technical analysis, a 3-model LLM analyst jury, Monte Carlo simulation, DCF valuation, live options chain, and real-time news — all in one dashboard.

**Live:** [fiforesight.duckdns.org](https://fiforesight.duckdns.org) · **Preview:** [fiforesight-preview.duckdns.org](https://fiforesight-preview.duckdns.org)

---

## Features

### Forecasting & Analysis
- **Ensemble ML Forecast** — Prophet + SARIMAX + Random Forest with dynamic inverse-error weighting; produces 48-hour high/low range + confidence score
- **Monte Carlo Simulation** — 1 000 price paths with P10/P50/P90 percentile fan chart and a 3D probability surface (react-plotly.js)
- **DCF Intrinsic Value** — 3-scenario WACC model (bear/base/bull) computed from real FCF and beta; shows margin of safety vs current price
- **5-Day Forecast Table** — Daily predicted price with high/low band and confidence percentage

### Technical Indicators
- **Candlestick / Line Chart** — Toggle between chart types, powered by Recharts
- **Bollinger Bands** — Upper/middle/lower with shaded region overlay
- **SMA 50 / SMA 200** — Simple moving average overlays
- **EMA 20 / EMA 50** — Exponential moving average overlays (toggleable)
- **RSI Panel** — Sub-chart with overbought (70) / oversold (30) reference lines
- **MACD Panel** — MACD line + signal + histogram sub-chart
- **Volume Sub-chart** — Bar chart below price
- **Support / Resistance** — Automatically detected key price levels
- **Earnings Calendar Markers** — Vertical markers on confirmed and estimated earnings dates

### LLM Analyst Jury
- **3 Independent AI Analysts** (via Groq API, parallel LangGraph fan-out):
  - Llama 4 Scout — Macro & Risk Lens
  - Llama 3.3 70B — Growth & Momentum Lens
  - Qwen3 32B — Quantitative Lens
- **Consensus Badge** — Weighted aggregate verdict (BUY / HOLD / SELL) with average confidence and agreement count
- **Per-analyst cards** — Verdict, confidence %, reasoning, and price targets

### Sentiment & News
- **VADER Sentiment** — Headlines scored with compound score [-1, 1] and Bullish/Bearish/Neutral label
- **Live News** — SerpAPI-powered headlines with source, thumbnail, and date
- **Trending Tickers** — Real-time trending symbols sidebar with sparklines

### Trade Setup
- **Entry Zone / Stop Loss / Targets** — Three price targets (T1/T2/T3) with risk:reward ratio
- **Position Sizing** — 1%-of-portfolio risk rule: suggested portfolio allocation based on VaR-95 stop distance
- **Setup Type Classification** — Bullish/Bearish breakout, momentum, or reversal label

### Options Chain
- **Nearest-Expiry Chain** — Calls and puts filtered to ±25% of spot price
- **Expiry Selector** — Switch between up to 8 upcoming expiry dates
- **ITM Highlighting** — In-the-money contracts highlighted in green (calls) or red (puts)
- **Columns** — Strike, Last, Bid, Ask, Chg%, Volume, Open Interest, IV%

### Fundamentals & Peer Comparison
- **Extended Fundamentals** — Market cap, P/E, forward P/E, PEG ratio, P/B, EV/EBITDA, FCF, revenue growth, total debt, beta, dividend yield, 52-week range, sector/industry
- **Peer Comparison Panel** — Side-by-side fundamentals for up to 5 sector peers

### Portfolio Simulation
- **Suggest Portfolio** — AI-driven ticker suggestions by risk level (conservative / balanced / aggressive)
- **Performance Simulation** — Historical P&L time-series for a custom holdings list
- **State Persistence** — Simulation state saved to InfluxDB

### Infrastructure
- **User Auth** — Supabase email/password sign-up and sign-in; session persisted via `onAuthStateChange`
- **AI Chat** — Groq-powered streaming chat assistant aware of the current ticker and prediction context
- **MCP Server** — FastMCP server exposing `predict`, `sparklines`, and `health` as Claude Code tools
- **Backend Tests** — pytest harness (22 tests) covering Monte Carlo, VADER sentiment, and yfinance fetch_info; all mocked, no network calls
- **New Relic APM** — Backend (`newrelic.ini`) + frontend (conditional browser agent) observability

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript 6, MUI 7, Recharts 3, Tailwind CSS 4, Lucide React |
| Backend | Python 3.12, FastAPI, Uvicorn |
| ML / Forecasting | Prophet, SARIMAX (statsmodels), RandomForestRegressor (scikit-learn) |
| LLM Jury | Groq API — Llama 4 Scout, Llama 3.3 70B, Qwen3 32B (LangGraph parallel fan-out) |
| Sentiment | VADER (vaderSentiment) |
| Market Data | yfinance, SerpAPI |
| Time-Series DB | InfluxDB |
| Auth | Supabase (email/password, free tier) |
| Observability | New Relic APM |
| Package Manager | pnpm (monorepo) |
| Infra | Docker, Terraform, GitHub Actions, Koyeb, Oracle Cloud VM |

---

## Getting Started

### Prerequisites

- Node.js 18+ / pnpm
- Python 3.12+
- InfluxDB instance (optional — yfinance fallback works without it)
- Groq API key (required for LLM jury)

### Installation

```bash
git clone https://github.com/WeekendDevelopment/FiForesight.git
cd FiForesight
pnpm install
pip install -r backend/requirements.txt
```

### Environment Variables

Create `backend/.env`:

```env
# Required
GROQ_API_KEY=your_groq_key

# Optional — yfinance fallback works without InfluxDB
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your_influx_token
INFLUXDB_ORG=WeekendDevelopment
INFLUXDB_BUCKET=FiForesightBucket

# Optional — news/trending tickers
SERP_API_KEY=your_serpapi_key

PORT=8000
```

Create `frontend/.env.local`:

```env
BACKEND_URL=http://localhost:8000

# Optional — Supabase auth
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key

# Optional — New Relic browser agent
NEXT_PUBLIC_APP_ENV=preview  # or "live"
```

### Run

```bash
pnpm run app:dev   # starts both Next.js (:3000) and FastAPI (:8000) concurrently
```

Or individually:

```bash
# Frontend
cd frontend && pnpm run dev

# Backend
python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:3000](http://localhost:3000).

### Tests

```bash
python -m pytest backend/tests/ -v   # 22 tests, ~1s, no network calls
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/debug` | Dependency diagnostics |
| POST | `/predict` | Full forecast — history, indicators, jury verdicts, news, sentiment, Monte Carlo |
| GET | `/sparklines` | Lightweight price sparklines for trending tickers |
| GET | `/compare?symbols=AAPL,MSFT` | Side-by-side fundamentals for peer comparison |
| GET | `/dcf/{symbol}` | DCF intrinsic value — bear/base/bull WACC scenarios |
| GET | `/options/{symbol}` | Nearest-expiry options chain (calls + puts, ±25% of spot) |
| POST | `/trade-setup` | Entry zone, stop loss, 3 targets, position sizing |
| POST | `/chat` | Streaming SSE chat assistant (Groq) |
| POST | `/simulation/suggest` | AI-suggested portfolio by risk level |
| POST | `/simulation/performance` | Historical P&L for a holdings list |
| POST/GET | `/simulation/state` | Save/load simulation state (InfluxDB) |

---

## Architecture

```
Browser
 └── Next.js App (/api/* proxy routes)
      ├── POST /api/predict  ──────────────► FastAPI /predict
      │                                          ├── InfluxDB (2Y cached OHLCV)
      │                                          │     └── yfinance (fallback)
      │                                          ├── Technical Indicators
      │                                          │     RSI · MACD · BB · SMA · EMA · S/R
      │                                          ├── Ensemble Forecast
      │                                          │     Prophet + SARIMAX + Random Forest
      │                                          ├── Monte Carlo (1 000 paths, seed=42)
      │                                          ├── VADER Sentiment (headline scoring)
      │                                          └── LangGraph Jury (3 analysts, parallel)
      │                                                Llama 4 Scout · Llama 3.3 70B · Qwen3 32B
      ├── GET  /api/dcf/[symbol] ───────────► FastAPI /dcf/{symbol}
      ├── GET  /api/options/[symbol] ───────► FastAPI /options/{symbol}
      ├── POST /api/trade-setup ────────────► FastAPI /trade-setup
      └── POST /api/chat (SSE) ─────────────► FastAPI /chat
```

### Backend Structure (post router-split)

```
backend/
├── main.py              # ~50-line entry point (lifespan + include_router × 4)
├── dependencies.py      # Service singletons shared across routers
├── routers/
│   ├── predict.py       # /health · /debug · /predict · /sparklines · /compare
│   ├── simulation.py    # /simulation/*
│   ├── trade.py         # /trade-setup · /chat
│   └── market.py        # /dcf/{symbol} · /options/{symbol}
├── services.py          # YFinanceService · InfluxService · SerpService · SentimentService · AnalystJuryService
├── jury_graph.py        # LangGraph StateGraph — parallel analyst fan-out
├── models.py            # Pydantic schemas + run_monte_carlo
├── simulation_service.py
├── mcp_server.py        # FastMCP — predict/sparklines/health as Claude Code tools
└── config.py
```

---

## CI/CD

| Trigger | Pipeline | Deploys To |
|---------|----------|------------|
| Pull Request | Lint, TypeScript, build, Docker smoke test | Preview (`fiforesight-preview.duckdns.org`) |
| Merge to main | Semantic version, GitHub release, full build + deploy | Prod (`fiforesight.duckdns.org` + Koyeb) |

---

## Disclaimer

This tool is for educational and informational purposes only. It is not financial advice. Financial markets involve significant risk — always perform your own due diligence before making any investment decisions.
