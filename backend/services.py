# backend/services.py
import re
import logging
import httpx
import pandas as pd
from datetime import datetime, timezone

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
    logging.getLogger(__name__).info(
        "[YFINANCE] ✓ yfinance package loaded successfully"
    )
except ImportError:
    yf = None  # type: ignore
    YFINANCE_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "[YFINANCE] ✗ yfinance not installed — run: pip install yfinance"
    )

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# InfluxDB Service  —  stores and retrieves full OHLCV data
# ---------------------------------------------------------------------------

class InfluxService:
    def __init__(self):
        logger.info(
            f"[INFLUXDB] Initialising client — url={Config.INFLUXDB_URL}, "
            f"org={Config.INFLUXDB_ORG}, bucket={Config.INFLUXDB_BUCKET}, "
            f"token_set={'yes' if Config.INFLUXDB_TOKEN else 'NO — writes will fail'}"
        )
        self.client = InfluxDBClient(
            url=Config.INFLUXDB_URL,
            token=Config.INFLUXDB_TOKEN,
            org=Config.INFLUXDB_ORG,
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()
        logger.info("[INFLUXDB] ✓ Client ready (write_api=SYNCHRONOUS)")

    # --- Write a single live close price (used for intraday snapshots) -------
    def write_price(self, symbol: str, price: float):
        logger.info(f"[INFLUXDB] write_price — symbol={symbol}, price=${price:.2f}")
        try:
            p = (
                Point("market_data")
                .tag("symbol", symbol)
                .field("close", float(price))
                .time(datetime.now(timezone.utc), WritePrecision.NS)
            )
            self.write_api.write(
                bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p
            )
            logger.info(
                f"[INFLUXDB] ✓ write_price — {symbol} @ ${price:.2f} stored "
                f"(measurement=market_data, field=close)"
            )
        except Exception as e:
            logger.error(f"[INFLUXDB] ✗ write_price error for {symbol}: {e}")

    # --- Write a full OHLCV batch (from yfinance) ----------------------------
    def write_ohlcv_batch(self, symbol: str, df: pd.DataFrame):
        """
        df must have a DatetimeIndex (UTC) and columns: Open, High, Low, Close, Volume.
        InfluxDB Cloud has a 30-day retention policy — rows older than 29 days are skipped.
        """
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=29)

        logger.info(
            f"[INFLUXDB] write_ohlcv_batch — symbol={symbol}, df_rows={len(df)}, "
            f"retention_cutoff={cutoff.date()} (last 29 days)"
        )

        points  = []
        skipped = 0
        for ts, row in df.iterrows():
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            if ts < cutoff:
                skipped += 1
                continue   # outside retention window
            p = (
                Point("market_data")
                .tag("symbol", symbol)
                .field("open",   float(row.get("Open",   row.get("open",   0))))
                .field("high",   float(row.get("High",   row.get("high",   0))))
                .field("low",    float(row.get("Low",    row.get("low",    0))))
                .field("close",  float(row.get("Close",  row.get("close",  0))))
                .field("volume", float(row.get("Volume", row.get("volume", 0))))
                .time(ts, WritePrecision.NS)
            )
            points.append(p)

        logger.info(
            f"[INFLUXDB] Batch analysis — total_rows={len(df)}, "
            f"skipped_outside_retention={skipped}, queued_to_write={len(points)}"
        )

        if not points:
            logger.warning(
                f"[INFLUXDB] write_ohlcv_batch — 0 points to write for {symbol} "
                f"(all {skipped} rows were outside the 29-day retention window)"
            )
            return

        try:
            self.write_api.write(
                bucket=Config.INFLUXDB_BUCKET,
                org=Config.INFLUXDB_ORG,
                record=points,
            )
            logger.info(
                f"[INFLUXDB] ✓ write_ohlcv_batch — wrote {len(points)} OHLCV rows for {symbol} "
                f"(skipped {skipped} rows outside retention)"
            )
        except Exception as e:
            logger.error(f"[INFLUXDB] ✗ write_ohlcv_batch error for {symbol}: {e}")

    # --- Query stored OHLCV history ------------------------------------------
    def query_history(self, symbol: str, days: int = 365) -> list:
        """
        Returns list of dicts with keys: _time, open, high, low, close, volume
        """
        logger.info(
            f"[INFLUXDB] query_history — symbol={symbol}, range=last {days}d, "
            f"measurement=market_data"
        )
        query = f"""
        from(bucket: "{Config.INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r["_measurement"] == "market_data" and r["symbol"] == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> sort(columns: ["_time"], desc: false)
        """
        try:
            tables = self.query_api.query(query)
            rows   = [r.values for t in tables for r in t.records]

            out = []
            for row in rows:
                out.append({
                    "_time":  row.get("_time"),
                    "open":   float(row.get("open",   row.get("close", 0)) or 0),
                    "high":   float(row.get("high",   row.get("close", 0)) or 0),
                    "low":    float(row.get("low",    row.get("close", 0)) or 0),
                    "close":  float(row.get("close",  0) or 0),
                    "volume": float(row.get("volume", 0) or 0),
                })

            if out:
                times    = [r["_time"] for r in out if r["_time"] is not None]
                date_min = min(times).date() if times else "?"
                date_max = max(times).date() if times else "?"
                logger.info(
                    f"[INFLUXDB] ✓ query_history — {len(out)} rows returned for {symbol} | "
                    f"date range: {date_min} → {date_max} | "
                    f"close: ${out[0]['close']:.2f} (oldest) → ${out[-1]['close']:.2f} (latest)"
                )
            else:
                logger.warning(
                    f"[INFLUXDB] query_history — 0 rows returned for {symbol} "
                    f"(symbol not in DB or range too narrow)"
                )
            return out

        except Exception as e:
            logger.error(f"[INFLUXDB] ✗ query_history error for {symbol}: {e}")
            return []

    def has_recent_data(self, symbol: str, within_hours: int = 20) -> bool:
        """Return True if we already have fresh data for today (avoids re-fetching)."""
        logger.info(
            f"[INFLUXDB] has_recent_data — symbol={symbol}, "
            f"checking last {within_hours}h ..."
        )
        query = f"""
        from(bucket: "{Config.INFLUXDB_BUCKET}")
          |> range(start: -{within_hours}h)
          |> filter(fn: (r) => r["_measurement"] == "market_data" and r["symbol"] == "{symbol}")
          |> count()
          |> limit(n: 1)
        """
        try:
            tables = self.query_api.query(query)
            for t in tables:
                for r in t.records:
                    count = r.get_value() or 0
                    if count > 0:
                        logger.info(
                            f"[INFLUXDB] Cache HIT — {count} record(s) found for {symbol} "
                            f"within last {within_hours}h → yfinance fetch will be SKIPPED"
                        )
                        return True
                    else:
                        logger.info(
                            f"[INFLUXDB] Cache MISS — 0 records for {symbol} "
                            f"within last {within_hours}h → yfinance fetch required"
                        )
                        return False
        except Exception as e:
            logger.error(f"[INFLUXDB] ✗ has_recent_data error for {symbol}: {e}")

        logger.info(
            f"[INFLUXDB] Cache MISS — no records returned for {symbol} "
            f"(query returned empty) → yfinance fetch required"
        )
        return False


# ---------------------------------------------------------------------------
# YFinance Service  —  free historical OHLCV + fundamentals
# ---------------------------------------------------------------------------

class YFinanceService:
    """
    Wraps yfinance for:
      - Full OHLCV history (1d bars, up to 2 years)
      - Company fundamentals (P/E, market cap, 52w range, dividend yield)
      - Current/last known price
    yfinance is completely free — no API key needed.
    """

    @staticmethod
    def _to_yf_symbol(symbol: str) -> str:
        """Convert SerpAPI-style 'NVDA:NASDAQ' → 'NVDA' for yfinance."""
        converted = symbol.split(":")[0].upper()
        if converted != symbol:
            logger.info(f"[YFINANCE] Symbol normalised: '{symbol}' → '{converted}'")
        return converted

    def fetch_history(self, symbol: str, period: str = "2y") -> pd.DataFrame:
        """
        Fetch daily OHLCV for `period` (e.g. '2y', '1y', '6mo').
        Returns a DataFrame with DatetimeIndex (UTC) and columns:
        Open, High, Low, Close, Volume.
        Returns empty DataFrame on failure.
        """
        if not YFINANCE_AVAILABLE:
            logger.error("[YFINANCE] ✗ fetch_history SKIPPED — yfinance not installed")
            return pd.DataFrame()

        ticker = self._to_yf_symbol(symbol)
        logger.info(
            f"[YFINANCE] fetch_history — ticker={ticker}, period={period}, "
            f"interval=1d, auto_adjust=True, timeout=20s"
        )

        try:
            df = yf.download(
                ticker,
                period=period,
                interval="1d",
                progress=False,
                auto_adjust=True,
                timeout=20,
            )

            if df.empty:
                logger.warning(
                    f"[YFINANCE] ✗ fetch_history — empty response for {ticker} "
                    f"(ticker may be invalid or delisted)"
                )
                return pd.DataFrame()

            # Flatten MultiIndex columns if present (yfinance ≥0.2 quirk)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df.index = pd.to_datetime(df.index)
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")

            keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df   = df[keep].dropna(subset=["Close"])

            logger.info(
                f"[YFINANCE] ✓ fetch_history — {len(df)} rows for {ticker} | "
                f"date range: {df.index.min().date()} → {df.index.max().date()} | "
                f"close: ${float(df['Close'].iloc[0]):.2f} (oldest) → "
                f"${float(df['Close'].iloc[-1]):.2f} (latest) | "
                f"columns: {list(df.columns)}"
            )
            return df

        except Exception as e:
            logger.error(f"[YFINANCE] ✗ fetch_history error for {ticker}: {e}")
            return pd.DataFrame()

    def fetch_info(self, symbol: str) -> dict:
        """
        Returns a dict of fundamentals:
        market_cap, pe_ratio, dividend_yield, prev_close, range_52w, current_price
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("[YFINANCE] fetch_info SKIPPED — yfinance not installed")
            return {}

        ticker = self._to_yf_symbol(symbol)
        logger.info(f"[YFINANCE] fetch_info — ticker={ticker}")

        try:
            info       = yf.Ticker(ticker).info
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
            high52     = info.get("fiftyTwoWeekHigh")
            low52      = info.get("fiftyTwoWeekLow")
            range_52w  = f"{low52:.2f} - {high52:.2f}" if high52 and low52 else "N/A"
            current    = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
                or 0.0
            )
            result = {
                "current_price":   float(current),
                "market_cap":      info.get("marketCap",      "N/A"),
                "pe_ratio":        info.get("trailingPE",     "N/A"),
                "dividend_yield":  info.get("dividendYield",  "N/A"),
                "prev_close":      prev_close or "N/A",
                "range_52w":       range_52w,
                "short_name":      info.get("shortName",  ticker),
                "sector":          info.get("sector",     "N/A"),
                "currency":        info.get("currency",   "USD"),
            }
            logger.info(
                f"[YFINANCE] ✓ fetch_info — {ticker}: "
                f"price=${result['current_price']:.2f}, "
                f"market_cap={result['market_cap']}, "
                f"pe={result['pe_ratio']}, "
                f"div_yield={result['dividend_yield']}, "
                f"52w={result['range_52w']}, "
                f"sector={result['sector']}, "
                f"currency={result['currency']}"
            )
            return result

        except Exception as e:
            logger.error(f"[YFINANCE] ✗ fetch_info error for {ticker}: {e}")
            return {}

    def get_live_price(self, symbol: str) -> float:
        """Fast path to get the latest price from yfinance."""
        if not YFINANCE_AVAILABLE:
            logger.warning("[YFINANCE] get_live_price SKIPPED — yfinance not installed")
            return 0.0

        ticker = self._to_yf_symbol(symbol)
        logger.info(f"[YFINANCE] get_live_price — ticker={ticker}")

        try:
            t     = yf.Ticker(ticker)
            price = (
                t.info.get("currentPrice")
                or t.info.get("regularMarketPrice")
                or t.info.get("previousClose")
                or 0.0
            )
            price_f = float(price)
            if price_f > 0:
                logger.info(f"[YFINANCE] ✓ get_live_price — {ticker} = ${price_f:.2f}")
            else:
                logger.warning(
                    f"[YFINANCE] get_live_price — {ticker} returned 0.0 "
                    f"(currentPrice/regularMarketPrice/previousClose all missing)"
                )
            return price_f

        except Exception as e:
            logger.error(f"[YFINANCE] ✗ get_live_price error for {ticker}: {e}")
            return 0.0


# ---------------------------------------------------------------------------
# Data Cleaner  —  gap-fill, outlier removal, normalise
# ---------------------------------------------------------------------------

class DataCleaner:
    """
    Cleans a raw OHLCV DataFrame before it goes to InfluxDB or the models.
    """

    @staticmethod
    def clean(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            logger.warning("[CLEANER] clean() — input DataFrame is empty, returning as-is")
            return df

        input_rows = len(df)
        logger.info(
            f"[CLEANER] clean() — input: {input_rows} rows | "
            f"close range: ${float(df['Close'].min()):.2f} – ${float(df['Close'].max()):.2f}"
        )

        df = df.copy()
        df.sort_index(inplace=True)

        # 1. Drop rows where Close is zero or NaN
        df = df[df["Close"].notna() & (df["Close"] > 0)]
        after_nan_drop = len(df)
        nan_removed    = input_rows - after_nan_drop
        if nan_removed:
            logger.info(f"[CLEANER] NaN/zero Close rows removed: {nan_removed}")
        else:
            logger.info(f"[CLEANER] NaN/zero check — 0 rows removed (all Close values valid)")

        if df.empty:
            logger.warning("[CLEANER] DataFrame empty after NaN/zero drop — returning empty")
            return df

        # 2. Remove outliers: Close values > 4σ from rolling 30-day median
        rolling_med = df["Close"].rolling(30, min_periods=5, center=True).median()
        rolling_std = df["Close"].rolling(30, min_periods=5, center=True).std()
        upper = rolling_med + 4 * rolling_std
        lower = rolling_med - 4 * rolling_std
        mask  = (df["Close"] >= lower) & (df["Close"] <= upper)
        removed = int((~mask).sum())
        if removed:
            logger.info(
                f"[CLEANER] Outlier rows removed (>4σ from 30d rolling median): {removed}"
            )
        else:
            logger.info(
                f"[CLEANER] Outlier check — 0 rows removed (all within 4σ rolling bands)"
            )
        df = df[mask]
        after_outlier = len(df)

        if df.empty:
            logger.warning("[CLEANER] DataFrame empty after outlier removal — returning empty")
            return df

        # 3. Reindex to business-day frequency and forward-fill gaps
        try:
            full_idx = pd.bdate_range(
                start=df.index.min(), end=df.index.max(), freq="B"
            )
            full_idx = full_idx.tz_localize("UTC") if full_idx.tz is None else full_idx
            df = df.reindex(full_idx).ffill()
            after_ffill = len(df)
            synthetic   = after_ffill - after_outlier
            logger.info(
                f"[CLEANER] Gap-fill (bdate_range ffill) — "
                f"rows before={after_outlier}, after={after_ffill} "
                f"(+{synthetic} synthetic business-day rows forward-filled)"
            )
        except Exception as e:
            logger.warning(
                f"[CLEANER] bdate_range reindex FAILED ({e}) — gap-fill SKIPPED, "
                f"proceeding with {after_outlier} rows"
            )

        if df.empty:
            logger.warning("[CLEANER] DataFrame empty after gap-fill — returning empty")
            return df

        # 4. Ensure High >= Close >= Low (yfinance adjusted data can drift)
        if "High" in df.columns and "Low" in df.columns:
            df["High"] = df[["High", "Close"]].max(axis=1)
            df["Low"]  = df[["Low",  "Close"]].min(axis=1)
            logger.info("[CLEANER] OHLC integrity enforced — High≥Close≥Low corrected")

        logger.info(
            f"[CLEANER] ✓ clean() complete — output: {len(df)} rows "
            f"(from {input_rows} input, net delta={len(df) - input_rows:+d})"
        )
        return df

    @staticmethod
    def to_history_list(df: pd.DataFrame) -> list:
        """Convert cleaned DataFrame → list of dicts used by main.py and models."""
        logger.info(f"[CLEANER] to_history_list() — converting {len(df)} rows to dicts")
        out = []
        for ts, row in df.iterrows():
            out.append({
                "_time":  ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                "open":   float(row.get("Open",   row.get("Close", 0))),
                "high":   float(row.get("High",   row.get("Close", 0))),
                "low":    float(row.get("Low",    row.get("Close", 0))),
                "close":  float(row.get("Close",  0)),
                "volume": float(row.get("Volume", 0)),
            })
        logger.info(
            f"[CLEANER] ✓ to_history_list() — {len(out)} dict rows produced | "
            f"close: ${out[0]['close']:.2f} (oldest) → ${out[-1]['close']:.2f} (latest)"
        )
        return out


# ---------------------------------------------------------------------------
# SerpAPI Service  —  live news & trending tickers
# ---------------------------------------------------------------------------

class SerpService:
    @staticmethod
    def clean_price(price_str):
        if price_str is None:
            return 0.0
        if isinstance(price_str, (int, float)):
            return float(price_str)
        cleaned = re.sub(r"[^\d.-]", "", str(price_str))
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    async def fetch_data(self, query: str) -> dict:
        """
        Query SerpAPI Google Finance for news and trending market data.
        Returns a dict with keys:
          - news_results : list of news articles
          - markets      : dict of category → list of tickers
        Falls back to empty structure if the API key is missing or the call fails.
        """
        if not Config.SERP_API_KEY:
            logger.info(
                f"[SERP] API key not set — news/trending fetch SKIPPED "
                f"(returning empty news_results and markets)"
            )
            return {"news_results": [], "markets": {}}

        logger.info(
            f"[SERP] fetch_data — query='{query}', engine=google_finance, timeout=25s"
        )
        params = {
            "engine":  "google_finance",
            "q":       query,
            "api_key": Config.SERP_API_KEY,
        }
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.get("https://serpapi.com/search", params=params)
                resp.raise_for_status()
                data = resp.json()

            news_count    = len(data.get("news_results", []))
            market_cats   = list(data.get("markets", {}).keys())
            market_total  = sum(
                len(v) for v in data.get("markets", {}).values() if isinstance(v, list)
            )
            logger.info(
                f"[SERP] ✓ fetch_data — query='{query}' | "
                f"news_articles={news_count} | "
                f"market_categories={market_cats} | "
                f"trending_tickers={market_total}"
            )
            return {
                "news_results": data.get("news_results", []),
                "markets":      data.get("markets",      {}),
            }

        except Exception as e:
            logger.error(f"[SERP] ✗ fetch_data error for '{query}': {e}")
            return {"news_results": [], "markets": {}}


# ---------------------------------------------------------------------------
# Analyst Jury  —  3 personas, each pinned to a different model & provider
#
#   KIMI-K2   → Groq moonshotai/kimi-k2-instruct (free tier)      — Macro & Risk lens
#   LLAMA-70B → Groq llama-3.3-70b-versatile    (14,400 RPD free) — Growth lens
#   QWEN3-32B → Groq qwen/qwen3-32b             (free tier)       — Quant lens
#
#   _ai_note uses Groq llama-3.3-70b independently (header note, not jury)
# ---------------------------------------------------------------------------

ANALYST_PERSONAS = [
    {
        "id":          "KIMI-K2",
        "avatar":      "K2",
        "title":       "Macro & Risk Lens",
        "model_label": "Groq · Kimi K2",
        "provider":    "groq",
        "api_model":   "moonshotai/kimi-k2-instruct",
        "color":       "#94a3b8",
        "system": (
            "You are KIMI-K2, a macro-economic and risk analyst running on Moonshot AI Kimi K2. "
            "Your lens is downside scenarios, warning signals, and risk-adjusted positioning. "
            "Analyse the provided market data and news results. "
            "Identify systemic risks, fundamental red flags, and external headwinds "
            "that could materially impact this asset. "
            "Flag RSI extremes, negative trend slope, elevated volatility, or concerning forecast skew. "
            "Examine BB band squeeze/expansion, proximity to support/resistance, whether volume confirms "
            "or contradicts the move, and any fundamental red flags. "
            "Focus on what could go wrong, not growth upside. "
            "Be specific, actionable, and advisory — not generic. "
            "Conclude with a clear rating (Strong Sell / Sell / Hold) and your recommended risk stance."
        ),
    },
    {
        "id":          "LLAMA-70B",
        "avatar":      "70B",
        "title":       "Growth Lens",
        "model_label": "Groq · llama-3.3-70b",
        "provider":    "groq",
        "api_model":   "llama-3.3-70b-versatile",
        "color":       "#00f2ff",
        "system": (
            "You are LLAMA-70B, a fundamental growth equity analyst running on Llama 3.3 70B. "
            "Your lens is momentum, corporate catalysts, and upside potential. "
            "Analyse the provided market data and SERP news results. "
            "Identify fundamental tailwinds, earnings momentum, product or sector catalysts, "
            "and breakout potential. Correlate positive news flow with price momentum and volume trends. "
            "Reference MACD momentum, SMA50/200 positioning, RSI strength, and forecast confidence. "
            "Ignore macro doomsday scenarios — focus on this asset's specific growth trajectory "
            "and why it has the potential to outperform. "
            "Be specific, actionable, and advisory — not generic. "
            "Conclude with a clear rating (Strong Buy / Buy / Hold) and an upside price target or range."
        ),
    },
    {
        "id":          "QWEN3-32B",
        "avatar":      "QW",
        "title":       "Quant Lens",
        "model_label": "Groq · Qwen3 32B",
        "provider":    "groq",
        "api_model":   "qwen/qwen3-32b",
        "max_tokens":  2048,
        "color":       "#10b981",
        "system": (
            "You are QWEN3-32B, a quantitative signal analyst running on Alibaba Qwen3 32B. "
            "You operate purely on technical indicators and statistical signals — no macro bias, no news sentiment. "
            "Analyse the provided OHLCV data and indicator outputs. "
            "Interpret RSI regime, MACD histogram crossover state, Bollinger Band width and price position, "
            "SMA50/200 crossover proximity and % distance, annualised volatility, "
            "and volume confirmation of the trend. Cite the forecast confidence label explicitly. "
            "Map each signal to a clear probabilistic implication. Be precise and data-first. "
            "Conclude with a clear quantitative rating (Accumulate / Hold / Distribute) "
            "and identify specific technical entry and exit levels where applicable."
        ),
    },
]


NOTE_PROMPT_SUFFIX = (
    "\n\nRespond ONLY with valid JSON in exactly this format (no extra text):\n"
    '{"rating": "<Strong Buy|Buy|Hold|Sell|Strong Sell|Low Risk|Medium Risk|High Risk|Accumulate|Distribute>", '
    '"note": "<3-4 advisory sentences, up to 420 chars, with specific signals and implications>", '
    '"confidence": <integer 10-95>}'
)


class AnalystJuryService:
    """
    Routes analyst persona calls to the correct provider API.

    Routing logic:
      - provider == 'groq'  → Groq OpenAI-compatible endpoint (all 3 personas)

    Each persona is pinned to its own model with no cross-provider fallback,
    ensuring each analyst genuinely reflects its own model's reasoning.
    """

    GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    # ------------------------------------------------------------------
    # Internal: generic OpenAI-compatible POST (Groq)
    # ------------------------------------------------------------------

    async def _call_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        model: str,
        system: str,
        user: str,
        provider_label: str,
        max_tokens: int = 320,
    ) -> str:
        """
        Generic OpenAI-compatible POST (Groq).
        Raises httpx.HTTPStatusError on non-2xx so callers can inspect status codes.
        """
        if not api_key:
            raise ValueError(f"{provider_label} API key not configured")

        logger.info(
            f"[{provider_label}] POST → {base_url} | "
            f"model={model}, max_tokens={max_tokens}, temperature=0.65, "
            f"system_chars={len(system)}, user_chars={len(user)}"
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }
        body = {
            "model":       model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "max_tokens":  max_tokens,
            "temperature": 0.65,
        }
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(base_url, json=body, headers=headers)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()

        logger.info(
            f"[{provider_label}] ✓ Response — model={model}, "
            f"response_chars={len(content)}, "
            f"http_status={resp.status_code}"
        )
        return content

    # ------------------------------------------------------------------
    # Internal: provider-specific wrapper
    # ------------------------------------------------------------------

    async def _call_groq(
        self, model: str, system: str, user: str, max_tokens: int = 320
    ) -> str:
        logger.info(
            f"[GROQ] _call_groq — model={model}, max_tokens={max_tokens}"
        )
        result = await self._call_openai_compatible(
            base_url=self.GROQ_BASE_URL,
            api_key=Config.GROQ_API_KEY,
            model=model,
            system=system,
            user=user,
            provider_label="GROQ",
            max_tokens=max_tokens,
        )
        logger.info(
            f"[GROQ] ✓ _call_groq complete — model={model}, "
            f"response_chars={len(result)}"
        )
        return result

    # ------------------------------------------------------------------
    # Internal: robust structured response parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_analyst_response(raw: str, persona_id: str = "?") -> dict:
        import json

        logger.info(
            f"[JURY/{persona_id}] _parse_analyst_response — "
            f"raw_chars={len(raw)}, "
            f"has_think_block={'yes' if '<think>' in raw else 'no'}"
        )

        # Strip reasoning-model thinking blocks (Qwen3 emits <think>...</think>)
        if "<think>" in raw:
            if "</think>" in raw:
                cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                logger.info(
                    f"[JURY/{persona_id}] <think> block stripped — "
                    f"remaining_chars={len(cleaned)}"
                )
            else:
                # Truncated mid-think — no JSON output yet; fall through to regex fallback
                cleaned = ""
                logger.warning(
                    f"[JURY/{persona_id}] Truncated <think> block (no </think>) — "
                    f"model ran out of tokens mid-reasoning, cleaned=''"
                )
        else:
            cleaned = raw.strip()

        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        cleaned = cleaned.replace("```", "").strip()

        # ── Primary: brace-depth JSON extraction ─────────────────────────────
        try:
            start = cleaned.index("{")
            depth, end = 0, -1
            for i, ch in enumerate(cleaned[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end != -1:
                parsed = json.loads(cleaned[start: end + 1])
                if "rating" in parsed:
                    logger.info(
                        f"[JURY/{persona_id}] ✓ Parse path: PRIMARY (brace-depth JSON) — "
                        f"rating={parsed.get('rating')}, confidence={parsed.get('confidence')}"
                    )
                    return parsed
        except (ValueError, json.JSONDecodeError):
            logger.debug(
                f"[JURY/{persona_id}] Primary brace-depth parse failed — "
                f"trying secondary full-string parse"
            )

        # ── Secondary: full cleaned string JSON parse ─────────────────────────
        try:
            parsed = json.loads(cleaned)
            if "rating" in parsed:
                logger.info(
                    f"[JURY/{persona_id}] ✓ Parse path: SECONDARY (full-string JSON) — "
                    f"rating={parsed.get('rating')}, confidence={parsed.get('confidence')}"
                )
                return parsed
        except (json.JSONDecodeError, TypeError):
            logger.debug(
                f"[JURY/{persona_id}] Secondary full-string JSON parse failed — "
                f"falling back to plain-text field extraction"
            )

        # ── Last resort: regex field extraction from plain text ───────────────
        logger.warning(
            f"[JURY/{persona_id}] ⚠ Parse path: LAST-RESORT (regex plain-text extraction) — "
            f"both JSON parse paths failed"
        )
        rating = "Hold"
        for candidate in [
            "Strong Buy", "Strong Sell",
            "Accumulate", "Distribute",
            "Low Risk", "Medium Risk", "High Risk",
            "Buy", "Sell", "Hold",
        ]:
            if candidate.lower() in cleaned.lower():
                rating = candidate
                break

        conf_match = re.search(r"(\d{1,3})\s*%", cleaned)
        confidence = int(conf_match.group(1)) if conf_match else 60
        note       = re.sub(r"\{.*?\}", "", cleaned, flags=re.DOTALL).strip()[:420]

        result = {
            "rating":     rating,
            "note":       note,
            "confidence": min(max(confidence, 10), 95),
        }
        logger.info(
            f"[JURY/{persona_id}] Last-resort result — "
            f"rating={result['rating']}, confidence={result['confidence']}"
        )
        return result

    # ------------------------------------------------------------------
    # Public: dispatch one persona and return a structured verdict
    # ------------------------------------------------------------------

    async def get_analyst_verdict(self, persona: dict, market_ctx: str) -> dict:
        """
        Dispatches a single analyst persona to its assigned provider and model.
        All 3 personas use Groq. Provider field reserved for future expansion.
        Returns a fully structured verdict dict ready for the API response.
        """
        user_prompt = market_ctx + NOTE_PROMPT_SUFFIX
        model_used  = persona["api_model"]
        max_tok     = persona.get("max_tokens", 320)
        raw         = ""

        logger.info(
            f"[JURY/{persona['id']}] ── Dispatching — "
            f"provider={persona['provider']}, model={model_used}, "
            f"max_tokens={max_tok}, title='{persona['title']}' ──"
        )
        logger.info(
            f"[JURY/{persona['id']}] Context sent — "
            f"market_ctx_chars={len(market_ctx)}, total_prompt_chars={len(user_prompt)}"
        )

        try:
            if persona["provider"] == "groq":
                raw = await self._call_groq(model_used, persona["system"], user_prompt, max_tok)
            else:
                raise ValueError(f"Unknown provider: {persona['provider']}")

            logger.info(
                f"[JURY/{persona['id']}] ✓ Raw response received — "
                f"model={model_used}, raw_chars={len(raw)}"
            )

        except Exception as e:
            logger.error(
                f"[JURY/{persona['id']}] ✗ FAILED — model={model_used}, error={e} | "
                f"FALLBACK: returning Hold/25 default verdict"
            )
            raw = (
                '{"rating": "Hold", '
                '"note": "Model unavailable — no verdict at this time.", '
                '"confidence": 25}'
            )
            model_used = "error"

        parsed = self._parse_analyst_response(raw, persona_id=persona["id"])

        verdict = {
            "id":          persona["id"],
            "avatar":      persona["avatar"],
            "title":       persona["title"],
            "model_label": persona["model_label"],
            "color":       persona["color"],
            "rating":      parsed.get("rating",     "Hold"),
            "note":        parsed.get("note",        "No available analysis at this time."),
            "confidence":  parsed.get("confidence",  50),
            "model":       model_used,
        }
        logger.info(
            f"[JURY/{persona['id']}] Final verdict — "
            f"rating={verdict['rating']}, confidence={verdict['confidence']}%, "
            f"model={verdict['model']}, note_chars={len(verdict['note'])}"
        )
        return verdict
