# FiForesight Roadmap

> Source of truth for planned work. Aligned with Jira project **FIFO** on Atlassian.
> Last synced: 2026-04-25

---

## Epic 1 — ML & Forecasting Engine [FIFO-5]

Improve the ensemble forecasting engine with advanced technical indicators, model accuracy tracking, backtesting, and hyperparameter optimization.

| Jira | Story | Status |
|------|-------|--------|
| FIFO-7 | Advanced Technical Indicators (RSI, MACD, BB, SMA50/200, Support/Resistance) | Done |
| FIFO-8 | Ensemble Model Improvements (hyperparameter tuning, dynamic weighting, new models) | To Do |
| FIFO-9 | Historical Forecast Tracking (accuracy metrics, model performance over time) | Done |

---

## Epic 2 — News & Sentiment Analysis [FIFO-6]

Build a complete news and sentiment analysis pipeline: SerpAPI news integration, NLP sentiment scoring, sentiment-weighted model adjustments, and AI analyst notes.

| Jira | Story | Status |
|------|-------|--------|
| FIFO-20 | SerpAPI News Integration | Done |
| FIFO-21 | Sentiment Analysis Pipeline (VADER — `SentimentService` in services.py) | Done |
| FIFO-22 | AI Analyst Notes (Groq llama-3.3-70b — replaces Gemini) | Done |

---

## Epic 3 — Infrastructure & DevOps [FIFO-32]

Harden infrastructure, improve CI/CD pipeline, and add observability. Covers HTTPS/SSL, CORS, rate limiting, security scanning, staging environments, structured logging, and error tracking.

| Jira | Story | Status |
|------|-------|--------|
| FIFO-36 | HTTPS & Security Hardening | Done |
| FIFO-37 | CI/CD Pipeline Improvements | To Do |
| FIFO-38 | Monitoring & Observability | To Do |

**Already shipped (not in Jira):** New Relic APM integration, GitHub Actions CI/CD (PR preview + prod deploy), Docker multi-stage builds, Koyeb + Oracle Cloud deploys, nginx structured JSON logging + stub_status.

---

## Epic 4 — Testing & Quality [FIFO-33]

Build comprehensive test suites and enforce quality gates. Currently at 0% test coverage — target 70%+ across backend (pytest) and frontend (Vitest). Add E2E testing with Playwright and enforce coverage in CI.

| Jira | Story | Status |
|------|-------|--------|
| FIFO-49 | Backend Test Suite (pytest) | To Do |
| FIFO-50 | Frontend Test Suite (Vitest + Playwright) | To Do |
| FIFO-51 | Code Quality Gates in CI | To Do |

---

## Epic 5 — Frontend Architecture & UX [FIFO-34]

Refactor the monolithic page.tsx into modular components, add accessibility support, implement error boundaries, optimize performance with Web Vitals tracking, and add analytics.

| Jira | Story | Status |
|------|-------|--------|
| FIFO-58 | Component Decomposition & Error Boundaries | Done |
| FIFO-59 | Accessibility (a11y) Compliance | To Do |
| FIFO-60 | Performance Optimization & Analytics | To Do |

**Already shipped (not in Jira):** Dark/light theme, loading skeletons, ticker autocomplete, candlestick chart mode, RSI/MACD/BB/SMA chart overlays, TradingView chart toggle, trending sparklines panel, portfolio simulation page. page.tsx decomposed to 336 lines with components in `frontend/components/`.

---

## Epic 6 — User Auth & Personalization [FIFO-35]

Add user authentication via Supabase, protected routes, personal watchlists, price alerts, and portfolio tracking. Enables a personalized experience and paves the way for premium features.

| Jira | Story | Status |
|------|-------|--------|
| FIFO-79 | Supabase Auth Integration | To Do |
| FIFO-80 | Watchlists & Alerts | To Do |

---

## Epic 7 — LLM Analyst Jury & AI Intelligence [FIFO-101]

Multi-model LLM analyst jury system using free-tier APIs and self-hosted models. Covers provider integration (Groq, Gemini, Together AI), self-hosted inference on Oracle Always Free A1, and fine-tuning pipeline.

| Jira | Story | Status |
|------|-------|--------|
| FIFO-102 | LLM Analyst Jury: Model Selection & Free API Integration (Groq: Llama 4 Scout, Llama 70B, Qwen3 32B) | Done |
| FIFO-103 | Self-Hosted LLM on Oracle Cloud Always Free Tier | To Do |
| FIFO-104 | Fine-Tuning Pipeline for Analyst Note Quality | To Do |

---

## Epic 8 — AI Decision Layer [FIFO-121]

Stock Chat Agent + Trade Setup Generator: AI-guided decision panel that synthesises all signals into actionable output for beginners and advanced users.

| Jira | Story | Status |
|------|-------|--------|
| FIFO-121 | Stock Chat Agent + Trade Setup Generator — AI-guided decision panel | Done |

**Shipped:** `POST /chat` SSE streaming endpoint (llama-3.3-70b), `POST /trade-setup` deterministic entry/stop/target computation + Groq rationale, `StockChatPanel` (380px drawer, beginner chips, streaming cursor), `TradeSetupCard` (entry/stop/3 targets, R:R, setup type badge).

---

## Backlog — Legacy Roadmap Items (not yet in Jira)

These items from the original roadmap are not yet tracked as Jira stories:

| Category | Item | Complexity |
|----------|------|-----------|
| UX | Multi-ticker comparison overlay | Medium |
| UX | Price alert system (toast/email) | High |
| Data | Earnings date markers on chart | Low |
| Data | Options chain data panel | Medium |
| Data | Macro economic dashboard (GDP, CPI, rates) | Medium |
| Data | International markets expansion | Medium |
| Data | Volume analysis sub-panel | Low |
| Data | Sector / peer comparison view | Medium |
| Data | Social sentiment pipeline (Reddit/X) | High |
| Intelligence | Support & resistance via DBSCAN clustering | High |
| Intelligence | Pattern detection (scipy.signal.find_peaks) | High |
| Intelligence | Isolation Forest anomaly detection | High |
| Intelligence | Walk-forward backtesting engine | High |
| Intelligence | Portfolio tracking & P&L dashboard | High |
| Intelligence | Risk metrics (Sharpe, Sortino, Beta) | Medium |
| Intelligence | Custom alert conditions (rule builder) | High |
| Testing | External data drift monitor (price/div/cap vs Yahoo API) | Medium |

---

## Summary

| Epic | Stories | Done | Remaining |
|------|---------|------|-----------|
| ML & Forecasting (FIFO-5) | 3 | 2 | 1 |
| News & Sentiment (FIFO-6) | 3 | 3 | 0 |
| Infrastructure (FIFO-32) | 3 | 1 | 2 |
| Testing & Quality (FIFO-33) | 3 | 0 | 3 |
| Frontend Architecture (FIFO-34) | 3 | 1 | 2 |
| User Auth (FIFO-35) | 2 | 0 | 2 |
| LLM Analyst Jury (FIFO-101) | 3 | 1 | 2 |
| AI Decision Layer (FIFO-121) | 1 | 1 | 0 |
| **Totals** | **21** | **9** | **12** |
| Backlog (not in Jira) | 16 | — | 16 |
