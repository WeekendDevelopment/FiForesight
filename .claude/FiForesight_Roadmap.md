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

- IPO Tracker tab (`/ipo`) — free **Nasdaq** IPO calendar (primary) → **SEC EDGAR** S-1 fallback, **no API key**. Upcoming 90d + recent 30d, Redis 4h TTL (`?refresh=true` to bypass), responsive card grid, status chips, `/analysis` links, AbortController on unmount. FMP was dropped (it retired its free IPO calendar 2025-08-31). (`#229`, `#231`)

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
- GitHub Actions: PR preview + prod deploy; Alpaca API keys wired through deploy pipeline (#209 + workflow updates)
- FastMCP server (`mcp_server.py`)

---

## Backlog

> Single flat list of everything not yet built. Add new items here as they come up.
> Tag format: `[Value: High/Med/Low]` `[Effort: Low/Med/High]` `[Needs: any external account/key]`

### Signals & Indicators
- ATR (Average True Range) → adaptive stops in Trade Setup — replace flat % offset with `stop = entry ± 2×ATR` · `[Value: High]` `[Effort: Low]`
- RSI + MACD divergence detection — `scipy.signal.find_peaks`; annotate chart; inject into jury context · `[Value: High]` `[Effort: Med]`
- Earnings surprise history — `yf.Ticker().earnings_history` → last 4Q EPS beat/miss table in FundamentalsPanel · `[Value: High]` `[Effort: Low]`
- RandomForest feature importance — `rf.feature_importances_` post-fit → top-5 bar chart below ModelWeightBar · `[Value: Med]` `[Effort: Low]`
- Ichimoku Cloud overlay — Tenkan/Kijun/Senkou A&B/Chikou; comprehensive single-chart trend system · `[Value: Med]` `[Effort: Med]`
- Stochastic Oscillator — overbought/oversold confirmation alongside RSI · `[Value: Med]` `[Effort: Low]`
- ADX (Average Directional Index) — trend strength; flag when trend is weak (RSI signals less reliable) · `[Value: Med]` `[Effort: Low]`
- OBV (On-Balance Volume) — volume accumulation/distribution divergence signal · `[Value: Med]` `[Effort: Low]`
- Fibonacci retracement levels — auto-calculated from swing high/low; overlay on price chart · `[Value: Med]` `[Effort: Med]`

### Intelligence & AI
- Jury dissent surfacing — when split 2-1, extract minority rationale → amber "Dissenting View" card in AnalystJuryPanel · `[Value: Med]` `[Effort: Low]`
- Regime detection (HMM via `hmmlearn`) — 3-state Gaussian HMM on returns + vol; trending_up / ranging / trending_down badge on jury panel · `[Value: High]` `[Effort: Med]`
- Market regime → model weight adjustment — in trending regime favour SARIMAX; in ranging favour RF; surface recommendation · `[Value: High]` `[Effort: Med]`

### New Data Sources
- Insider transactions (SEC EDGAR Form 4) — free, no key; `efts.sec.gov`; last 10 Form 4 filings per ticker; buy/sell colour-coded table · `[Value: High]` `[Effort: Med]`
- FRED macro context → jury prompts — `DGS10`, `CPIAUCSL`, `UNRATE`, `FEDFUNDS`, `T10Y2Y`; inject current values + 30d delta into each analyst system prompt · `[Value: High]` `[Effort: Med]`
- Reddit sentiment (PRAW) — `r/wallstreetbets` + `r/stocks` mention count + VADER delta; needs Reddit API account · `[Value: Med]` `[Effort: High]` `[Needs: Reddit dev account]`
- Google Trends signal (`pytrends`) — relative search interest for `"{symbol} stock"`; sparkline + trend direction; fragile but free · `[Value: Med]` `[Effort: Med]`
- Short interest tracker — FINRA ATS transparency data (free, weekly); days-to-cover ratio · `[Value: Med]` `[Effort: Med]`
- Earnings call transcript sentiment — SEC EDGAR free; NLP on 10-Q/8-K filings · `[Value: Med]` `[Effort: High]`

### UX & Data Display
- Intraday sparklines (QW-1) — replace static trending ticker list with 1-day `5m` bars; "Today" label; dynamic list from SerpAPI trending + SPY/QQQ/BTC anchors · `[Value: High]` `[Effort: Low]` · *Files: `TrendingSparklines.tsx`, `GET /sparklines` endpoint*
- Watchlist persistence (Supabase) — auth is shipped; save/load watchlist tickers to Supabase; sync across devices · `[Value: High]` `[Effort: Med]`
- Multi-ticker overlay comparison — ratio chart (stock vs SPY); rolling 30d correlation line · `[Value: Med]` `[Effort: Low]`
- Macro dashboard (`/macro` tab) — standalone FRED tab: GDP, CPI, rates, yield curve, fed dot plot · `[Value: Med]` `[Effort: Med]`
- International markets — yfinance supports non-US tickers; exchange detection already exists · `[Value: Med]` `[Effort: Med]`
- Analyst price target range — `yf.Ticker().analyst_price_targets` → low/mean/high bar in FundamentalsPanel · `[Value: Med]` `[Effort: Low]`

### Architecture & Infra
- Custom alert rule builder — price cross, RSI threshold, % move triggers; needs auth + background worker + notification channel · `[Value: High]` `[Effort: High]`
- Daily briefing email / push — scheduled Supabase edge function; morning summary digest · `[Value: High]` `[Effort: High]`
- Pattern detection (`scipy.signal.find_peaks`) — head & shoulders, double top/bottom, flag/pennant; annotate chart · `[Value: Med]` `[Effort: Med]`
- Isolation Forest anomaly detection — flag statistical outliers in price/volume series · `[Value: Med]` `[Effort: High]`

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
| **Nasdaq** | IPO calendar — free upcoming + recent (primary) | No (browser UA) |
| **Alpaca** | Level 2 order book — US equities | Yes (free paper trading) |
| **Coinbase** | Level 2 order book — crypto | No (public WebSocket) |
| **PRAW / Reddit** | Social sentiment (Phase B) | Yes (free dev account) |
| **InfluxDB** | OHLCV time-series cache | Self-hosted (Oracle) |
| **Redis** | Response caching | Self-hosted |
| **Koyeb + Oracle Cloud** | Hosting | Free tiers |
