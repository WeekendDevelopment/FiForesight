# FiForesight — Implementation Prompts for Features 9–12

> Copy-ready, self-contained prompts. Build order: **F11 → F12 → F10 → F9**.
> Each prompt re-orients via CLAUDE.md, lists reusable building blocks, states prerequisites,
> requires local testing before PR, and **mandates documentation updates every time a feature
> is introduced or changed** (CLAUDE.md + /docs + .env.example + PR contract + roadmap).

---

## Feature 11 Prompt — Security Hardening *(build first)*

```
## Context
You are working on FiForesight — an AI-driven quantitative financial forecasting SaaS.
Read CLAUDE.md first (project root): full tech stack, file structure, conventions, env vars,
data flow. Do not re-explore what's documented there.

## Why this feature
A security audit found the backend is effectively unprotected:
- Auth is FRONTEND-ONLY. These expensive endpoints are fully public:
  `/predict` (ML + 4 Groq calls), `/chat` (Groq stream), `/jury/reanalyze` (3 Groq calls),
  `/trade-setup` (Groq call).
- ZERO rate limiting — one script can drain the Groq free-tier quota and exhaust compute.
- `/chat` is prompt-injectable: `req.message` + context interpolated into the Groq prompt
  unsanitized, no length cap.
- CORS is unset (defaults open).
- `/predict` symbol input is only `.upper()`-ed, not validated.
- 9 `except Exception` handlers silently skip data with no logging.

## Existing building blocks (reuse, don't reinvent)
- `backend/dependencies.py` already has `get_user_id()` (extracts JWT Bearer; line ~36-63).
  It currently decodes WITHOUT signature verification when `SUPABASE_JWT_SECRET` is unset.
  Only the 3 `/simulation/state*` endpoints use it today.
- `backend/services.py` has `_SAFE_TAG_RE = re.compile(r"^[A-Za-z0-9._:\-]+$")` and
  `_validate_tag()` (line ~36-52) — reuse for symbol validation.
- `backend/config.py` loads secrets from `.env` via python-dotenv; has a logging filter
  that masks API keys.
- Global exception handler in `backend/main.py` already hides tracebacks (good — keep it).

## Goal
Add defense-in-depth without breaking existing UX. Read-only market data stays usable;
expensive/compute endpoints get protected and throttled.

---

## Step 1: Rate limiting (slowapi)
- Add `slowapi` to `backend/requirements.txt`.
- In `backend/main.py`: create a `Limiter(key_func=get_remote_address)`, register the
  `_rate_limit_exceeded_handler`, attach `app.state.limiter`.
- Apply per-route limits via decorator or middleware:
  - `/predict`: 10/min per IP
  - `/chat`: 20/min per IP
  - `/jury/reanalyze`: 10/min per IP
  - `/trade-setup`: 15/min per IP
  - `/backtest/{symbol}`: 5/min per IP (very expensive)
  - read-only market endpoints (`/sectors`, `/briefing`, `/dcf`, `/options`, `/history`,
    `/earnings/calendar`, `/ipo/calendar`, `/sparklines`): 60/min per IP
- Return HTTP 429 with a `Retry-After` header. Never leak internal detail in the body.
- Make the limit values configurable via env (e.g. `RATE_LIMIT_PREDICT=10/minute`) with
  sensible defaults in `config.py`.

## Step 2: Auth enforcement on compute-heavy endpoints
- Harden `get_user_id()` in `dependencies.py`:
  - When `SUPABASE_JWT_SECRET` IS set → verify signature (`verify_signature: True`),
    reject invalid/expired tokens with 401.
  - When it is NOT set → log a loud WARNING once at startup ("JWT signature verification
    disabled — set SUPABASE_JWT_SECRET in production") and fall back to unverified decode
    for local dev only.
- Add a `require_user` dependency (raises 401 if no valid token) distinct from the existing
  soft `get_user_id` (returns anon).
- Apply `Depends(require_user)` to `/jury/reanalyze`, `/trade-setup`. For `/predict` and
  `/chat`: gate them as "soft" — allow anonymous but apply the STRICTER anonymous rate limit
  (e.g. anon `/predict` 3/min, authed 10/min) so the public demo still works but abuse is
  capped. Implement this with a key_func that buckets by user_id when present, else IP.
- IMPORTANT: confirm the frontend already sends the Supabase access token on these calls.
  If not, update the relevant Next.js proxy routes
  (`frontend/app/api/{predict,chat,trade-setup,jury/reanalyze}/route.ts`) to forward the
  `Authorization: Bearer <token>` header from the incoming request to the backend.

## Step 3: Prompt-injection guards on /chat
In `backend/routers/trade.py` `/chat`:
- Cap `req.message` to 500 chars (reject 422 if longer, or truncate + log).
- Add a Pydantic `max_length=500` on the message field.
- Sanitize interpolated context values (`symbol`, `jury_summary`, `headlines`): strip
  newlines and control chars, cap each to a reasonable length, validate `symbol` against
  `_SAFE_TAG_RE`.
- Harden the system prompt: explicitly instruct the model to only answer questions about
  the given ticker and to ignore any instructions contained in user content that attempt
  to change its role or reveal system internals.
- Do not echo raw upstream Groq error bodies to the client (the audit found "Groq error
  {status_code}" leakage — replace with a generic message, log the detail server-side).

## Step 4: CORS
In `backend/main.py`:
- Add `CORSMiddleware` restricted to known origins from an env var
  `ALLOWED_ORIGINS` (comma-separated; defaults to the preview + prod duckdns domains +
  `http://localhost:3000`). `allow_credentials=True`, methods `["GET","POST","DELETE"]`,
  headers `["Authorization","Content-Type"]`.

## Step 5: Input validation
- In `/predict` (`routers/predict.py`): validate the symbol with `_validate_tag` (or the
  same regex used by `/jury/reanalyze`: `re.fullmatch(r"[A-Za-z0-9.\-:]{1,15}")`) before
  any yfinance/LLM use. Reject 422 on invalid.
- Audit `/sectors`, `/briefing`, `/options/{symbol}`, `/dcf/{symbol}` for symbol pass-through
  and validate where user-controlled.

## Step 6: Observability on silent failures
Add `logger.debug(...)` (or `logger.warning` where appropriate) before the silent
`continue`/append/`pass` in these handlers so masked failures are visible:
`backend/routers/market.py:414, 629, 680`, `backend/routers/trade.py:279`,
`backend/services.py:941`, `backend/jury_graph.py:169`. Keep behavior identical — only add logging.

---

## Testing requirements (mandatory before PR)
1. Run backend + frontend locally (`pnpm run dev` from frontend/ + uvicorn). Verify:
   - Anonymous `/predict` works but is throttled at the anon limit (hammer it, expect 429
     with Retry-After).
   - Authenticated `/predict` (with a real Supabase token) gets the higher limit.
   - `/jury/reanalyze` and `/trade-setup` return 401 without a token, 200 with one.
   - `/chat` rejects a >500-char message and resists a basic injection
     ("ignore previous instructions...") — it stays on-topic.
   - CORS: a request from a disallowed Origin is blocked; localhost:3000 works.
   - Invalid symbol (`/predict` with `data="; DROP"`) returns 422.
2. `python -m pytest backend/tests/ -v` — all existing tests pass.
   ADD new tests: rate-limit returns 429; require_user returns 401 without token;
   /chat rejects oversized message; symbol validation rejects bad input.
   (These also start closing the audit's coverage gaps.)
3. `pnpm run build` — clean TypeScript compile (proxy header forwarding compiles).
4. `ruff check backend/` — no new errors.

## Documentation (REQUIRED — part of done, do NOT skip)
Update docs in the SAME PR whenever a feature is introduced or changed:
1. `CLAUDE.md` — add a "Security" subsection under Key Decisions: auth enforcement model,
   rate-limit defaults, new env vars (`ALLOWED_ORIGINS`, `SUPABASE_JWT_SECRET`,
   `RATE_LIMIT_*`). Add the new env vars to the Environment Variables block.
2. `/docs/FiForesight-Documentation.md` — add a Security section documenting auth, rate
   limits per endpoint, and the prompt-injection guards. While here, FIX the stale claim
   at ~line 1061 that `/compare` is an unimplemented stub (it is live).
3. `backend/.env.example` — add the new env vars with comments.
4. PR description — document the auth model + rate-limit table (the API contract).
5. Roadmap — move Feature 11 from "Next Up" to "Shipped" with the PR number.

## PR workflow
1. Commit logically (rate-limit, auth, chat-guards, cors, validation, observability, docs).
2. Push to `feat/security-hardening`. Open a PR against `main`.
3. Monitor CI — auto-fix any failures immediately and push fixes to the same branch.
4. Resolve all CodeRabbit review comments: fix valid issues; reply with rationale on any
   intentional won't-fix. Keep iterating until all checks are green and reviews resolved.
```

---

## Feature 12 Prompt — Forecast Accuracy & Sentiment Analytics Dashboard *(build second)*

```
## Context
You are working on FiForesight — an AI-driven quantitative financial forecasting SaaS.
Read CLAUDE.md first (project root). Do not re-explore what's documented there.

## Prerequisite
Feature 11 (Security Hardening) should be merged first — apply the same rate limits to the
new analytics endpoints (read-only tier, 60/min).

## Why this feature
The product makes forecasts but never shows whether they were RIGHT. A rich accuracy
dataset is ALREADY collected in InfluxDB and thrown away at the UI layer. Sentiment is
computed per-request and never persisted. This is the highest value-per-effort feature
because the data already exists — it's mostly read + visualize.

## Existing data assets (in `backend/services.py`, ForecastStore + InfluxService)
- `forecast_record` — per-model day-1 predictions (Prophet/SARIMA/RF) + ensemble d1–d5 +
  model weights. Query: `ForecastStore.query_forecast_records()` (~line 601).
- `price_outcome` — actual closes written when forecasts resolve.
  Query: `query_price_outcomes()` (~627).
- `model_accuracy` — per-model MAE + sample count, EMA-decayed (90-day lookback).
  Query: `query_model_accuracy()` (~658).
- `ensemble_mae` — aggregate ensemble MAE per horizon d1–d5.
  Query: `query_ensemble_mae()` (~699).
- `resolve_past_forecasts()` (`routers/predict.py:~453`) already runs on every /predict and
  populates these. NONE of it is surfaced to users today.
- VADER `SentimentService.score_headlines()` in services.py (~1435) returns compound + label
  per request — NOT persisted.

## Goal
A new `/insights` tab answering "how accurate are these forecasts, and how is sentiment
trending?" — built mostly from data already in InfluxDB.

---

## Step 1: Backend — accuracy analytics endpoint
Create `backend/routers/analytics.py`, register it in `backend/main.py`.

`GET /analytics/accuracy/{symbol}`:
- Validate symbol (reuse the F11 validation).
- Read `query_model_accuracy`, `query_ensemble_mae`, `query_forecast_records`,
  `query_price_outcomes` for the symbol.
- Compute and return:
  ```json
  {
    "symbol": "NVDA",
    "model_mae": {"prophet": 4.1, "sarima": 4.8, "random_forest": 3.6},
    "best_model": "random_forest",
    "ensemble_mae_by_horizon": [{"horizon":"d1","mae":2.1}, ... "d5"],
    "directional_accuracy": {"prophet":0.62,"sarima":0.60,"random_forest":0.71,"ensemble":0.67},
    "forecast_vs_actual": [{"date":"2025-05-01","forecast":135.2,"actual":133.9}, ...],
    "samples": 42,
    "generated_at": "..."
  }
  ```
  Directional accuracy = % of resolved forecasts where predicted direction matched actual.
  `forecast_vs_actual` joins `forecast_record` (e_d1) with `price_outcome` by timestamp.
- Redis cache 15-min TTL. `asyncio.wait_for(timeout=12)`. If insufficient history, return
  a 200 with `samples: 0` and empty arrays (frontend shows an empty state — NOT a 404).

## Step 2: Backend — persist sentiment over time
- Add an InfluxService method `write_sentiment_score(symbol, compound, label)` writing to a
  new `sentiment_score` measurement (tags: symbol, env; fields: compound, label).
- In `routers/predict.py`, after VADER scoring, fire-and-forget a background write of the
  compound score (use the existing `_safe_background` helper so a failure never breaks
  /predict).
- Add InfluxService `query_sentiment_history(symbol, days=30)`.
- `GET /analytics/sentiment/{symbol}` → `{ "symbol", "history": [{"date","compound","label"}], "current" }`.
  Redis 15-min TTL.

## Step 3: Frontend — /insights tab
- Add an "Insights" item to the AppShell sidebar (use a chart icon, e.g. `Activity` or
  `BarChart3` from lucide-react). Route: `/insights`.
- Create `frontend/app/(app)/insights/page.tsx`:
  - Symbol search input (reuse the landing-page autocomplete pattern); default empty with an
    empty state "Search a ticker to see its forecast accuracy and sentiment trend".
  - On submit, fetch `/api/analytics/accuracy/{symbol}` and `/api/analytics/sentiment/{symbol}`.
  - Render (Recharts):
    1. **Model performance ranking** — horizontal bar of per-model MAE (lower = better),
       highlight best_model.
    2. **Ensemble confidence by horizon** — line/bar of ensemble MAE d1→d5 (shows how
       confidence decays with horizon).
    3. **Directional accuracy** — small stat cards per model + ensemble (%).
    4. **Forecast vs Actual** — line chart overlaying predicted vs realized closes.
    5. **Sentiment trend** — line chart of compound score over 30 days, colored by label.
  - Read `isDark` + `primaryColor` from `AppShellContext`.
  - Loading skeletons; graceful empty state when `samples === 0`.
- Create proxies `frontend/app/api/analytics/accuracy/[symbol]/route.ts` and
  `frontend/app/api/analytics/sentiment/[symbol]/route.ts` (standard pattern:
  `BACKEND_URL`, `AbortSignal.timeout(15000)`, `err: unknown`, 502 on failure).
- Add the TS types to `frontend/types/index.ts`.

---

## Testing requirements (mandatory before PR)
1. Local run. Because InfluxDB needs accumulated history, seed it by running a few /predict
   calls for a ticker across the day (or mock). Verify:
   - `/insights` empty state shows before search.
   - After searching a ticker with history: all 5 charts render; empty state shows cleanly
     for a ticker with `samples: 0`.
   - Sentiment write happens on /predict (check the new measurement) and the trend renders.
2. `python -m pytest backend/tests/ -v` — all pass. ADD tests for `/analytics/accuracy`
   and `/analytics/sentiment`: mock ForecastStore/InfluxService queries, assert response
   shape and the `samples: 0` empty path.
3. `pnpm run build` clean; `ruff check backend/` clean.

## Documentation (REQUIRED — part of done, do NOT skip)
Update docs in the SAME PR whenever a feature is introduced or changed:
1. `CLAUDE.md` — add `/analytics/accuracy` + `/analytics/sentiment` to the Data Flow section;
   document the new `sentiment_score` InfluxDB measurement under Key Decisions; add the
   Insights tab to the frontend structure list.
2. `/docs/FiForesight-Documentation.md` — add an Analytics/Insights section with the API
   contracts and what each chart shows.
3. PR description — request/response shapes for both endpoints.
4. Roadmap — move Feature 12 to Shipped with the PR number.

## PR workflow
1. Commit logically (accuracy endpoint, sentiment persistence, frontend tab, docs).
2. Push to `feat/accuracy-sentiment-dashboard`. Open PR against `main`.
3. Monitor CI — auto-fix failures, push to the same branch.
4. Resolve all CodeRabbit comments (fix or reasoned won't-fix). Iterate until green + resolved.
```

---

## Feature 10 Prompt — Portfolio Manager *(build third)*

```
## Context
You are working on FiForesight — an AI-driven quantitative financial forecasting SaaS.
Read CLAUDE.md first (project root). Do not re-explore what's documented there.

## Prerequisite
Features 11 (auth) and ideally 12 must be merged first. The portfolio endpoints MUST be
auth-gated using the `require_user` dependency added in Feature 11.

## Why this feature
The current "/simulation" page is a BACKTEST RACE SIMULATOR — it does not track a user's
real holdings or live P&L. There is no user-trade table. This is the biggest functional
gap vs. competitors (Yahoo Finance, Seeking Alpha). The Supabase auth + watchlist + the
InfluxDB `simulation_state` plumbing and `HoldingPnl` types are ~70% reusable.

## Existing building blocks
- Supabase auth shipped (`frontend/contexts/AuthContext.tsx`, `frontend/lib/supabase.ts`).
  Watchlist persistence pattern in `frontend/lib/watchlist.ts` (Supabase table + RLS) —
  COPY this pattern for holdings.
- `backend/simulation_service.py` computes `HoldingPnl` (pnl, pnlPct) — reuse the P&L math.
- Live price via `yf_svc.get_live_price`; fundamentals (sector) via `yf_svc.fetch_info`.
- Ensemble forecast + jury already callable for per-holding outlook.

## Goal
A real `/portfolio` tab: users add holdings (symbol, shares, cost basis), see live P&L,
sector allocation, a diversification score, and a portfolio-level forecast.

---

## Step 1: Supabase schema
- Create a migration (SQL) for table `holdings`:
  `id uuid pk default gen_random_uuid(), user_id uuid not null, symbol text not null,
   shares numeric not null, cost_basis numeric not null, opened_at timestamptz default now()`.
- Enable RLS: users can only select/insert/update/delete WHERE `user_id = auth.uid()`
  (mirror the watchlist policy).
- Document the migration SQL in the PR and in `/docs`.

## Step 2: Backend — portfolio router (auth-gated)
Create `backend/routers/portfolio.py`, register in `backend/main.py`. All endpoints use
`Depends(require_user)` (from Feature 11) — 401 if unauthenticated.

- `GET /portfolio/holdings` — list the user's holdings (read from Supabase via the service
  role key or via the token; choose the pattern consistent with how simulation/state reads
  user-scoped data).
- `POST /portfolio/holdings` — add/update a holding (validate symbol with the F11 regex;
  shares > 0; cost_basis >= 0).
- `DELETE /portfolio/holdings/{id}` — remove (enforce ownership).
- `GET /portfolio/summary` — the heavy one:
  - Fetch live price for each holding (concurrent, `asyncio.gather`, per-call timeout).
  - Per holding: market_value, cost_value, pnl, pnl_pct, weight_pct, sector.
  - Totals: total_market_value, total_cost, total_pnl, total_pnl_pct.
  - Sector allocation: aggregate weight by sector.
  - Diversification score: simple Herfindahl-based 0–100 (1 - HHI of weights, scaled).
  - Portfolio forecast: weighted aggregate of per-holding ensemble forecast direction
    (reuse the forecast; cache aggressively — do NOT run the full jury for every holding,
    that's too expensive; use the lighter ensemble or cached /predict results, Redis 15-min).
  - `asyncio.wait_for` timeouts on all external calls; partial results on failure (skip a
    holding that errors, log it — do not 500 the whole summary).

## Step 3: Frontend — /portfolio tab
- Add "Portfolio" to the AppShell sidebar (icon e.g. `Briefcase` or `Wallet`).
  Gate it behind auth — if not signed in, show an AuthGate prompt (reuse existing component).
- Create `frontend/app/(app)/portfolio/page.tsx`:
  - Holdings table: symbol, shares, cost basis, live price, market value, P&L $ / %,
    weight %, sector. Inline add row (symbol autocomplete, shares, cost basis) + edit/delete.
  - Summary header cards: total value, total P&L $ / %, diversification score.
  - Sector allocation pie (Recharts).
  - Portfolio-level forecast badge.
  - Each holding row clickable → `/analysis?symbol=X`.
  - Read `isDark`/`primaryColor` from `AppShellContext`. Loading skeletons; empty state
    "Add your first holding to start tracking P&L".
- Create `frontend/lib/holdings.ts` (mirror `watchlist.ts`): fetch/add/update/remove,
  forwarding the Supabase token.
- Proxies under `frontend/app/api/portfolio/...` forwarding `Authorization` to the backend.
- Add TS types to `frontend/types/index.ts`.

## Out of scope v1 (document explicitly)
Stock splits, dividends, and multi-currency are NOT handled in v1. Note this in the docs
and show cost basis as user-entered. A follow-up can add corporate-action adjustment.

---

## Testing requirements (mandatory before PR)
1. Local run with a real Supabase project (or the placeholder fallback for build). Verify:
   - Unauthenticated → /portfolio shows AuthGate; backend endpoints return 401.
   - Add a holding → appears in table with live price + P&L.
   - Summary cards, sector pie, diversification score render.
   - Delete/edit work; ownership enforced (can't touch another user's row).
   - A holding with a bad/halted symbol degrades gracefully (skipped, logged, no 500).
2. `python -m pytest backend/tests/ -v` — all pass. ADD tests for the portfolio router:
   auth required (401), P&L math correctness on a mocked holding set, summary partial-failure
   path. Mock Supabase + yfinance.
3. `pnpm run build` clean; `ruff check backend/` clean.

## Documentation (REQUIRED — part of done, do NOT skip)
Update docs in the SAME PR whenever a feature is introduced or changed:
1. `CLAUDE.md` — add the portfolio endpoints to Data Flow; document the Supabase `holdings`
   table + RLS under Key Decisions; add the Portfolio tab to the frontend structure; note
   splits/dividends as out-of-scope v1.
2. `/docs/FiForesight-Documentation.md` — Portfolio Manager section: API contracts, the
   migration SQL, the diversification-score formula.
3. PR description — endpoint contracts + migration SQL.
4. Roadmap — move Feature 10 to Shipped with the PR number.

## PR workflow
1. Commit logically (migration, backend router, frontend tab + lib, docs).
2. Push to `feat/portfolio-manager`. Open PR against `main`.
3. Monitor CI — auto-fix failures, push to the same branch.
4. Resolve all CodeRabbit comments (fix or reasoned won't-fix). Iterate until green + resolved.
```

---

## Feature 9 Prompt — Alerts & Notifications *(build last)*

```
## Context
You are working on FiForesight — an AI-driven quantitative financial forecasting SaaS.
Read CLAUDE.md first (project root). Do not re-explore what's documented there.

## Prerequisite
Features 11 (auth) and 10 (portfolio) must be merged first. Alert endpoints are auth-gated
via `require_user` (Feature 11). Alerts can optionally reference portfolio holdings (Feature 10).

## Why this feature
Engagement is pull-only: users must manually re-run a ticker to learn anything changed.
Alerts/notifications are the #1 retention lever for retail finance apps. The backlog
prioritizes this twice (alert rule builder + daily briefing). Foundations exist: Supabase
auth, the `/briefing` aggregation, watchlist + holdings.

## Goal
Users define alert rules (price cross, RSI threshold, % move, earnings-tomorrow,
forecast-breakout). A scheduled evaluator checks them against live data and notifies via
web-push and/or email. A daily-briefing digest reuses `/briefing`.

---

## Step 1: Supabase schema
Migration for `alert_rules`:
`id uuid pk, user_id uuid not null, symbol text not null, type text not null,
 operator text, threshold numeric, active boolean default true,
 last_fired timestamptz, created_at timestamptz default now()`.
RLS scoped to `auth.uid()`. Types: `price_cross`, `rsi_threshold`, `pct_move`,
`earnings_soon`, `forecast_breakout`.
(Optional) `alert_fires` table to log fire history: `id, rule_id, fired_at, message, value`.

## Step 2: Backend — alerts router (auth-gated)
Create `backend/routers/alerts.py`, register in `main.py`. All `Depends(require_user)`.
- `GET /alerts/rules` — list user's rules.
- `POST /alerts/rules` — create/update (validate symbol with F11 regex; validate type +
  operator + threshold combinations).
- `DELETE /alerts/rules/{id}` — delete (ownership enforced).
- `GET /alerts/fires` — recent fire history for the user.

## Step 3: The evaluator (scheduled worker)
- Implement `evaluate_alerts()` that:
  - Loads all active rules (across users) grouped by symbol (dedupe symbol fetches).
  - For each symbol: fetch live price + RSI (reuse existing indicator helpers), earnings
    date, latest forecast as needed by the rule types present.
  - Evaluate each rule; if it fires and hasn't recently (`last_fired` cooldown, e.g. 6h),
    record a fire, update `last_fired`, and enqueue a notification.
  - Wrap everything defensively — one bad symbol must not abort the batch (log + continue).
- Scheduling: prefer a Supabase scheduled Edge Function or a lightweight cron hitting an
  internal `POST /alerts/evaluate` endpoint protected by a shared secret header
  (`X-Cron-Secret`, env `CRON_SECRET`). Do NOT use a Bash sleep loop. Document the chosen
  mechanism. Run cadence: every 15 min during market hours.

## Step 4: Delivery
- **Web push (free):** implement the Web Push (VAPID) flow — store push subscriptions in a
  Supabase `push_subscriptions` table; backend sends via `pywebpush`. Add VAPID keys to env
  (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`).
- **Email (optional fallback):** Supabase Edge Function or a free SMTP/Resend free tier;
  gate behind an env flag so the feature works web-push-only if email isn't configured.
- **Daily briefing digest:** a once-daily job that emails/pushes the `/briefing` summary +
  any of the user's holdings/watchlist movers. Reuse the `/briefing` data.

## Step 5: Frontend — /alerts tab
- Add "Alerts" to the AppShell sidebar (icon `Bell`). Auth-gated (AuthGate when signed out).
- `frontend/app/(app)/alerts/page.tsx`:
  - Rule builder: symbol autocomplete, type select, operator + threshold inputs that adapt
    to the chosen type (e.g. price_cross → operator above/below + price; rsi_threshold →
    above/below + 0–100; earnings_soon → no threshold).
  - Active rules list with toggle (active/paused) + delete.
  - Fire history list.
  - A "Enable browser notifications" button that registers the web-push subscription
    (requests Notification permission, subscribes with the VAPID public key, POSTs the
    subscription to the backend).
  - Read theme from `AppShellContext`; skeletons; empty states.
- Proxies under `frontend/app/api/alerts/...` forwarding `Authorization`.
- TS types in `frontend/types/index.ts`.

---

## Testing requirements (mandatory before PR)
1. Local run. Verify:
   - Unauthenticated → AuthGate; endpoints 401.
   - Create each rule type; they appear and persist.
   - Manually invoke the evaluator (`POST /alerts/evaluate` with the cron secret) against a
     rule crafted to fire → a fire is recorded and a web-push notification is received in the
     browser.
   - Cooldown prevents duplicate fires within the window.
   - Evaluator survives a bad symbol in the batch (logged, others still processed).
2. `python -m pytest backend/tests/ -v` — all pass. ADD tests: rule CRUD auth (401),
   evaluator firing logic per rule type (mock prices/RSI), cooldown suppression,
   cron-secret rejection without the header. Mock Supabase + yfinance + push.
3. `pnpm run build` clean; `ruff check backend/` clean.

## Documentation (REQUIRED — part of done, do NOT skip)
Update docs in the SAME PR whenever a feature is introduced or changed:
1. `CLAUDE.md` — add alerts endpoints + the evaluator/cron mechanism to Data Flow; document
   `alert_rules`/`alert_fires`/`push_subscriptions` tables and the new env vars
   (`CRON_SECRET`, `VAPID_*`, email flags) under Key Decisions + Environment Variables.
2. `/docs/FiForesight-Documentation.md` — Alerts & Notifications section: rule types, API
   contracts, the scheduling/delivery design, migration SQL.
3. `backend/.env.example` — add the new env vars.
4. PR description — endpoint contracts + the scheduling/delivery architecture.
5. Roadmap — move Feature 9 to Shipped with the PR number.

## PR workflow
1. Commit logically (migrations, alerts router, evaluator, delivery, frontend tab, docs).
2. Push to `feat/alerts-notifications`. Open PR against `main`.
3. Monitor CI — auto-fix failures, push to the same branch.
4. Resolve all CodeRabbit comments (fix or reasoned won't-fix). Iterate until green + resolved.
```
