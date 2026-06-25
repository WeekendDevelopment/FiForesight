# FiForesight Roadmap

> Source of truth for planned work. Feature-based, free-tier only.
> Last synced: 2026-06-12 — F11/F12/F10 shipped. F13 (Watchlist + Intraday Sparklines + Responsive) shipped. F9 (Alerts) remains.

> **Planning vs. implementation sessions:** In a *planning/roadmap* session (proposing features,
> reviewing capabilities, editing this backlog), changes are limited to docs + generated
> implementation prompts — application code is left to the *implementation* session that builds the
> feature, to avoid branch/PR confusion. This is scoped to session type, not a blanket rule.

---

## Definition of Done (applies to Feature 9 onward)

Documentation is part of the feature, not an afterthought. A feature PR is **not done** until all five exist:
1. **Roadmap** — item moved from committed/Backlog → Shipped with PR #.
2. **`CLAUDE.md`** — new endpoints added to Data Flow; new env vars; new gotchas/decisions.
3. **`/docs/FiForesight-Documentation.md`** — a section for the feature (and fix the stale `/compare` "stub" claim at line ~1061 as the first instance).
4. **API contract** — request/response shape documented in the PR description.
5. **Tests** — each new endpoint ships ≥1 integration test (also closes the audit's coverage gaps).

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
- Advanced Technical Signals (Feature 14): ATR-14 volatility-adaptive trade stops (2.0×/2.5×, 8% cap), RSI/MACD divergence detection (scipy `find_peaks`, injected into jury context + prompts), earnings surprise history (last 4Q), RF feature importance (top-5), and Stochastic/ADX/OBV sub-panels (`SignalPanels`, localStorage-persisted). New helpers in `models.py`; `indicators` payload extended; 19 new backend tests. (#260)
- Fibonacci Retracement overlay (Feature 25): swing-high/low auto-detection → 7 retracement levels in the /predict indicators payload + toggleable dashed overlay on PriceChartCard. New `calculate_fibonacci_levels` helper in models.py.

### Intelligence
- 3-model LLM Analyst Jury (Llama 4 Scout, Llama 3.3 70B, GPT-OSS 20B) via Groq + LangGraph
- VADER sentiment scoring on news headlines
- Stock Chat Agent — SSE streaming via `POST /chat`
- Trade Setup Generator — entry/stop/3 targets + R:R + Groq rationale
- Tool-using jury agents — Groq function calling; tools: `get_vix`, `get_put_call_ratio`, `get_insider_flow`, `get_macro_snapshot`; jury re-analysis UI (#220)
- Jury quant lens swapped to `openai/gpt-oss-20b`; verdict parsing hardened; malformed output tracked (#226)
- Forecast Accuracy & Sentiment Analytics Dashboard — `/insights` tab + `GET /analytics/{accuracy,sentiment}/{symbol}`; persists VADER compound to new `sentiment_score` measurement (Feature 12, PR #244)
- Portfolio Manager — real holdings + live P&L ("My Portfolio" tab) + `GET/POST/DELETE /portfolio/holdings` + `GET /portfolio/summary` (Supabase `holdings` + RLS); existing race sim renamed "Simulator" (Feature 10, PR #249)
- Analyst price targets card — Wall St. mean/low/high range bar + rating breakdown (Feature 21, PR #267)
- Gap Explainer — auto-detects ≥3% daily moves, surfaces top headlines + Groq one-sentence explanation in a banner above the chart (F22)

- Watchlist persistence + intraday sparklines + responsive design (Feature 13): `watchlists` Supabase table, `/watchlist` CRUD, intraday 5m bars on `/sparklines`, `WatchlistContext`, sidebar watchlist panel, mobile bottom chip bar, full responsive audit across all tabs (320px–4K). 13 new backend tests. (#pending-F13)

- Alternative Data Sources (Feature 15): three free, keyless feeds. **FRED macro** (`FREDService`) — DGS10/CPIAUCSL/UNRATE/FEDFUNDS/T10Y2Y value+30d-delta snapshot, injected into all 3 jury prompts + new `/macro` dashboard tab (`GET /macro/snapshot`, 1h cache). **SEC EDGAR Form 4 insider** (`InsiderService`) — last 10 filings per ticker, `InsiderTransactionsCard` + `GET /insider/{symbol}` + `insiderTransactions` on `/predict`. **FINRA short interest** (`ShortInterestService`) — weekly short-volume → short % / days-to-cover in `FundamentalsPanel` + `shortInterest` on `/predict`. `FRED_API_KEY` optional. 21 new backend tests. (#pending-F15)

- Market Regime Intelligence (Feature 16): per-ticker **3-state Gaussian HMM** (`RegimeService`, `hmmlearn`) on the last 60 bars (features: daily log return + 5-day realised-vol proxy, standardised) → `trending_up` / `ranging` / `trending_down` (+ `unknown` fallback), Redis-cached 4h. **Regime-adaptive ensemble weights** (`adjust_weights_for_regime` in `models.py`): SARIMA boosted in trending, RF in ranging, scaled by confidence — wired into `run_ensemble_forecast`; live weights flow to `ModelWeightBar`. Regime injected into jury context + all 3 persona prompts; persisted to new `market_regime` InfluxDB measurement. **`RegimeBadge`** on the jury panel + Monte-Carlo subtitle, and **jury dissent surfacing** (`detect_dissent`) — amber Alert on a 2-1 split. `regime` + `juryDissent` added to `/predict`; `juryDissent` to `/jury/reanalyze`. 16 new backend tests. (#pending-F16)

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
- Sector heatmap — `SectorHeatmap`, `GET /sectors`, 11 SPDR ETFs (#205) — _superseded by F23_
- Sector heatmap (F23) — single `GET /sectors/heatmap` + one `SectorHeatmapPanel` (full `/sectors` tab with 1D/5D toggle + compact interactive landing overview); click-to-load ticker. Legacy `/sectors` endpoint/component removed.
- Equity Screener (`/screener`) — curated 50-stock universe filtered by sector, PE, RSI, beta, dividend yield; 1h Redis cache; sortable results table (F24)
- Interactive dashboard widgets — Market Pulse + Trending tiles are click-to-analyze (indices like `^VIX` stay static); `SectorContextChip` on the analysis page links each stock to its sector ETF's move (yfinance sector → ETF).
- Level 2 order book — `OrderBookPanel`, Alpaca Markets (US equities) + Coinbase (crypto) (#209)
- URL-persistent analysis tab — `?symbol=` param, `router.replace` after predict, watchlist quick-launch (#228)
- VWAP intraday overlay — dashed line + ±1σ bands on 1D/5D intervals (#228)
- Dividend & Income card (Feature 26): `GET /dividends/{symbol}` (yfinance, Redis 6h) + `DividendIncomeCard` — forward yield, annual rate, payout ratio, 5-yr avg yield, ex-date, YoY growth; clean non-payer empty state.
- Sector Rotation leaderboard (Feature 27): `GET /sectors/rotation` (11 GICS ETFs' relative strength vs SPY over 1M/3M/6M + RRG-lite quadrant, Redis 1h) + `/rotation` page (leaderboard table + quadrant scatter, click-to-analyze). Reuses the heatmap batch-download machinery.

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
- Security hardening — slowapi rate limits on all endpoints, auth enforcement (`require_user` on `/trade-setup` + `/jury/reanalyze`), CORS (`ALLOWED_ORIGINS`), symbol input validation (regex), `/chat` prompt-injection guards (500-char cap, control-char sanitization, hardened system prompt), JWT signature verification (`SUPABASE_JWT_SECRET`), observability logging on silent exceptions. 99 tests, ruff clean. (#235)

### Infra
- Redis caching layer (`redis_cache.py`)
- InfluxDB OHLCV cache (2Y)
- New Relic APM (backend + frontend)
- HTTPS, Docker multi-stage, Koyeb + Oracle Cloud deploys
- GitHub Actions: PR preview + prod deploy; Alpaca API keys wired through deploy pipeline (#209 + workflow updates)
- FastMCP server (`mcp_server.py`)

---

## Next Up — Features 9–12 (committed 2026-06-08)

> Build order: **F11 → F12 → F10 → F9**. Harden first (gates user-data features), then ship the high-trust dashboard, then the portfolio manager, then alerts (depend on auth + holdings).

### Feature 11 · Security Hardening *(do first)*
**Branch:** `feat/security-hardening`
**Problem:** Backend auth is frontend-only; `/predict`, `/chat`, `/jury/reanalyze`, `/trade-setup` are public and unthrottled; `/chat` is prompt-injectable; CORS is open.
- **Auth enforcement** — require Bearer token on compute-heavy endpoints via existing `get_user_id` in `dependencies.py`; keep read-only market endpoints public or soft-gated.
- **Rate limiting** — add `slowapi`; per-IP quotas (e.g. `/predict` 10/min, `/chat` 20/min); 429 + `Retry-After`.
- **Prompt-injection guards** (`routers/trade.py` `/chat`) — cap `message` length (≤500 chars), sanitize `symbol`/context before interpolation, harden system prompt against instruction-override.
- **CORS** — `CORSMiddleware` restricted to known frontend origins.
- **Input validation** — apply existing `_validate_tag` regex to all user symbols (`/predict` currently only `.upper()`s).
- **Observability** — `logger.debug` on the 9 silent-failure handlers (`market.py:414,629,680`, `trade.py:279`, `services.py:941`, etc.).
- **JWT** — require signature verification when `SUPABASE_JWT_SECRET` set; warn loudly when not.

**Files:** `backend/main.py` (CORS), `backend/dependencies.py`, `backend/routers/{predict,trade,market}.py`, `backend/requirements.txt` (+slowapi)
**Complexity:** Medium

### Feature 12 · Forecast Accuracy & Sentiment Analytics Dashboard ✅ *SHIPPED (PR #244)*
**Branch:** `feat/accuracy-sentiment-dashboard`
**Problem:** Forecast-accuracy data is already collected in InfluxDB but never shown; sentiment is never persisted.
- **Backend** — new `GET /analytics/accuracy/{symbol}` reading `ForecastStore.query_model_accuracy`, `query_ensemble_mae`, `query_forecast_records` + `query_price_outcomes`: per-model MAE trend, ensemble MAE by horizon (d1–d5), directional accuracy %, forecast equity curve.
- **Sentiment history** — write VADER compound per ticker to a new InfluxDB `sentiment_score` measurement on each `/predict`; new `GET /analytics/sentiment/{symbol}` returns the trend.
- **Frontend** — new `/insights` tab: accuracy timeline, model-performance ranking, ensemble-confidence-by-horizon chart, sentiment trend line.
- **Reuse** — Recharts; Redis-cache analytics queries (15-min TTL).

**Files:** new `backend/routers/analytics.py`, `backend/services.py` (sentiment write), `frontend/app/(app)/insights/page.tsx`, proxies
**Complexity:** Low–Medium *(data already exists)*

### Feature 10 · Portfolio Manager ✅ *SHIPPED (PR #249)*
**Branch:** `feat/portfolio-manager`
**Problem:** Current "portfolio" only backtests hypotheticals; no real holdings or live P&L.
- **Naming** — the existing `/simulation` race tab (was mislabeled "Portfolio") renamed **"Simulator"**; the new real-holdings tab is **"My Portfolio"** (`/portfolio`). Endpoints + labels kept clearly distinct.
- **Schema** — Supabase `holdings(id, user_id, symbol, shares, cost_basis, opened_at)` + `unique(user_id, symbol)` with RLS `auth.uid() = user_id` (`supabase/migrations/0001_holdings.sql`).
- **Backend** — `GET/POST/DELETE /portfolio/holdings` (auth-gated via `require_user`, reads/writes Supabase PostgREST with the caller's forwarded JWT → RLS, no service-role key); `GET /portfolio/summary` → live prices, per-holding + total P&L, sector allocation, HHI diversification score, lightweight market-value-weighted trend forecast (NOT full ensemble/jury — too costly per holding); skips bad symbols, Redis-cached 15min.
- **Frontend** — `/portfolio` tab: summary cards, holdings table (add/remove), sector pie, forecast badge, AuthGate when signed out; `lib/holdings.ts` + `/api/portfolio/*` proxies.
- **Tests** — `backend/tests/test_portfolio.py` (auth 401, P&L math, partial-failure skip, trend signal).
- **Edge cases** — splits/dividends/multi-currency documented as out-of-scope v1.

**Files:** `backend/routers/portfolio.py`, `backend/portfolio_service.py`, `backend/supabase_rest.py`, `supabase/migrations/0001_holdings.sql`, `frontend/app/(app)/portfolio/page.tsx`, `frontend/lib/holdings.ts`, `/api/portfolio/*` proxies, sidebar nav rename
**Complexity:** Medium–High

### Feature 9 · Alerts & Notifications ✅ *SHIPPED (PR #254)*
**Branch:** `feat/alerts-notifications`
**Problem:** Engagement is pull-only; no proactive signals.
- **Schema** — Supabase `alert_rules(id, user_id, symbol, type, operator, threshold, active, last_fired, created_at)` + `alert_fires` (fire log) + `push_subscriptions` (Web Push); types: `price_cross`, `rsi_threshold`, `pct_move`, `earnings_soon`, `forecast_breakout`. RLS `auth.uid() = user_id` (`supabase/migrations/0003_alerts.sql` + `0004_push_subscriptions.sql`).
- **Backend CRUD** — `GET/POST/PATCH/DELETE /alerts/rules`, `GET /alerts/fires`, `POST /alerts/subscribe|unsubscribe`, `GET /alerts/vapid-public-key` — all auth-gated via `require_user`, reading/writing via the caller's forwarded JWT (RLS), through `alerts_store.py`.
- **Evaluator** — `alerts_evaluator.evaluate_alerts()` loads all active rules **cross-user via the service-role key** (the one place RLS is bypassed; never user-facing), groups by symbol, runs a pure `evaluate_rule()` per type, fires outside a 6h cooldown (`ALERT_COOLDOWN_HOURS`), records a fire + stamps `last_fired`. One bad symbol never aborts the batch.
- **Delivery** — Web Push via `pywebpush` + a server **VAPID** key pair (free, service worker at `frontend/public/sw.js`); optional Resend email fallback (`ALERT_EMAIL_ENABLED`). Daily digest (`/alerts/digest`) reuses `/briefing` + holdings movers.
- **Scheduling** — NO sleep loop: internal `POST /alerts/evaluate` (15-min) + `/alerts/digest` (daily) guarded by an `X-Cron-Secret` header (`CRON_SECRET`, fail-closed). Driven by GitHub Actions cron / Supabase scheduled function / cron+curl.
- **Frontend** — `/alerts` tab: adaptive rule builder, active-rules list (toggle/delete), fire history, "enable browser notifications" Web-Push flow; `lib/alerts.ts` + `/api/alerts/*` proxies.
- **Tests** — `backend/tests/test_alerts.py` (CRUD auth 401, per-type firing logic, cooldown suppression, cron-secret rejection, bad-symbol resilience).

**Files:** `backend/routers/alerts.py`, `backend/alerts_store.py`, `backend/alerts_evaluator.py`, `backend/notifications.py`, `supabase/migrations/0003_alerts.sql` + `0004_push_subscriptions.sql`, `frontend/app/(app)/alerts/page.tsx`, `frontend/lib/alerts.ts`, `frontend/public/sw.js`, `/api/alerts/*` proxies, sidebar nav
**Complexity:** High

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

### Intelligence & AI
- ~~Jury dissent surfacing~~ ✅ SHIPPED (Feature 16) — `detect_dissent` (2-1 split → minority rationale), amber "Dissenting View" Alert in `AnalystJuryPanel`
- ~~Regime detection (HMM via `hmmlearn`)~~ ✅ SHIPPED (Feature 16) — `RegimeService` 3-state Gaussian HMM, `RegimeBadge` on jury panel + Monte-Carlo subtitle
- ~~Market regime → model weight adjustment~~ ✅ SHIPPED (Feature 16) — `adjust_weights_for_regime` (SARIMA in trending, RF in ranging, confidence-scaled), live weights in `ModelWeightBar`

### New Data Sources
- ~~Insider transactions (SEC EDGAR Form 4)~~ ✅ SHIPPED (Feature 15) — `InsiderService`, `InsiderTransactionsCard`, `GET /insider/{symbol}`
- ~~FRED macro context → jury prompts~~ ✅ SHIPPED (Feature 15) — `FREDService`, value+30d-delta injected into all 3 analyst prompts
- Reddit sentiment (PRAW) — `r/wallstreetbets` + `r/stocks` mention count + VADER delta; needs Reddit API account · `[Value: Med]` `[Effort: High]` `[Needs: Reddit dev account]`
- Google Trends signal (`pytrends`) — relative search interest for `"{symbol} stock"`; sparkline + trend direction; fragile but free · `[Value: Med]` `[Effort: Med]`
- ~~Short interest tracker~~ ✅ SHIPPED (Feature 15) — `ShortInterestService` (FINRA weekly), short % / days-to-cover in FundamentalsPanel
- Earnings call transcript sentiment — SEC EDGAR free; NLP on 10-Q/8-K filings · `[Value: Med]` `[Effort: High]`

### UX & Data Display
- Multi-ticker overlay comparison — ratio chart (stock vs SPY); rolling 30d correlation line · `[Value: Med]` `[Effort: Low]`
- ~~Macro dashboard (`/macro` tab)~~ ✅ SHIPPED (Feature 15) — standalone FRED tab: 5 stat cards, T10Y2Y trend line, 30d-delta bar chart, inversion banner
- International markets — yfinance supports non-US tickers; exchange detection already exists · `[Value: Med]` `[Effort: Med]`
- ~~Analyst price target range~~ ✅ SHIPPED (Feature 21, PR #267) — `GET /analyst-targets/{symbol}`, `AnalystTargetsCard` (low/mean/high range bar + current marker + rating breakdown) below `DCFCard`
- "Setups today" hint — scan the user's watchlist and flag which tickers have a *clean* (actionable) swing and/or day-trade setup, so users aren't hunting ticker-by-ticker. The coherence gate (PR #288/#289) correctly returns "no clean trade" on most choppy-day tickers (~3/10 actionable in a basket scan), so this surfaces the few that pass without loosening the gate. Likely a small badge/count in the Watchlist panel + an endpoint that fans out `/trade-setup` + `/day-trade-setup` per watchlist symbol (reuse Redis cache; one row each). · `[Value: High]` `[Effort: Med]`

### Architecture & Infra
- Custom alert rule builder — price cross, RSI threshold, % move triggers; needs auth + background worker + notification channel · `[Value: High]` `[Effort: High]`
- Daily briefing email / push — scheduled Supabase edge function; morning summary digest · `[Value: High]` `[Effort: High]`
- Pattern detection (`scipy.signal.find_peaks`) — head & shoulders, double top/bottom, flag/pennant; annotate chart · `[Value: Med]` `[Effort: Med]`
- Isolation Forest anomaly detection — flag statistical outliers in price/volume series · `[Value: Med]` `[Effort: High]`

### Model Quality & Self-Improvement (meta)

> Theme: validate and fix the math/patterns that drive forecasts, trade setups, and projections
> FIRST, then add an AI layer that self-improves them. **Build math-first, AI-last.** Most input
> data already exists (InfluxDB `forecast_record` / `price_outcome` / `model_accuracy`, the
> walk-forward backtester, RF `feature_importances_`, regime/RL weights). Split so no single item
> is an unbounded rewrite — fixes are surgical and evidence-driven, not guesses.
> Recommended order: **calibration audit → driver attribution → component scorecard → math fixes →
> self-tuning loop → AI meta-layer.**

- **Forecast calibration audit** *(do first)* — is the core output even correct? Measure whether the
  48h high/low range and Monte Carlo P10/P50/P90 are actually *calibrated* (does ~80% of realized
  price land inside P10–P90? is directional accuracy > a naive/persistence baseline?). Pure analysis
  over existing InfluxDB outcome data; surfaces a coverage/reliability report and the "is it currently
  wrong?" gate everything else depends on. · `[Value: High]` `[Effort: Med]`
- **Prediction driver attribution** — quantify which inputs actually move each prediction and which
  correlate with *realized* accuracy (not just in-sample importance). Extend RF `feature_importances_`
  with an outcome-correlation pass over `price_outcome`; expose a "what drove this call" breakdown.
  Separates signal from decoration. · `[Value: High]` `[Effort: Med]`
- **Component backtest scorecard** — before trusting any model/indicator/signal, score its historical
  hit-rate vs realized outcomes (ensemble vs buy-hold/persistence, each indicator's edge, trade-setup
  stop/target geometry hit rate, R:R realization). One internal scorecard on the walk-forward
  backtester + outcome store; the ground truth for what to keep, fix, or drop.
  · `[Value: High]` `[Effort: Med–High]`
- **Trade-setup & projection math fixes** — act on the audit/scorecard: correct entry/stop/target/R:R
  logic and projection ranges where the math is demonstrably off. Surgical, not a rebuild (unless a
  component is shown to add no edge). · `[Value: High]` `[Effort: Med]` `[Depends: calibration audit + scorecard]`
- **Self-tuning weight calibration loop** — close the loop: periodically recompute model/signal weights
  from accumulated accuracy (a bounded, explainable *math* layer atop the existing RL/regime weighting),
  so the app's crucial factors auto-adjust as outcomes accrue. Recompute-on-demand, not a heavy online
  learner. · `[Value: High]` `[Effort: High]`
- **AI meta-improvement layer** — only after the math is validated and self-tuning: an LLM layer that
  reasons over the driver-attribution + scorecard + calibration outputs to propose concrete model/setup
  improvements (and explain them). The "AI on top of working math" cap.
  · `[Value: Med]` `[Effort: High]` `[Depends: all of the above]`

### Strategy Lab (stics.ai capability review)

> From the stics.ai 12-prompt review (2026-06-22). Most of these are only worth their salt when wired
> to the **rule-based strategy backtester (F28, proposed)** so every AI-generated strategy is
> immediately validated by real backtest math — same math-first / AI-last principle as above.
> Build order: ship F28 first (foundation) → cheap tweaks to shipped features → optimizer/risk tools
> on top of F28 → strategy/factor/macro generators → portfolio optimizer → alpha detection last.

**Net-new**
- **Strategy generation** (#1) — AI (Groq) proposes 3 codified strategies (indicators + exact settings,
  entry/exit rules, SL/TP, best conditions, edge) that map onto the F28 backtester rule set, so each
  suggestion is immediately backtestable. · `[Value: Med]` `[Effort: Med]` `[Depends: F28 backtester]`
- **Multi-factor / factor screener** (#5) — Momentum + Value + Volatility + Trend factor scores over the
  curated screener universe, weighted composite rank + example basket. · `[Value: Med]` `[Effort: High]`
- **Strategy optimization** (#6) — bounded parameter grid-search over the F28 rules to lift Sharpe /
  cut drawdown; before-vs-after table. · `[Value: Med]` `[Effort: High]` `[Depends: F28 backtester]`
- **Portfolio construction / optimizer** (#7) — given an asset list + risk tolerance + horizon, suggest
  an allocation (risk-parity / mean-variance-lite via `scipy.optimize`), expected return + volatility +
  drawdown + per-asset rationale. Extends Portfolio Manager (F10). · `[Value: Med]` `[Effort: High]`
- **Macro-based strategy signals** (#11) — FRED macro regime → positioning rules + entry/exit signals;
  builds on `FREDService` (F15). · `[Value: Med]` `[Effort: Med]`
- **Risk-reward & drawdown advisory** (#3 + #10) — on a backtested strategy: recovery-time + underwater
  curve + AI suggestions to reduce risk / lift returns. · `[Value: Med]` `[Effort: Med]` `[Depends: F28 backtester]`
- **Alpha / edge detection** (#12) — speculative AI: behavioral-inefficiency / market-structure ideas.
  Lowest priority; gate on everything above. · `[Value: Low–Med]` `[Effort: High]`

**Tweaks to already-shipped capabilities** (enhance, don't rebuild)
- **Regime (F16)** (#4) — add a volatility dimension (ATR-percentile: calm/normal/volatile) + a plain-
  language "favoured strategy type / what to avoid" line. · `[Value: Med]` `[Effort: Low]`
- **Trade Setup** (#8) — extend single-ticker → ranked top-N "best setups now" scan over the screener
  universe (entry/stop/targets/R:R, sorted by R:R). · `[Value: Med]` `[Effort: Med]`
- **Monte Carlo (#9)** — also run MC/bootstrap on F28 *strategy* trade returns → prob-of-loss +
  robust/fragile verdict (currently MC is price-only). · `[Value: Med]` `[Effort: Med]` `[Depends: F28 backtester]`
- **F28 backtester enhancement** — add per-regime performance breakdown ("best/worst conditions",
  covering #2) + max-drawdown recovery time (#10); fold into F28 rather than a separate feature.
  · `[Value: Med]` `[Effort: Low]`

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
