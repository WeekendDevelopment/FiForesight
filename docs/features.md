# FiForesight — Feature & Signal Reference

This guide explains every feature, indicator, and signal on the FiForesight dashboard. Use it when a chart, number, or badge looks unfamiliar.

---

## Table of Contents

1. [Search & Ticker Input](#1-search--ticker-input)
2. [Price Chart](#2-price-chart)
3. [Technical Indicators](#3-technical-indicators)
   - [Bollinger Bands](#bollinger-bands)
   - [SMA (Simple Moving Average)](#sma-simple-moving-average)
   - [EMA (Exponential Moving Average)](#ema-exponential-moving-average)
   - [RSI (Relative Strength Index)](#rsi-relative-strength-index)
   - [MACD](#macd)
   - [Volume](#volume)
   - [Support & Resistance](#support--resistance)
   - [Earnings Markers](#earnings-markers)
4. [Ensemble ML Forecast](#4-ensemble-ml-forecast)
5. [Monte Carlo Simulation](#5-monte-carlo-simulation)
6. [LLM Analyst Jury](#6-llm-analyst-jury)
7. [VADER Sentiment Score](#7-vader-sentiment-score)
8. [DCF Intrinsic Value](#8-dcf-intrinsic-value)
9. [Trade Setup Card](#9-trade-setup-card)
10. [Options Chain Panel](#10-options-chain-panel)
11. [Fundamentals Panel](#11-fundamentals-panel)
12. [Peer Comparison Panel](#12-peer-comparison-panel)
13. [News Feed](#13-news-feed)
14. [Portfolio Simulation](#14-portfolio-simulation)
15. [Auth & Account](#15-auth--account)
16. [AI Chat Assistant](#16-ai-chat-assistant)
17. [Reading Signals Together](#17-reading-signals-together)

---

## 1. Search & Ticker Input

**What it is:** The main input at the top of the dashboard. Enter any ticker symbol (e.g. `AAPL`, `TSLA`, `BTC-USD`) and optionally select an exchange from the dropdown.

**Exchange selector:** Use this when the same symbol exists on multiple exchanges (e.g. `VOD` on LSE vs NASDAQ). Defaults to auto-detect.

**Autocomplete list:** Pre-populated with 40 popular tickers across equities, ETFs, and crypto.

**What happens when you search:** The app fires the full analysis pipeline — historical data fetch, all indicators, ensemble forecast, LLM jury, sentiment scoring, news, DCF, options chain, and trade setup. DCF, options, and trade setup load asynchronously after the main result so the page isn't blocked.

---

## 2. Price Chart

**Chart types:**
- **Line** — Closing price plotted as a continuous line. Simpler and easier to read for trend direction.
- **Candlestick** — Each bar shows Open, High, Low, Close for that period. Green candle = close above open (price rose). Red candle = close below open (price fell). Good for spotting patterns and intraday momentum.

**Chart engine:**
- **Classic** — Recharts-powered 2D chart with full overlay and sub-panel support.
- **Pro** — TradingView-powered chart for more advanced visual analysis.

**Time period shown:** The most recent ~1 year of daily OHLCV data, sourced from InfluxDB (2-year cache) with yfinance fallback.

**Overlays toggle:** Use the button group below the chart header to turn individual indicators on/off without reloading data.

---

## 3. Technical Indicators

### Bollinger Bands

**What they are:** Three lines plotted around price:
- **Upper band** = 20-day SMA + (2 × standard deviation)
- **Middle band** = 20-day SMA
- **Lower band** = 20-day SMA − (2 × standard deviation)

**How to read them:**
- Price touching the **upper band** → potentially overbought; price may pull back.
- Price touching the **lower band** → potentially oversold; price may bounce.
- **Bands squeezing together** (low volatility) often precedes a sharp move in either direction — watch for a breakout.
- **Bands expanding** = high volatility; the trend may be accelerating.

**What it doesn't tell you:** Direction. A stock can walk the upper band for weeks during a strong uptrend ("riding the band"). Always combine with RSI or MACD for confirmation.

---

### SMA (Simple Moving Average)

**SMA 50:** Average closing price over the last 50 trading days (~10 weeks). A medium-term trend indicator.

**SMA 200:** Average closing price over the last 200 trading days (~40 weeks). The primary long-term trend benchmark.

**How to read them:**
- **Price above SMA 50/200** → bullish (price is above its average).
- **Price below SMA 50/200** → bearish.
- **Golden Cross:** SMA 50 crosses above SMA 200 → historically bullish signal.
- **Death Cross:** SMA 50 crosses below SMA 200 → historically bearish signal.

**Lag:** SMAs are lagging indicators — they tell you about past price action, not the future. Use them to confirm a trend already in motion, not to predict reversals.

---

### EMA (Exponential Moving Average)

**EMA 20:** Like SMA 20, but gives more weight to recent prices. Reacts faster to price changes than SMA.

**EMA 50:** Medium-term EMA. Often used as a dynamic support/resistance level.

**EMA vs SMA:** EMA hugs price more tightly. This makes it more sensitive to recent moves but also more prone to false signals. Traders use EMA when they want faster signals; SMA for smoother, more reliable trend identification.

**How to read them:**
- EMA crossing above a longer EMA → short-term bullish momentum.
- Price pulling back to EMA 20 and bouncing → EMA acting as support.
- Price breaking below EMA 50 → potential trend weakening.

---

### RSI (Relative Strength Index)

**What it is:** A momentum oscillator that measures the speed and magnitude of price changes, on a scale of 0–100.

**Formula (simplified):** Compares average gains to average losses over 14 days. High ratio → high RSI.

**Key levels:**
- **Above 70** → Overbought. The asset has risen fast; a pullback is possible but not guaranteed.
- **Below 30** → Oversold. The asset has fallen fast; a bounce is possible.
- **50** → Neutral / mid-line. RSI crossing 50 from below can signal a strengthening uptrend.

**Divergence (advanced):**
- **Bullish divergence:** Price makes a new low but RSI makes a higher low → momentum is weakening; potential reversal up.
- **Bearish divergence:** Price makes a new high but RSI makes a lower high → momentum is weakening; potential reversal down.

**Limitations:** In strong trends, RSI can stay overbought/oversold for weeks. RSI above 70 in a momentum bull run isn't necessarily a sell signal.

The dashboard shows RSI as both a badge ("Overbought / Oversold / Neutral") and as a sub-panel chart below the price chart.

---

### MACD

**What it is:** Moving Average Convergence Divergence — a trend-following momentum indicator.

**Three components:**
- **MACD Line** = EMA(12) − EMA(26). Positive when short-term average > long-term average.
- **Signal Line** = EMA(9) of the MACD Line. Smoothed version.
- **Histogram** = MACD Line − Signal Line. Shows the distance between the two.

**How to read them:**
- **MACD crosses above signal line** → bullish crossover (potential buy signal).
- **MACD crosses below signal line** → bearish crossover (potential sell signal).
- **Histogram growing** → momentum is increasing in that direction.
- **Histogram shrinking** → momentum is fading (possible reversal ahead).
- **MACD above zero** → short-term average above long-term average; upward trend.
- **MACD below zero** → downward trend.

**Zero-line crossovers:** When MACD crosses from negative to positive, it confirms a trend change — a stronger (slower) signal than line crossovers.

---

### Volume

**What it is:** The number of shares (or contracts) traded in a given period.

**How to read it:**
- **High volume on an up day** → buyers are aggressive; move is likely to continue.
- **High volume on a down day** → sellers are aggressive.
- **Low volume on a move** → the move may not be sustained ("thin air" rally or drop).
- **Volume spike** → something significant happened (news, earnings, institutional activity).

Volume alone doesn't tell you direction — always read it alongside price.

---

### Support & Resistance

**Support:** A price level where buying has historically been strong enough to halt a decline. Price tends to bounce here.

**Resistance:** A price level where selling pressure has historically capped advances. Price tends to stall or reverse here.

**How FiForesight calculates them:** Automated detection of local swing highs (resistance) and swing lows (support) from the recent price history.

**How to use them:**
- A break above resistance (on high volume) often becomes new support — "resistance flipped to support."
- A break below support often becomes new resistance.
- The closer current price is to support, the better the risk/reward for a long trade (tight stop below support).

---

### Earnings Markers

**What they are:** Vertical lines on the price chart marking known past earnings dates (solid) and estimated upcoming earnings dates (dashed).

**Why they matter:** Earnings releases cause the biggest single-day price moves for most stocks. Implied volatility (IV) in options inflates before earnings and collapses after ("IV crush"). The markers help you see:
- How the stock historically reacted on earnings days.
- Whether an upcoming earnings date falls within your trading window.

---

## 4. Ensemble ML Forecast

**What it is:** FiForesight runs three forecasting models and combines their outputs into a single 48-hour high/low range with a confidence score.

**The three models:**
| Model | Strengths |
|-------|-----------|
| **Prophet** (Meta) | Handles seasonality, holiday effects, and trend changes automatically |
| **SARIMAX** (statsmodels) | Statistical time-series model; good at autocorrelation patterns |
| **Random Forest** (scikit-learn) | Captures non-linear relationships and feature interactions |

**How they're combined:** Inverse-error weighting — models that have been more accurate recently get a higher weight. The ensemble range is the weighted average of each model's high/low output.

**Confidence score:** Derived from the spread of the three models' predictions relative to recent volatility. A tight cluster of model outputs = high confidence. Wide spread = low confidence.

**What the forecast shows:**
- **High Range / Low Range:** The predicted 48-hour price corridor.
- **Trend badge:** Bullish (high range > current price) or Bearish (low range < current price).

**Important caveat:** ML models extrapolate from past price patterns. They cannot predict news events, earnings surprises, macro shocks, or any event not in the training data. Always treat the forecast as one signal among many.

**5-Day Forecast Table:** Shows day-by-day predicted price, high/low band, and confidence for the next 5 trading days — longer-horizon output from Prophet.

---

## 5. Monte Carlo Simulation

**What it is:** A probabilistic simulation that runs 1 000 possible future price paths, using the stock's recent volatility and drift as inputs.

**How it works (simplified):**
1. Calculate daily log-returns from recent history.
2. Estimate mean (drift) and standard deviation (volatility) of those returns.
3. Use Geometric Brownian Motion to simulate 1 000 random paths over 5–10 days.
4. Report percentile outcomes across those paths.

**Key outputs:**

| Metric | Meaning |
|--------|---------|
| **P10** | Price at the 10th percentile — only 10% of paths ended this low or lower. Pessimistic scenario. |
| **P50** | Median price — the midpoint of all simulated paths. |
| **P90** | Price at the 90th percentile — 90% of paths ended below this. Optimistic scenario. |
| **Prob. Gain** | Percentage of paths that ended above the starting price. |
| **VaR-95** | Value at Risk at 95% confidence — the maximum expected loss in 95% of scenarios. E.g. VaR-95 = $4.20 means 95% of paths lose no more than $4.20. |

**Fan chart:** Shows the P10/P50/P90 bands over time as a shaded corridor. The fan widens as time increases, reflecting growing uncertainty.

**3D Probability Surface:** An advanced visualisation showing the full distribution of price outcomes at each future day — the "mountain" of probability.

**Deterministic:** Uses a fixed seed (42) so the same inputs always produce the same output. This makes results reproducible.

**What it doesn't model:** Earnings surprises, gap events, correlation with other assets, or regime changes in volatility.

---

## 6. LLM Analyst Jury

**What it is:** Three independent AI analysts, each with a different investment lens, simultaneously analyse the stock and deliver a verdict.

**The analysts:**

| Analyst | Model | Lens |
|---------|-------|------|
| **Dr. A. Sterling** | Llama 4 Scout (Meta) | Macro & Risk — geopolitical risk, sector headwinds, tail risks |
| **Marcus Chen** | Llama 3.3 70B (Meta) | Growth & Momentum — revenue trajectory, earnings outlook, price momentum |
| **Kai Nakamura** | Qwen3 32B (Alibaba) | Quantitative — valuation ratios, statistical signals, factor analysis |

**How they run:** In parallel via LangGraph (a graph-based orchestration framework). Each analyst receives: current price, RSI, trend, news headlines, VADER sentiment score, model weights, and fundamental metrics. They do NOT communicate with each other — fully independent verdicts.

**Per-analyst output:**
- **Rating:** BUY / HOLD / SELL
- **Confidence:** 0–100%
- **Reasoning:** Free-text rationale in their analytical style
- **Target prices:** High and low price targets

**Consensus Badge:** Shown at the top of the jury panel. Displays the majority rating, average confidence, and agreement fraction (e.g. "BUY 72% 2/3"). This is the aggregate signal to focus on when analysts disagree.

**Failure resilience:** If any analyst's API call fails, that analyst returns Hold / 25% confidence — the other two verdicts are unaffected.

**How to read it:**
- All 3 agree = high-conviction signal.
- 2/3 agree = moderate signal; read the dissenting analyst's rationale.
- All 3 disagree = low conviction; the stock is genuinely ambiguous or the jury hasn't converged.
- Never act on the jury alone — it has no access to real-time order flow, insider activity, or future news.

---

## 7. VADER Sentiment Score

**What it is:** A rule-based sentiment analysis engine (VADER — Valence Aware Dictionary and sEntiment Reasoner) applied to recent news headlines.

**How it works:** VADER scores each headline on a polarity scale from −1.0 (most negative) to +1.0 (most positive), using a lexicon tuned for financial and social media text.

**Outputs:**

| Field | Meaning |
|-------|---------|
| **Compound score** | Normalised aggregate from −1 to +1. Above +0.05 = Bullish. Below −0.05 = Bearish. Between = Neutral. |
| **Label** | Bullish / Bearish / Neutral |
| **Headline count** | Number of headlines scored |

**Limitations:** VADER is a lexicon-based model — it doesn't understand context, sarcasm, or nuanced financial language. "Inflation rises, Fed raises rates" might be scored neutrally even though it's bearish for growth stocks. The jury analysts receive this score as context, but they apply deeper reasoning on top of it.

---

## 8. DCF Intrinsic Value

**What it is:** A Discounted Cash Flow (DCF) model that estimates what the company is fundamentally worth per share, based on its free cash flow and expected growth.

**How it works:**
1. Fetch trailing free cash flow (FCF) from yfinance fundamentals.
2. Compute WACC (Weighted Average Cost of Capital) = Risk-Free Rate (4.5%) + beta × Equity Risk Premium (5.5%).
3. Project FCF forward 5 years at each growth rate scenario.
4. Add a terminal value (Gordon Growth Model at 2.5% perpetual growth).
5. Discount all cash flows back to present value.
6. Divide by shares outstanding → intrinsic value per share.

**Three scenarios:**

| Scenario | WACC | Growth Rate |
|----------|------|-------------|
| **Bear** | Base + 1.5% | Base − 3% |
| **Base** | Derived from beta | Analyst consensus estimate |
| **Bull** | Base − 1.5% | Base + 3% |

**MOS (Margin of Safety):** The difference between the base-case intrinsic value and the current market price, shown as a percentage.
- **Green MOS (e.g. +25% MOS):** Stock is trading below intrinsic value — potentially undervalued.
- **Red MOS (e.g. −15% MOS):** Stock is trading above intrinsic value — potentially overvalued.

**Important limitations:**
- DCF is only as good as the FCF and growth estimates. Unprofitable companies, companies with negative FCF, or high-growth tech companies are poorly served by DCF.
- The model returns a 422 error and no card if FCF ≤ 0.
- This is a simplified single-stage DCF. Real analyst models use multi-stage DCF, detailed capex/working capital projections, and scenario-specific discount rates.

---

## 9. Trade Setup Card

**What it is:** A structured trade plan based on the forecast, technical indicators, and position sizing rules.

**Components:**

| Field | Meaning |
|-------|---------|
| **Entry Zone** | Suggested buy range (low to high). Based on current price and momentum signals. |
| **Stop Loss** | The price at which you exit the trade to cap your loss. Placed below key support or a technical level. |
| **T1 / T2 / T3** | Three price targets in ascending order. T1 = conservative first target (often near resistance). T2 = mid target. T3 = full target. |
| **R:R (Risk:Reward)** | Ratio of potential gain to potential loss. E.g. R:R 2.4 means you risk $1 to make $2.40. Generally want R:R ≥ 2.0. |
| **Setup Type** | Classification: Bullish Breakout, Bearish Breakdown, Momentum, Reversal, etc. |

**Position Sizing (1% Rule):**

| Field | Meaning |
|-------|---------|
| **Risk/share** | Distance from entry midpoint to stop loss in dollars. |
| **Risk %** | Risk/share as a percentage of entry price. |
| **Suggested position** | What percentage of your total portfolio to allocate. Calculated so that if stop loss is hit, you lose exactly 1% of portfolio value. Capped at 5% regardless of how tight the stop is. |

**Example:** Entry $100, Stop $97, portfolio $10 000.
- Risk/share = $3 (3%)
- 1% of portfolio = $100
- Shares to buy = $100 / $3 = 33 shares
- Position value = 33 × $100 = $3 300 = **33% allocation**... capped at **5% = $500 / $100 = 5 shares**

The 1% rule keeps any single trade from doing significant damage to a portfolio.

**This is not financial advice.** The stop level, targets, and sizing are algorithmic suggestions. Always adjust to your own risk tolerance and account size.

---

## 10. Options Chain Panel

**What it is:** Live options data for the nearest upcoming expiry date, showing calls and puts.

**Terminology:**

| Term | Meaning |
|------|---------|
| **Call** | Option to buy the stock at the strike price. Profits if stock rises above strike. |
| **Put** | Option to sell the stock at the strike price. Profits if stock falls below strike. |
| **Strike** | The price at which the option can be exercised. |
| **Last** | Most recent trade price for this contract. |
| **Bid / Ask** | The market's buy/sell spread for the contract. Wide spread = illiquid. |
| **Chg%** | Change in contract price since previous close, as a percentage. |
| **Volume** | Number of contracts traded today. Higher = more activity. |
| **OI (Open Interest)** | Total number of open contracts. High OI at a strike = significant level to watch. |
| **IV% (Implied Volatility)** | The market's expectation of future volatility, implied by option prices. High IV = expensive options (market expects large moves). |
| **ITM (In the Money)** | Highlighted rows. A call is ITM when strike < current price. A put is ITM when strike > current price. ITM options have intrinsic value. |

**Expiry selector:** Up to 8 upcoming expiry dates. Near-term expiries (weekly options) are more sensitive to price moves (higher gamma). Longer-dated options (LEAPs) give more time for a thesis to play out.

**Filter:** Only strikes within ±25% of current price are shown, to keep the table readable.

**What to look for:**
- Large OI concentration at a strike = the market expects price to gravitate toward or stay below/above that level ("max pain" theory).
- Very high IV on near-term options = market expects a big move (earnings, news event).
- Low IV = relatively cheap options if you expect volatility to increase.

---

## 11. Fundamentals Panel

**What it is:** A snapshot of the company's financial characteristics, sourced from yfinance fundamentals.

**Metrics explained:**

| Metric | What it measures | What to look for |
|--------|-----------------|-----------------|
| **Market Cap** | Total market value (price × shares). Large cap = >$10B. | Context for scale and risk. |
| **P/E Ratio** | Price ÷ Earnings per share (trailing). How much you pay for $1 of earnings. | Industry average varies widely. High P/E = growth expectations. |
| **Forward P/E** | Price ÷ estimated next-year EPS. | Lower than trailing P/E = earnings expected to grow. |
| **PEG Ratio** | P/E ÷ earnings growth rate. Adjusts for growth. | PEG < 1 often considered undervalued. |
| **Price/Book** | Price ÷ book value per share. How much above asset value you're paying. | <1 = trading below assets. |
| **EV/EBITDA** | Enterprise Value ÷ EBITDA. Useful for comparing capital-intensive companies. | Lower = cheaper. |
| **Free Cash Flow** | Cash generated after capex. The "real" earnings. | Positive and growing = healthy. |
| **Revenue Growth** | Year-over-year revenue change. | High growth justifies high P/E for some companies. |
| **Total Debt** | Total debt on the balance sheet. | High debt + rising rates = risk. |
| **Beta** | Volatility relative to the market. Beta 1 = moves with market. Beta 2 = twice as volatile. | High beta = more risk, more reward potential. |
| **Dividend Yield** | Annual dividend ÷ price. | Income investors target 2–5%. Very high yield may signal distress. |
| **52-Week Range** | The stock's highest and lowest price in the past year. | Where in its range is it trading? Near lows vs near highs changes risk/reward. |
| **Sector / Industry** | Classification for peer comparison. | Useful for benchmarking multiples. |

---

## 12. Peer Comparison Panel

**What it is:** Side-by-side fundamentals for the searched ticker and up to 5 sector peers, so you can benchmark valuation and metrics.

**How to use it:** Look for outliers. If your stock has a P/E of 35 while peers average 18, is it justified by faster growth (check revenue growth and forward P/E)? Or is it simply expensive?

**Data source:** Peers are selected based on sector/industry tags from yfinance. The comparison uses the same fundamental fields as the Fundamentals Panel.

---

## 13. News Feed

**What it is:** The 5–10 most recent news headlines for the ticker, sourced via SerpAPI.

**Fields:** Title, source publication, date, and thumbnail (where available). Each headline links to the full article.

**How it feeds into analysis:** Headlines are scored by VADER before the LLM jury runs — the jury analysts see the sentiment score and label as part of their context. This means market-moving news from the past 24–48 hours can influence the jury verdict.

**Limitation:** News is as recent as SerpAPI's index. Breaking news in the last few minutes may not be reflected.

---

## 14. Portfolio Simulation

**Where to find it:** The `/simulation` page — linked from the "Portfolio Race" button in the header.

**Two modes:**

### Suggest Portfolio
- Choose a **risk level** (conservative / balanced / aggressive) and **budget**.
- The app queries SerpAPI and yfinance to suggest a portfolio of tickers suited to that risk profile.
- Conservative → dividend payers, large-cap value. Aggressive → high-growth, higher-beta names.

### Performance Simulation
- Enter a list of holdings (ticker + quantity + optional purchase date).
- The app fetches historical prices and computes the portfolio's value over time.
- Output: a time-series chart of total portfolio value, P&L, and per-holding breakdown.

**State persistence:** Your simulation is saved to InfluxDB and can be retrieved later via the state ID.

**Use case:** "If I had bought $5 000 of AAPL and $3 000 of MSFT 6 months ago, what would I have today?" — without risking real money.

---

## 15. Auth & Account

**What it is:** Optional Supabase email/password authentication. The app works fully without signing in.

**Sign Up:** Creates an account on the Supabase project. A confirmation email may be required depending on Supabase project settings.

**Sign In:** Authenticates and persists the session across page refreshes using `onAuthStateChange`.

**Sign Out:** Clears the session. The header reverts to the Sign In button.

**Current scope:** Auth is the foundation for future features — watchlists, price alerts, saved searches, and personalised settings.

---

## 16. AI Chat Assistant

**What it is:** A streaming chat panel (accessible via the chat icon) powered by Groq's API (Llama model).

**Context:** The assistant is aware of the currently loaded ticker, current price, RSI, trend, and analyst verdict. You can ask it to explain indicators, interpret the jury, or discuss the company.

**Streaming:** Responses stream token-by-token so you see the answer as it's generated, rather than waiting for the full response.

**Limitations:** The assistant has knowledge up to its training cutoff. It doesn't have real-time internet access or access to your account/portfolio. If the Groq API is unavailable, the stream will return "Streaming unavailable" rather than exposing error details.

---

## 17. Reading Signals Together

Having many signals is only useful if you know how to combine them. Here's a practical framework:

### Bullish setup checklist
- [ ] Price above SMA 50 and SMA 200 (uptrend confirmed)
- [ ] RSI between 40–65 (momentum without being overbought)
- [ ] MACD above signal line (positive momentum)
- [ ] Bollinger Bands expanding upward (trend strengthening)
- [ ] Volume above average on up days
- [ ] LLM jury: 2/3 or 3/3 BUY
- [ ] Sentiment: Bullish
- [ ] DCF: Positive margin of safety (undervalued)
- [ ] Monte Carlo P50 > current price
- [ ] Earnings not imminent (avoid holding through binary events unless intentional)

### Bearish setup checklist
- [ ] Price below SMA 50 and SMA 200 (downtrend)
- [ ] RSI below 45
- [ ] MACD below signal line
- [ ] LLM jury: 2/3 or 3/3 SELL
- [ ] Sentiment: Bearish
- [ ] High OI at puts below current price

### When signals conflict
Conflicting signals are normal and usually mean the stock is at an inflection point. This is when conviction should be low:
- Wait for a clearer setup.
- Size the position smaller.
- Use options to define risk (max loss = premium paid).
- Read the jury analysts' individual rationales — the dissenting analyst's argument often identifies the real risk.

### Common signal traps
- **RSI overbought in a strong trend:** RSI above 70 during a breakout is normal. Don't sell early just because RSI is high.
- **High DCF upside on a money-losing company:** DCF requires positive FCF. If the company burns cash, the DCF number is not meaningful.
- **Jury BUY but sentiment Bearish:** The jury has more context (fundamentals, targets) than raw headline sentiment. Weight the jury more heavily unless you see a specific market-moving headline.
- **Tight Bollinger Bands (squeeze) + upcoming earnings:** A volatility explosion is likely — but direction is unknown. Options strategies like straddles may be appropriate.

---

*FiForesight is for educational purposes only and does not constitute financial advice. Always do your own research before making investment decisions.*
