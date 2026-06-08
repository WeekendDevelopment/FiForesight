# FiForesight Roadmap

> Source of truth for planned work. Feature-based, free-tier only.
> Last synced: 2026-06-08 — All Features 5–8 shipped. Phase C items (L2, jury tools, backtester) also shipped. No open Next Up items — backlog is Phases A/B and Quick Wins.

---

## Shipped

### Forecasting & Quant
- Ensemble forecast: Prophet + SARIMAX + RandomForest
- Technical indicators: RSI, MACD, Bollinger Bands, SMA50/200, Support/Resistance
- Historical forecast tracking & per-model accuracy/MAE (`ForecastTrackingService`)
- Monte Carlo GBM simulation — 1000 paths, VaR-95, p10/p50/p90, fan chart + 3D surface
- Volume Profile panel
- Dynamic chart time intervals (1D/5D/1M/3M/6M/1Y/2Y) — `GET /history`, VWAP overlay, contextual metrics (#208)
- Chart zoom/pan across all intervals — drop classic view, AdvancedChart timestamp hardening (#221)
- Walk-forward backtester — rolling 252-day train → 5-day predict, per-model MAE + directional accuracy (#222)

### Intelligence
- 3-model LLM Analyst Jury (Llama 4 Scout, Llama 3.3 70B, GPT-OSS 20B) via Groq + LangGraph
- VADER sentiment scoring on news headlines
- Stock Chat Agent — SSE streaming via `POST /chat`
- Trade Setup Generator — entry/stop/3 targets + R:R + Groq rationale
- Tool-using jury agents — Groq function calling; tools: `get_vix`, `get_put_call_ratio`, `get_insider_flow`, `get_macro_snapshot`; jury re-analysis UI (#220)
- Jury quant lens swapped to `openai/gpt-oss-20b`; verdict parsing hardened; malformed output tracked (#226)

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
- "Why did this move?" explainer — `WhyDidMoveCard`, >3% trigger, fallback to top headline (#205)
- Sector heatmap — `SectorHeatmap`, `GET /sectors`, 11 SPDR ETFs (#205)
- Level 2 order book — `OrderBookPanel`, Alpaca Markets (US equities) + Coinbase (crypto) (#209)
- URL-persistent analysis tab — `?symbol=` param, `router.replace` after predict, watchlist quick-launch (#228)
- VWAP intraday overlay — dashed line + ±1σ bands on 1D/5D intervals (#228)

### Navigation & Architecture
- App Shell sidebar — collapsible, mobile bottom nav, `AppShellContext`, theme + auth in footer (#223)
- Landing page — lightweight: MorningBriefingPanel + SectorHeatmap + TrendingSparklines + search (#223)
- Standalone Options Chain tab (`/options`) — self-fetching `OptionsChainPanel`, symbol search (#225)
- Earnings Calendar tab (`/earnings`) — top 60 S&P 500, top 8/day, Redis 6h TTL (#225)
- Options Greeks (Δ, Θ) + aggregate stats (IV, put/call ratio, IV skew) (#225)
- Expiry selector on options chain (#225)

- IPO Tracker tab (`/ipo`) — FMP primary + SEC EDGAR S-1 fallback, upcoming 90d + recent 30d, Redis 4h TTL, responsive card grid, status chips, SEC EDGAR links, AbortController on unmount (no PR — pushed direct to main)

### Auth & Backend
- Supabase email/password auth — `AuthContext`, `AuthModal`, watchlist groundwork (#193)
- Backend pytest harness — 22 tests, no network calls (`backend/tests/`) (#192)
- Router split — `main.py` → `routers/predict.py`, `simulation.py`, `trade.py`, `market.py` (#195)
- App-tester QA fixes — jury consensus, DCF edge cases, SerpAPI, StockTwits, order book (#211)
- Groq quota-exhaustion resilience — failure caching (5 min TTL), LangGraph fallback under New Relic (#208)

### Infra
- Redis caching layer (`redis_cache.py`)
- InfluxDB OHLCV cache (2Y)
- New Relic APM (backend + frontend)
- HTTPS, Docker multi-stage, Koyeb + Oracle Cloud deploys
- GitHub Actions: PR preview + prod deploy; Alpaca + FMP API keys wired through deploy pipeline (#209 + workflow updates)
- FastMCP server (`mcp_server.py`)

---

## Next Up

> All planned Features 5–8 are shipped. The next work items are Quick Wins (QW-1) and Phase A/B backlog below.


## Quick Wins

### QW-1 · Intraday Sparklines (replace static trending ticker list)
**Current:** `TrendingSparklines` shows a hardcoded popular ticker list with static
multi-day sparklines and % change from SerpAPI weekly data.

**Desired:** Replace with **1 trading day / last trading day intraday bars**
(`period="1d", interval="5m"`) — each mini-chart shows the actual intraday price path.

- **Backend** — extend `GET /sparklines` (in `routers/predict.py`) or new
  `GET /sparklines/intraday`. Per ticker: `yf.download(t, period="1d", interval="5m")`.
  Return `{ symbol, prices: [float], change_pct, current_price }`. Redis 5-min TTL.
  `asyncio.wait_for(timeout=12)`.
- **Frontend** — `TrendingSparklines.tsx`: swap data source to new endpoint.
  Label change: "Trending" → "Today" (or "Last Session" if market closed).
  % change = (last bar − first bar) / first bar for the session.
- **Dynamic list (optional):** pull from SerpAPI trending symbols + SPY/QQQ/BTC-USD
  as anchors so the strip reflects what's actually moving, not a hardcoded list.
- One backend change propagates to both landing page and analysis page sidebar.

**Files:** `backend/routers/predict.py` (or `market.py`), `frontend/components/TrendingSparklines.tsx`, `frontend/app/api/sparklines/route.ts`
**Effort:** ½ day

---

## Phase A Backlog — More Signal, Same Stack
> Research complete (2026-06-06). Prompt written. No new APIs required.

| Feature | Value | Effort | Notes |
|---|---|---|---|
| ATR (Average True Range) → adaptive stops | High | Low | Replace flat % stops in TradeSetup; `stop = entry ± 2×ATR` |
| RSI + MACD divergence detection | High | Med | `scipy.signal.find_peaks`; annotate chart; inject into jury context |
| Earnings surprise history | High | Low | `yf.Ticker().earnings_history` → last 4Q EPS beat/miss table |
| RandomForest feature importance | Med | Low | `rf.feature_importances_` post-fit → top-5 bar chart |

> Note: Options Greeks + IV rank + put/call ratio are partially shipped in PR #225.

---

## Phase B Backlog — New Data Sources
> Research complete (2026-06-06). Prompt written.

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Insider transactions (SEC EDGAR Form 4) | High | Med | Free, no key — `efts.sec.gov`; last 10 Form 4 filings per ticker |
| FRED macro context → jury prompts | High | Med | `DGS10`, `CPIAUCSL`, `UNRATE`, `FEDFUNDS`, `T10Y2Y`; inject into analyst system prompt |
| Regime detection (HMM via `hmmlearn`) | High | Med | 3-state Gaussian HMM on returns + vol; label badge on jury panel |
| Jury dissent surfacing | Med | Low | When split 2-1, extract minority rationale → amber "Dissenting View" card |
| Reddit sentiment (PRAW — free) | Med | High | `r/wallstreetbets` + `r/stocks` mention count + VADER; needs Reddit API account |
| Google Trends signal (`pytrends`) | Med | Med | Relative search interest for `"{symbol} stock"`; fragile but free |

---

## Phase C Backlog — New Architecture
> Research complete (2026-06-06). Prompt written.
> ✅ Level 2 order book, tool-using jury agents, and walk-forward backtester already shipped (PRs #209, #220, #222).

| Feature | Value | Effort | Status | Notes |
|---|---|---|---|---|
| ~~Level 2 order book~~ | ~~High~~ | ~~High~~ | ✅ Shipped #209 | Alpaca (US equities) + Coinbase (crypto) |
| ~~Tool-using jury agents~~ | ~~High~~ | ~~High~~ | ✅ Shipped #220 | Groq function calling; `get_vix`, `get_put_call_ratio`, `get_insider_flow`, `get_macro_snapshot` |
| ~~Walk-forward backtester~~ | ~~High~~ | ~~High~~ | ✅ Shipped #222 | Rolling 252-day train → 5-day predict; per-model MAE + directional accuracy |
| Custom alert rule builder | High | High | Pending | Needs auth + background worker |
| Isolation Forest anomaly detection | Med | High | Pending | Flag statistical outliers in price/volume |
| Pattern detection (`scipy.signal.find_peaks`) | Med | Med | Pending | Head & shoulders, double top/bottom, flag/pennant |

---

## Feature Ideas (longer horizon)

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Watchlist persistence (Supabase) | High | Med | Auth shipped; watchlist UI is second pass |
| Daily briefing email / push | High | High | Needs worker + Supabase edge function |
| Multi-ticker overlay comparison | Med | Low | Ratio chart (stock vs SPY); rolling correlation |
| International markets | Med | Med | yfinance supports non-US tickers |
| Macro dashboard (FRED — standalone `/macro` tab) | Med | Med | GDP, CPI, rates, yield curve |
| Earnings call transcript sentiment | Med | High | SEC EDGAR free; NLP on 10-Q/8-K filings |
| Short interest tracker | Med | Med | FINRA ATS transparency (free weekly data) |

---

## Free-Tier Constraint

All features use free APIs / free tiers / self-hosted:

| Source | Usage | Key Required |
|---|---|---|
| **yfinance** | Market data, history, fundamentals | No |
| **SerpAPI** | News headlines, trending symbols | Yes (free tier) |
| **Groq** | LLM jury (Llama 4 Scout, Llama 3.3 70B, GPT-OSS 20B) | Yes (free tier) |
| **VADER** | Headline sentiment scoring | No (local) |
| **Supabase** | Auth + watchlist persistence | Yes (free tier) |
| **FRED API** | Macro indicators (Phase B) | No (read-only) |
| **SEC EDGAR** | Form 4 insider filings, S-1 IPO filings | No |
| **FMP** | IPO calendar (Feature 8) | Yes (free tier, 250 req/day) |
| **Alpaca** | Level 2 order book — US equities | Yes (free paper trading) |
| **Coinbase** | Level 2 order book — crypto | No (public WebSocket) |
| **PRAW / Reddit** | Social sentiment (Phase B) | Yes (free dev account) |
| **InfluxDB** | OHLCV time-series cache | Self-hosted (Oracle) |
| **Redis** | Response caching | Self-hosted |
| **Koyeb + Oracle Cloud** | Hosting | Free tiers |
