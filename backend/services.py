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
        points = []
        for ts, row in df.iterrows():
            # Ensure timezone-aware
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
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
                    "open":   float(row.get("open",  row.get("close", 0))),
                    "high":   float(row.get("high",  row.get("close", 0))),
                    "low":    float(row.get("low",   row.get("close", 0))),
                    "close":  float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)),
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
        except Exception:
            pass
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
            df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
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

        # 4. Reindex to business-day frequency and forward-fill gaps
        #    (covers market holidays, weekends already excluded by yfinance)
        full_idx = pd.bdate_range(start=df.index.min(), end=df.index.max(), freq="B")
        full_idx = full_idx.tz_localize("UTC") if full_idx.tz is None else full_idx
        df = df.reindex(full_idx).ffill()

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
        async with httpx.AsyncClient(timeout=25.0) as client:
            params = {
                "engine":  "google_finance",
                "q":       query,
                "api_key": Config.SERP_API_KEY,
            }
            resp = await client.get("https://serpapi.com/search.json", params=params)
            return resp.json() if resp.status_code == 200 else {}
