# FiForesight Roadmap

> This file lives in `.claude/` (gitignored). It is the source of truth for planned work.
> Sequencing: Track 1 (UX/Indicators) → Track 2 (Data) → Track 3 (Intelligence)

---

## Track 1 — UX Polish & Core Indicators (10 tasks)

| # | Task | Complexity | Status |
|---|------|-----------|--------|
| 1 | Dark/light theme toggle | Low | ✅ Done |
| 2 | Loading skeletons | Low | ✅ Done |
| 3 | Ticker autocomplete | Low | ✅ Done |
| 4 | RSI dedicated sub-chart panel | Medium | ✅ Done |
| 5 | MACD panel (line + histogram) | Medium | ✅ Done |
| 6 | Bollinger Bands overlay on chart | Medium | ✅ Done |
| 7 | SMA 50 & SMA 200 overlay lines | Medium | ✅ Done |
| 8 | Candlestick chart mode | Medium | ⬜ Pending |
| 9 | Multi-ticker comparison overlay | Medium | ⬜ Pending |
| 10 | Price alert system (toast/email) | High | ⬜ Pending |

---

## Track 2 — Data Expansion (8 tasks)

| # | Task | Complexity | Status |
|---|------|-----------|--------|
| 1 | News sentiment scoring (FinBERT/VADER on yfinance headlines) | Medium | ⬜ Pending |
| 2 | Earnings date markers on chart | Low | ⬜ Pending |
| 3 | Options chain data panel | Medium | ⬜ Pending |
| 4 | Macro economic dashboard (GDP, CPI, rates) | Medium | ⬜ Pending |
| 5 | International markets expansion | Medium | ⬜ Pending |
| 6 | Volume analysis sub-panel | Low | ⬜ Pending |
| 7 | Sector / peer comparison view | Medium | ⬜ Pending |
| 8 | Social sentiment pipeline (Reddit/X) | High | ⬜ Pending |

---

## Track 3 — Intelligence Layer (9 tasks)

| # | Task | Complexity | Status |
|---|------|-----------|--------|
| 1 | Support & resistance via DBSCAN clustering | High | ⬜ Pending |
| 2 | Pattern detection (scipy.signal.find_peaks) | High | ⬜ Pending |
| 3 | Structured trade setup generator | High | ⬜ Pending |
| 4 | Isolation Forest anomaly detection | High | ⬜ Pending |
| 5 | Walk-forward backtesting engine | High | ⬜ Pending |
| 6 | LLM chat panel (FastAPI StreamingResponse + stock context) | High | ⬜ Pending |
| 7 | Portfolio tracking & P&L dashboard | High | ⬜ Pending |
| 8 | Risk metrics (Sharpe, Sortino, Beta) | Medium | ⬜ Pending |
| 9 | Custom alert conditions (rule builder) | High | ⬜ Pending |

---

## Sequencing Notes

- **Phase 1** (now): All Track 1 Low tasks + MACD/BB/SMA indicators. No new backend deps needed.
- **Phase 2** (next): Track 2 data tasks — seeds InfluxDB richly for the AI layer.
- **Phase 3** (after): Track 3 intelligence — each task builds on the previous; do in order.
