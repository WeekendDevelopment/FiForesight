# backend/services.py
import re
import logging
import httpx
import pandas as pd
from datetime import datetime, timezone

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    yf = None  # type: ignore
    YFINANCE_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "yfinance not installed — run: pip install yfinance"
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
        self.client = InfluxDBClient(
            url=Config.INFLUXDB_URL,
            token=Config.INFLUXDB_TOKEN,
            org=Config.INFLUXDB_ORG,
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()

    # --- Write a single live close price (used for intraday snapshots) ------
    def write_price(self, symbol: str, price: float):
        try:
            p = (
                Point("market_data")
                .tag("symbol", symbol)
                .field("close", float(price))
                .time(datetime.now(timezone.utc), WritePrecision.NS)
            )
            self.write_api.write(bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p)
        except Exception as e:
            logger.error(f"InfluxDB write_price error: {e}")

    # --- Write a full OHLCV batch (from yfinance) ---------------------------
    def write_ohlcv_batch(self, symbol: str, df: pd.DataFrame):
        """
        df must have a DatetimeIndex (UTC) and columns:
        Open, High, Low, Close, Volume
        """
        from datetime import timedelta
        # InfluxDB Cloud has a 30-day retention policy — skip older rows to avoid 400 errors
        cutoff = datetime.now(timezone.utc) - timedelta(days=29)

        points = []
        for ts, row in df.iterrows():
            # Ensure timezone-aware
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            if ts < cutoff:
                continue  # outside retention window — don't attempt to write
            p = (
                Point("market_data")
                .tag("symbol", symbol)
                .field("open",   float(row.get("Open",  row.get("open",  0))))
                .field("high",   float(row.get("High",  row.get("high",  0))))
                .field("low",    float(row.get("Low",   row.get("low",   0))))
                .field("close",  float(row.get("Close", row.get("close", 0))))
                .field("volume", float(row.get("Volume", row.get("volume", 0))))
                .time(ts, WritePrecision.NS)
            )
            points.append(p)
        try:
            self.write_api.write(
                bucket=Config.INFLUXDB_BUCKET,
                org=Config.INFLUXDB_ORG,
                record=points,
            )
            logger.info(f"InfluxDB: wrote {len(points)} OHLCV rows for {symbol}")
        except Exception as e:
            logger.error(f"InfluxDB write_ohlcv_batch error: {e}")

    # --- Query stored OHLCV history -----------------------------------------
    def query_history(self, symbol: str, days: int = 365) -> list:
        """
        Returns list of dicts with keys: _time, open, high, low, close, volume
        """
        query = f"""
        from(bucket: "{Config.INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r["_measurement"] == "market_data" and r["symbol"] == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> sort(columns: ["_time"], desc: false)
        """
        try:
            tables = self.query_api.query(query)
            rows = [r.values for t in tables for r in t.records]
            # Normalise field names to lowercase
            out = []
            for row in rows:
                out.append({
                    "_time":  row.get("_time"),
                    "open":   float(row.get("open",  row.get("close", 0)) or 0),
                    "high":   float(row.get("high",  row.get("close", 0)) or 0),
                    "low":    float(row.get("low",   row.get("close", 0)) or 0),
                    "close":  float(row.get("close", 0) or 0),
                    "volume": float(row.get("volume", 0) or 0),
                })
            return out
        except Exception as e:
            logger.error(f"InfluxDB query_history error: {e}")
            return []

    def has_recent_data(self, symbol: str, within_hours: int = 20) -> bool:
        """Return True if we already have fresh data for today (avoid re-fetching)."""
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
                    return (r.get_value() or 0) > 0
        except Exception as e:
            logger.error(f"InfluxDB has_recent_data error: {e}")
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
        return symbol.split(":")[0].upper()

    def fetch_history(self, symbol: str, period: str = "2y") -> pd.DataFrame:
        """
        Fetch daily OHLCV for `period` (e.g. '2y', '1y', '6mo').
        Returns a DataFrame with DatetimeIndex (UTC) and columns:
        Open, High, Low, Close, Volume.
        Returns empty DataFrame on failure.
        """
        if not YFINANCE_AVAILABLE:
            logger.error("yfinance not installed — cannot fetch history")
            return pd.DataFrame()
        ticker = self._to_yf_symbol(symbol)
        try:
            # yfinance now uses curl_cffi internally for Yahoo's bot detection —
            # passing a requests.Session raises an error in recent versions.
            df = yf.download(
                ticker, period=period, interval="1d",
                progress=False, auto_adjust=True,
                timeout=20,
            )
            if df.empty:
                logger.warning(f"yfinance: no history for {ticker}")
                return pd.DataFrame()

            # Flatten MultiIndex columns if present (yfinance ≥0.2 quirk)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df.index = pd.to_datetime(df.index)
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")

            # Keep only the columns we care about
            keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[keep].dropna(subset=["Close"])

            logger.info(f"yfinance: fetched {len(df)} rows for {ticker}")
            return df
        except Exception as e:
            logger.error(f"yfinance fetch_history error ({ticker}): {e}")
            return pd.DataFrame()

    def fetch_info(self, symbol: str) -> dict:
        """
        Returns a dict of fundamentals:
        market_cap, pe_ratio, dividend_yield, prev_close, range_52w, current_price
        """
        if not YFINANCE_AVAILABLE:
            return {}
        ticker = self._to_yf_symbol(symbol)
        try:
            info = yf.Ticker(ticker).info
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
            high52 = info.get("fiftyTwoWeekHigh")
            low52  = info.get("fiftyTwoWeekLow")
            range_52w = (
                f"{low52:.2f} - {high52:.2f}"
                if high52 and low52 else "N/A"
            )
            current = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
                or 0.0
            )
            return {
                "current_price":    float(current),
                "market_cap":       info.get("marketCap",       "N/A"),
                "pe_ratio":         info.get("trailingPE",      "N/A"),
                "dividend_yield":   info.get("dividendYield",   "N/A"),
                "prev_close":       prev_close or "N/A",
                "range_52w":        range_52w,
                "short_name":       info.get("shortName",       ticker),
                "sector":           info.get("sector",          "N/A"),
                "currency":         info.get("currency",        "USD"),
            }
        except Exception as e:
            logger.error(f"yfinance fetch_info error ({ticker}): {e}")
            return {}

    def get_live_price(self, symbol: str) -> float:
        """Fast path to get the latest price from yfinance."""
        if not YFINANCE_AVAILABLE:
            return 0.0
        ticker = self._to_yf_symbol(symbol)
        try:
            t = yf.Ticker(ticker)
            price = (
                t.info.get("currentPrice")
                or t.info.get("regularMarketPrice")
                or t.info.get("previousClose")
                or 0.0
            )
            return float(price)
        except Exception as e:
            logger.error(f"yfinance get_live_price error ({ticker}): {e}")
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
            return df

        df = df.copy()

        # 1. Sort by time
        df.sort_index(inplace=True)

        # 2. Drop rows where Close is zero or NaN
        df = df[df["Close"].notna() & (df["Close"] > 0)]
        if df.empty:
            return df

        # 3. Remove outliers: flag Close values more than 4 std-devs from rolling
        #    30-day median (handles bad ticks / splits not adjusted)
        rolling_med = df["Close"].rolling(30, min_periods=5, center=True).median()
        rolling_std = df["Close"].rolling(30, min_periods=5, center=True).std()
        upper = rolling_med + 4 * rolling_std
        lower = rolling_med - 4 * rolling_std
        mask = (df["Close"] >= lower) & (df["Close"] <= upper)
        removed = (~mask).sum()
        if removed:
            logger.info(f"DataCleaner: removed {removed} outlier rows")
        df = df[mask]
        if df.empty:
            return df   # guard: avoids NaT bdate_range crash below

        # 4. Reindex to business-day frequency and forward-fill gaps
        #    (covers market holidays, weekends already excluded by yfinance)
        try:
            full_idx = pd.bdate_range(start=df.index.min(), end=df.index.max(), freq="B")
            full_idx = full_idx.tz_localize("UTC") if full_idx.tz is None else full_idx
            df = df.reindex(full_idx).ffill()
        except Exception as e:
            logger.warning(f"DataCleaner: bdate_range reindex failed ({e}), skipping gap-fill")

        if df.empty:
            return df

        # 5. Ensure High >= Close >= Low (yfinance adjusted data can drift)
        if "High" in df.columns and "Low" in df.columns:
            df["High"] = df[["High", "Close"]].max(axis=1)
            df["Low"]  = df[["Low",  "Close"]].min(axis=1)

        return df

    @staticmethod
    def to_history_list(df: pd.DataFrame) -> list:
        """Convert cleaned DataFrame → list of dicts used by main.py and models."""
        out = []
        for ts, row in df.iterrows():
            out.append({
                "_time":  ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                "open":   float(row.get("Open",  row.get("Close", 0))),
                "high":   float(row.get("High",  row.get("Close", 0))),
                "low":    float(row.get("Low",   row.get("Close", 0))),
                "close":  float(row.get("Close", 0)),
                "volume": float(row.get("Volume", 0)),
            })
        return out


# ---------------------------------------------------------------------------
# SerpAPI Service  —  live price, news, trending tickers
# ---------------------------------------------------------------------------

class SerpService:
    @staticmethod
    def clean_price(price_str):
        if price_str is None:
            return 0.0
        if isinstance(price_str, (int, float)):
            return float(price_str)
        cleaned = re.sub(r'[^\d.-]', '', str(price_str))
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
            logger.warning("SerpAPI key not set — skipping news/trending fetch")
            return {"news_results": [], "markets": {}}

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
                return {
                    "news_results": data.get("news_results", []),
                    "markets":      data.get("markets", {}),
                }
        except Exception as e:
            logger.error(f"SerpAPI fetch_data error: {e}")
            return {"news_results": [], "markets": {}}


# ---------------------------------------------------------------------------
# Groq Service  —  multi-analyst jury via free-tier Groq API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Analyst Jury  —  3 personas, each pinned to a different model
#
#   LLAMA-70B   → Groq llama-3.3-70b-versatile   (1,000 RPD free)  — Growth lens
#   LLAMA-8B    → Groq llama-3.1-8b-instant       (14,400 RPD free) — Risk lens
#   GEMINI-FLASH→ Google Gemini 2.5 Flash          (1,000 RPD free)  — Quant lens
#                 (Gemini call handled in main.py using the existing ai_client)
# ---------------------------------------------------------------------------

ANALYST_PERSONAS = [
    {
        "id":       "LLAMA-70B",
        "avatar":   "70B",
        "title":    "Growth Lens",
        "model_label": "Groq · llama-3.3-70b",
        "provider": "groq",
        "groq_model": "llama-3.3-70b-versatile",
        "color":    "#00f2ff",
        "system": (
            "You are LLAMA-70B, a growth-focused equity analyst running on Llama 3.3 70B. "
            "Your lens is momentum, catalysts, and upside potential. "
            "Analyse the provided market data and deliver a substantive advisory opinion: "
            "comment on price momentum relative to SMA, RSI strength, what the forecast range implies, "
            "any notable volatility context, and your overall growth outlook. "
            "Reference MACD momentum, SMA50/200 positioning, volume trend, forecast confidence, and any fundamental tailwinds. "
            "Be specific, actionable, and advisory — not generic. Conclude with a clear rating."
        ),
    },
    {
        "id":       "LLAMA-8B",
        "avatar":   "8B",
        "title":    "Risk Lens",
        "model_label": "Groq · llama-3.1-8b",
        "provider": "groq",
        "groq_model": "llama-3.1-8b-instant",
        "color":    "#bc13fe",
        "system": (
            "You are LLAMA-8B, a risk and macro analyst running on Llama 3.1 8B. "
            "Your lens is downside scenarios, warning signals, and risk-adjusted positioning. "
            "Analyse the provided market data and deliver a substantive advisory opinion: "
            "flag any RSI extremes, negative trend slope, elevated volatility, or concerning forecast skew. "
            "Discuss what could go wrong and how severe the downside looks. "
            "Examine BB band squeeze/expansion, proximity to support/resistance, whether volume confirms or contradicts the move, and any fundamental red flags. "
            "Be specific, actionable, and advisory — not generic. Conclude with a clear rating."
        ),
    },
    {
        "id":       "GEMINI-FLASH",
        "avatar":   "GF",
        "title":    "Quant Lens",
        "model_label": "Google · Gemini 2.5 Flash",
        "provider": "gemini",
        "color":    "#f59e0b",
        "system": (
            "You are GEMINI-FLASH, a quantitative strategist running on Google Gemini 2.5 Flash. "
            "You operate purely on statistical signals — no fundamental or macro bias. "
            "Analyse the provided market data and deliver a substantive advisory opinion: "
            "interpret RSI level and regime, trend slope direction and magnitude, "
            "price position relative to SMA20, forecast confidence, and annualised volatility. "
            "Cover MACD histogram crossover state, Bollinger Band width, SMA50/200 crossover proximity, and volume confirmation of the trend. Cite the forecast confidence label explicitly. "
            "Map each signal to a clear implication. Be precise, data-first, and advisory. "
            "Conclude with a clear rating."
        ),
    },
]

NOTE_PROMPT_SUFFIX = (
    "\n\nRespond ONLY with valid JSON in exactly this format (no extra text):\n"
    '{"rating": "<Strong Buy|Buy|Hold|Sell|Strong Sell>", '
    '"note": "<3-4 advisory sentences, up to 420 chars, with specific signals and implications>", '
    '"confidence": <integer 10-95>}'
)


class GroqService:
    """
    Calls Groq's free-tier API (OpenAI-compatible).
    Each persona is pinned to a specific Groq model; no automatic fallback
    between models so each analyst genuinely reflects its own model's view.
    Gemini persona is handled by the caller (main.py) using the existing ai_client.
    """
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    async def _call_groq(self, model: str, system: str, user: str) -> str:
        """Raw Groq API call. Raises on non-2xx or missing key."""
        if not Config.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured")
        headers = {
            "Authorization": f"Bearer {Config.GROQ_API_KEY}",
            "Content-Type":  "application/json",
        }
        body = {
            "model":       model,
            "messages":    [{"role": "system", "content": system},
                            {"role": "user",   "content": user}],
            "max_tokens":  320,
            "temperature": 0.65,
        }
        async with httpx.AsyncClient(timeout=22.0) as client:
            resp = await client.post(self.BASE_URL, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _parse_analyst_response(raw: str) -> dict:
        """
        Extract structured fields from model output.
        Expected JSON: {"rating": "Buy", "note": "...", "confidence": 72}
        Falls back to regex extraction on malformed output.
        """
        import json, re
        json_match = re.search(r'\{[^{}]*"rating"[^{}]*\}', raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except Exception:
                pass
        rating = "Hold"
        for candidate in ["Strong Buy", "Strong Sell", "Buy", "Sell", "Hold"]:
            if candidate.lower() in raw.lower():
                rating = candidate
                break
        conf_match = re.search(r'(\d{1,3})\s*%', raw)
        confidence = int(conf_match.group(1)) if conf_match else 60
        note = re.sub(r'\{.*?\}', '', raw, flags=re.DOTALL).strip()[:420]
        return {"rating": rating, "note": note, "confidence": min(max(confidence, 10), 95)}

    async def get_analyst_verdict(self, persona: dict, market_ctx: str) -> dict:
        """
        Run one Groq-backed analyst persona and return structured verdict.
        Uses the model pinned to this persona (no cross-model fallback).
        """
        user_prompt = market_ctx + NOTE_PROMPT_SUFFIX
        model_used  = persona["groq_model"]
        raw = ""
        try:
            raw = await self._call_groq(model_used, persona["system"], user_prompt)
        except Exception as e:
            logger.error(f"GroqService [{persona['id']}] failed: {e}")
            raw = '{"rating": "Hold", "note": "Model unavailable — no verdict at this time.", "confidence": 25}'
            model_used = "error"

        parsed = self._parse_analyst_response(raw)
        return {
            "id":          persona["id"],
            "avatar":      persona["avatar"],
            "title":       persona["title"],
            "model_label": persona["model_label"],
            "color":       persona["color"],
            "rating":      parsed.get("rating",     "Hold"),
            "note":        parsed.get("note",       ""),
            "confidence":  parsed.get("confidence", 50),
            "model":       model_used,
        }
