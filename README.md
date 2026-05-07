# FiForesight

[![Build](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/pull-request.yml/badge.svg)](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/pull-request.yml)
[![Build and Deploy](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/merge.yml/badge.svg)](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/merge.yml)
[![Daily RL Training](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/daily-train.yml/badge.svg)](https://github.com/WeekendDevelopment/FiForesight/actions/workflows/daily-train.yml)

AI-driven quantitative financial forecasting SaaS. Enter a ticker symbol and get an ensemble ML forecast (48-hour price range), technical indicators, a 3-analyst LLM jury verdict, and live news — all in one dashboard.

## Current Features

- **Ensemble ML Forecasting** — Prophet + SARIMAX + Random Forest with dynamic inverse-error weighting
- **Technical Indicators** — RSI, MACD, Bollinger Bands, SMA 50/200, Support/Resistance levels
- **LLM Analyst Jury** — 3 independent AI analysts (Kimi K2, Llama 3.3 70B, Qwen3 32B) each provide a verdict, confidence score, reasoning, and target prices via Groq API
- **Live News & Trending** — SerpAPI-powered news headlines and trending tickers
- **Interactive Charts** — Candlestick/line charts with RSI, MACD, and Bollinger Band sub-panels (Recharts)
- **Dark/Light Theme** — Toggle between themes with MUI theming
- **Ticker Autocomplete** — Search across major exchanges
- **Time-Series Database** — Persistent market data storage using InfluxDB with yfinance fallback
- **Observability** — New Relic APM for backend and frontend monitoring

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript 6, MUI 7, Recharts 3, Tailwind CSS 4 |
| Backend | Python 3.12, FastAPI, Uvicorn |
| ML | Prophet, SARIMAX (statsmodels), Random Forest (scikit-learn) |
| AI | Groq API — Kimi K2, Llama 3.3 70B, Qwen3 32B |
| Data | yfinance, InfluxDB, SerpAPI |
| Observability | New Relic APM |
| Infra | Docker, Terraform, GitHub Actions, Koyeb, Oracle Cloud |

## Getting Started

### Prerequisites

- Node.js 18+ (LTS)
- Python 3.12+
- pnpm
- InfluxDB instance (optional — yfinance fallback works without it)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/WeekendDevelopment/FiForesight.git
   cd FiForesight
   ```

2. **Install dependencies:**
   ```bash
   pnpm install
   pip install -r backend/requirements.txt
   ```

3. **Configure environment variables** — create `backend/.env`:
   ```env
   INFLUXDB_URL=http://localhost:8086
   INFLUXDB_TOKEN=your_influx_token
   INFLUXDB_ORG=WeekendDevelopment
   INFLUXDB_BUCKET=FiForesightBucket
   GROQ_API_KEY=your_groq_key        # Required — LLM analyst jury
   SERP_API_KEY=your_serpapi_key      # Optional — news/trending
   PORT=8000
   ```

4. **Run the application:**
   ```bash
   pnpm run app:dev
   ```
   This starts both the FastAPI backend (port 8000) and Next.js frontend (port 3000) concurrently.

   Or run individually:
   ```bash
   # Frontend
   cd frontend && pnpm run dev

   # Backend
   python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
   ```

5. Open http://localhost:3000

## Architecture

```
Browser --> Next.js /api/predict (proxy) --> FastAPI /predict
              |                                   |
              |                                   |-- InfluxDB (cached 2Y OHLCV)
              |                                   |     \-- yfinance (fallback)
              |                                   |-- Technical Indicators (RSI, MACD, BB, SMA, S/R)
              |                                   |-- Ensemble Forecast (Prophet + SARIMA + RF)
              |                                   |-- Groq LLM Jury (3 analysts, concurrent)
              |                                   \-- SerpAPI (news + trending)
              |
              \-- Recharts (candlestick, RSI, MACD, BB/SMA overlays)
                  \-- AnalystJuryPanel (3 verdict cards)
```

## CI/CD

| Trigger | Pipeline | Deploys To |
|---------|----------|------------|
| Pull Request | Lint, build, Docker smoke test | Preview (fiforesight-preview.duckdns.org) |
| Merge to main | Semantic version, GitHub release, full build | Prod (fiforesight.duckdns.org + Koyeb) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (`{status: "ok"}`) |
| GET | `/debug` | Diagnostic check of all dependencies |
| POST | `/predict` | Main prediction — accepts `{symbol: "AAPL"}`, returns forecast + indicators + jury verdicts + news |

## Project Roadmap

Tracked in Jira project **FIFO**. See [`.claude/FiForesight_Roadmap.md`](.claude/FiForesight_Roadmap.md) for details.

| Epic | Description | Progress |
|------|-------------|----------|
| ML & Forecasting (FIFO-5) | Indicators, model tuning, accuracy tracking | 1/3 |
| News & Sentiment (FIFO-6) | SerpAPI, FinBERT/VADER, AI notes | 0/3 |
| Infrastructure (FIFO-32) | HTTPS, CI/CD hardening, monitoring | 0/3 |
| Testing & Quality (FIFO-33) | pytest, Vitest, Playwright, coverage gates | 0/3 |
| Frontend Architecture (FIFO-34) | Component decomposition, a11y, perf | 0/3 |
| User Auth (FIFO-35) | Supabase, watchlists, alerts | 0/2 |
| LLM Analyst Jury (FIFO-101) | Multi-model jury, self-hosted LLM, fine-tuning | 1/3 |

---

*Disclaimer: This tool is for educational purposes only. Financial markets involve risk. Always perform your own due diligence before making investment decisions.*
