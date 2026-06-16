# backend/services.py
import re
import json
import math
import logging
import asyncio
import httpx
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import newrelic.agent

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
# Input validation — prevents Flux/InfluxQL injection via user-supplied tags
# ---------------------------------------------------------------------------

_SAFE_TAG_RE  = re.compile(r"^[A-Za-z0-9._:\-]+$")
_VALID_SIM_ENV      = frozenset({"local", "preview", "live"})
_VALID_SIM_ENV_READ = frozenset({"local", "preview", "live", "all"})
_UUID_RE       = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _validate_tag(value: str, field: str = "tag") -> str:
    """
    Strict validation for values that are interpolated into Flux queries.
    Rejects any character outside [A-Za-z0-9._:-] to prevent query injection
    (e.g. a symbol like `AAPL" or r._field == "`).
    """
    if not isinstance(value, str) or not _SAFE_TAG_RE.match(value):
        raise ValueError(f"Invalid {field}: {value!r}")
    if len(value) > 32:
        raise ValueError(f"{field} too long: {value!r}")
    return value


_ALLOWED_MODELS = frozenset({
    "prophet", "sarima", "rf",
    # per-horizon ensemble accuracy trackers (d1 reuses same slot as per-model)
    "ensemble_d1", "ensemble_d2", "ensemble_d3", "ensemble_d4", "ensemble_d5",
})


def _validate_model(model: str) -> str:
    if model not in _ALLOWED_MODELS:
        raise ValueError(f"Invalid model: {model!r}")
    return model


# ---------------------------------------------------------------------------
# InfluxDB Service  —  stores and retrieves full OHLCV data
# ---------------------------------------------------------------------------

class InfluxService:
    def __init__(self):
        logger.debug(
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
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[INFLUXDB] write_price rejected — {e}")
            return
        logger.debug(f"[INFLUXDB] write_price — symbol={symbol}, price=${price:.2f}")
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

    # --- Persist a VADER sentiment score (time-series) -----------------------
    def write_sentiment_score(self, symbol: str, compound: float, label: str):
        """Append one sentiment data point for `symbol` to the sentiment_score
        measurement (tags: symbol, env; fields: compound, label).

        Called fire-and-forget from /predict so the 30-day sentiment trend on the
        Insights tab accumulates over time. Any failure is logged, never raised.
        """
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[INFLUXDB] write_sentiment_score rejected — {e}")
            return
        env = Config.APP_ENV if isinstance(Config.APP_ENV, str) and Config.APP_ENV else "local"
        try:
            p = (
                Point("sentiment_score")
                .tag("symbol", symbol)
                .tag("env", env)
                .field("compound", float(compound))
                .field("label", str(label))
                .time(datetime.now(timezone.utc), WritePrecision.NS)
            )
            self.write_api.write(
                bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p
            )
            logger.info(
                f"[INFLUXDB] ✓ write_sentiment_score — {symbol} compound={compound:+.4f} ({label})"
            )
        except Exception as e:
            logger.error(f"[INFLUXDB] ✗ write_sentiment_score error for {symbol}: {e}")

    # --- Query stored sentiment history (for the Insights trend chart) -------
    def query_sentiment_history(self, symbol: str, days: int = 30) -> list:
        """Return [{date, compound, label}, ...] ascending by time for the last
        N days. Empty list when no data or on any error (caller shows empty state)."""
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[INFLUXDB] query_sentiment_history rejected — {e}")
            return []
        days = max(1, int(days))
        query = f"""
        from(bucket: "{Config.INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r["_measurement"] == "sentiment_score" and r["symbol"] == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> sort(columns: ["_time"], desc: false)
        """
        try:
            tables = self.query_api.query(query)
            out: list = []
            for t in tables:
                for r in t.records:
                    tv = r.values.get("_time")
                    if tv is None:
                        continue
                    out.append({
                        "date":     tv.date().isoformat(),
                        "compound": round(float(r.values.get("compound", 0.0) or 0.0), 4),
                        "label":    str(r.values.get("label", "Neutral")),
                    })
            logger.info(
                f"[INFLUXDB] query_sentiment_history — {symbol}: {len(out)} points in last {days}d"
            )
            return out
        except Exception as e:
            logger.error(f"[INFLUXDB] ✗ query_sentiment_history error for {symbol}: {e}")
            return []

    # --- Persist a market-regime label (time-series, Feature 16) -------------
    def write_market_regime(self, symbol: str, regime: str, confidence: float) -> None:
        """Append one regime data point for `symbol` to the market_regime
        measurement (tags: symbol, env; fields: regime, confidence).

        Called fire-and-forget from /predict so a future regime-timeline chart
        on the Insights tab can accumulate over time. Any failure is logged,
        never raised.
        """
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[INFLUXDB] write_market_regime rejected — {e}")
            return
        env = Config.APP_ENV if isinstance(Config.APP_ENV, str) and Config.APP_ENV else "local"
        try:
            p = (
                Point("market_regime")
                .tag("symbol", symbol)
                .tag("env", env)
                .field("regime", str(regime))
                .field("confidence", float(confidence))
                .time(datetime.now(timezone.utc), WritePrecision.NS)
            )
            self.write_api.write(
                bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p
            )
            logger.info(
                f"[INFLUXDB] ✓ write_market_regime — {symbol} {regime} (conf={confidence:.2f})"
            )
        except Exception as e:
            logger.error(f"[INFLUXDB] ✗ write_market_regime error for {symbol}: {e}")

    # --- Write a full OHLCV batch (from yfinance) ----------------------------
    def write_ohlcv_batch(self, symbol: str, df: pd.DataFrame):
        """
        df must have a DatetimeIndex (UTC) and columns: Open, High, Low, Close, Volume.
        InfluxDB Cloud has a 30-day retention policy — rows older than 29 days are skipped.
        """
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[INFLUXDB] write_ohlcv_batch rejected — {e}")
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=29)

        logger.debug(
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

        logger.debug(
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
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[INFLUXDB] query_history rejected — {e}")
            return []
        days = max(1, int(days))
        logger.debug(
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
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[INFLUXDB] has_recent_data rejected — {e}")
            return False
        within_hours = max(1, int(within_hours))
        logger.debug(
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

    # ── Simulation state persistence ─────────────────────────────────────────
    # Each simulation is stored as a separate time-series (env + sim_id tags).
    # Soft-delete: write an empty-string tombstone so `last()` filters it out.
    # One InfluxDB point per save/delete — negligible storage footprint.

    @staticmethod
    def _validate_sim_env(env: str) -> str:
        if env not in _VALID_SIM_ENV:
            raise ValueError(f"Invalid simulation env: {env!r}")
        return env

    @staticmethod
    def _validate_sim_env_read(env: str) -> str:
        """Like _validate_sim_env but also accepts 'all' for cross-env reads."""
        if env not in _VALID_SIM_ENV_READ:
            raise ValueError(f"Invalid simulation env for read: {env!r}")
        return env

    @staticmethod
    def _validate_sim_id(sim_id: str) -> str:
        if not _UUID_RE.match(sim_id.lower()):
            raise ValueError(f"sim_id must be a UUID v4, got: {sim_id!r}")
        return sim_id.lower()

    @staticmethod
    def _validate_user_id(user_id: str) -> str:
        """Accepts empty string (anonymous) or a Supabase UUID."""
        if not user_id:
            return ""
        if not _UUID_RE.match(user_id.lower()):
            raise ValueError(f"user_id must be a UUID v4, got: {user_id!r}")
        return user_id.lower()

    def write_simulation_state(self, sim_id: str, env: str, state: dict, user_id: str = "") -> bool:
        try:
            env     = self._validate_sim_env(env)
            sim_id  = self._validate_sim_id(sim_id)
            user_id = self._validate_user_id(user_id)
            point   = (
                Point("simulation_state")
                .tag("env",    env)
                .tag("sim_id", sim_id)
                .field("state_json", json.dumps(state))
            )
            if user_id:
                point = point.tag("user_id", user_id)
            self.write_api.write(
                bucket=Config.INFLUXDB_BUCKET,
                org=Config.INFLUXDB_ORG,
                record=point,
            )
            logger.info("[INFLUXDB] simulation_state saved: sim_id=%s env=%s user=%s", sim_id, env, "authenticated" if user_id else "anon")
            return True
        except Exception as exc:
            logger.error("[INFLUXDB] write_simulation_state failed: %s", exc)
            return False

    def query_simulation_states(self, env: str, user_id: str = "") -> List[dict]:
        """Return live (non-deleted) simulations for the given env, optionally filtered by user."""
        try:
            if env not in _VALID_SIM_ENV_READ:
                raise ValueError(f"Invalid simulation env: {env!r}")
            user_id = self._validate_user_id(user_id)
            env_filter  = "" if env == "all" else f'  |> filter(fn: (r) => r.env == "{env}")\n'
            # Authenticated: exact-match on user_id tag.
            # Anonymous: restrict to legacy rows that have no user_id tag at all.
            if user_id:
                user_filter = f'  |> filter(fn: (r) => r.user_id == "{user_id}")\n'
            else:
                user_filter = '  |> filter(fn: (r) => not exists r.user_id)\n'
            query = f"""
from(bucket: "{Config.INFLUXDB_BUCKET}")
  |> range(start: -365d)
  |> filter(fn: (r) => r._measurement == "simulation_state")
{env_filter}{user_filter}  |> filter(fn: (r) => r._field == "state_json")
  |> last()
  |> filter(fn: (r) => r._value != "")
  |> sort(columns: ["_time"], desc: true)
"""
            tables = self.query_api.query(query, org=Config.INFLUXDB_ORG)
            results: List[dict] = []
            for table in tables:
                for record in table.records:
                    try:
                        state = json.loads(record.get_value())
                        if "env" not in state:
                            state["env"] = record.values.get("env", env)
                        results.append(state)
                    except Exception as exc:
                        logger.debug(
                            "[INFLUXDB] skipping unparseable simulation_state record: %s",
                            exc,
                        )
            return results
        except Exception as exc:
            logger.error("[INFLUXDB] query_simulation_states failed: %s", exc)
            return []

    def delete_simulation_state(self, sim_id: str, env: str, user_id: str = "") -> bool:
        """Soft-delete: write an empty-string tombstone so `last()` filters it out."""
        try:
            env     = self._validate_sim_env(env)
            sim_id  = self._validate_sim_id(sim_id)
            user_id = self._validate_user_id(user_id)
            point   = (
                Point("simulation_state")
                .tag("env",    env)
                .tag("sim_id", sim_id)
                .field("state_json", "")
            )
            if user_id:
                point = point.tag("user_id", user_id)
            self.write_api.write(
                bucket=Config.INFLUXDB_BUCKET,
                org=Config.INFLUXDB_ORG,
                record=point,
            )
            logger.info("[INFLUXDB] simulation_state deleted: sim_id=%s env=%s user=%s", sim_id, env, "authenticated" if user_id else "anon")
            return True
        except Exception as exc:
            logger.error("[INFLUXDB] delete_simulation_state failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# ForecastStore  —  RL feedback loop: record forecasts, resolve outcomes,
#                   maintain per-model accuracy for calibrated weight blending
# ---------------------------------------------------------------------------

class ForecastStore:
    """
    Three InfluxDB measurements:
      forecast_record  — per-model day-1 preds + ensemble preds + weights
      price_outcome    — actual market closes (written at resolution time)
      model_accuracy   — running day-1 MAE per model (prophet / sarima / rf)

    On every /predict request:
      1. write_forecast_record  — records what was predicted
      2. resolve_past_forecasts (background) — matches old forecasts against
         actual closes, updates model_accuracy
      3. query_model_accuracy  — returns historical MAE used to blend weights
    """

    def __init__(self, influx_service: "InfluxService"):
        self._svc = influx_service

    # ── Writes ────────────────────────────────────────────────────────────────

    def write_forecast_record(
        self,
        symbol: str,
        last_price: float,
        prophet_d1: Optional[float],
        sarima_d1: Optional[float],
        rf_d1: Optional[float],
        w_prophet: float,
        w_sarima: float,
        w_rf: float,
        ensemble_preds: List[float],  # 5-element list (one per forecast day)
        d1_high: Optional[float] = None,
        d1_low: Optional[float] = None,
    ) -> None:
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[RL] write_forecast_record rejected — {e}")
            return
        p_str = f"{prophet_d1:.2f}" if prophet_d1 is not None else "N/A"
        s_str = f"{sarima_d1:.2f}"  if sarima_d1  is not None else "N/A"
        r_str = f"{rf_d1:.2f}"      if rf_d1       is not None else "N/A"
        try:
            logger.debug(
                f"[RL] write_forecast_record — {symbol} @ last_price=${last_price:.2f} | "
                f"p_d1={p_str}, s_d1={s_str}, r_d1={r_str} | "
                f"w=[{w_prophet:.3f},{w_sarima:.3f},{w_rf:.3f}]"
            )
            p = (
                Point("forecast_record")
                .tag("symbol", symbol)
                .field("last_price", float(last_price))
                .field("p_d1", float(prophet_d1) if prophet_d1 is not None else -1.0)
                .field("s_d1", float(sarima_d1)  if sarima_d1  is not None else -1.0)
                .field("r_d1", float(rf_d1)       if rf_d1       is not None else -1.0)
                .field("w_p",  float(w_prophet))
                .field("w_s",  float(w_sarima))
                .field("w_r",  float(w_rf))
            )
            for i, pred in enumerate(ensemble_preds[:5], 1):
                p = p.field(f"e_d{i}", float(pred))
            if d1_high is not None:
                p = p.field("e_d1_high", float(d1_high))
            if d1_low is not None:
                p = p.field("e_d1_low", float(d1_low))
            p = p.time(datetime.now(timezone.utc), WritePrecision.NS)
            self._svc.write_api.write(
                bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p
            )
            logger.info(f"[RL] ✓ forecast_record written for {symbol}")
        except Exception as e:
            logger.error(f"[RL] ✗ write_forecast_record error for {symbol}: {e}")

    def write_price_outcome(
        self, symbol: str, outcome_dt: datetime, actual_close: float
    ) -> None:
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[RL] write_price_outcome rejected — {e}")
            return
        try:
            p = (
                Point("price_outcome")
                .tag("symbol", symbol)
                .field("actual_close", float(actual_close))
                .time(outcome_dt, WritePrecision.NS)
            )
            self._svc.write_api.write(
                bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p
            )
            logger.info(
                f"[RL] ✓ price_outcome written — {symbol} {outcome_dt.date()} = ${actual_close:.2f}"
            )
        except Exception as e:
            logger.error(f"[RL] ✗ write_price_outcome error for {symbol}: {e}")

    def mark_forecast_resolved(
        self, symbol: str, record_time: datetime, horizon: int = 1
    ) -> None:
        """
        Write a resolution marker for a given forecast_record.
        `horizon` is the highest ensemble day resolved so far (1–5).
        Writing the same timestamp overwrites the previous value in InfluxDB,
        so the stored value always reflects the max horizon resolved.
        """
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[RL] mark_forecast_resolved rejected — {e}")
            return
        try:
            p = (
                Point("forecast_resolution")
                .tag("symbol", symbol)
                .field("resolved", int(horizon))
                .time(record_time, WritePrecision.NS)
            )
            self._svc.write_api.write(
                bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p
            )
        except Exception as e:
            logger.error(f"[RL] ✗ mark_forecast_resolved error for {symbol}: {e}")

    def query_resolved_timestamps(
        self, symbol: str, days: int = 30
    ) -> Dict[object, int]:
        """
        Return {forecast_record_time: max_horizon_resolved} for all resolved records.
        horizon=1 means d1 done, horizon=5 means fully resolved.
        Old records written with resolved=1 (boolean) continue to work correctly.
        """
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[RL] query_resolved_timestamps rejected — {e}")
            return {}
        days = max(1, int(days))
        query = f"""
        from(bucket: "{Config.INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r["_measurement"] == "forecast_resolution" and r["symbol"] == "{symbol}")
          |> keep(columns: ["_time", "_value"])
        """
        try:
            tables = self._svc.query_api.query(query)
            out: Dict[object, int] = {}
            for t in tables:
                for r in t.records:
                    tv  = r.values.get("_time")
                    val = r.values.get("_value", 0) or 0
                    if tv is not None:
                        out[tv] = max(out.get(tv, 0), int(val))
            return out
        except Exception as e:
            logger.error(f"[RL] ✗ query_resolved_timestamps error for {symbol}: {e}")
            return {}

    def write_model_accuracy(
        self, symbol: str, model: str, mae: float, sample_count: int
    ) -> bool:
        """Write updated EMA-MAE stats for one model/horizon key.

        Returns True on success, False on any validation or InfluxDB failure
        so callers can gate downstream operations (e.g. mark_forecast_resolved)
        on confirmed writes.
        """
        try:
            _validate_tag(symbol, "symbol")
            _validate_model(model)
        except ValueError as e:
            logger.error(f"[RL] write_model_accuracy rejected — {e}")
            return False
        try:
            p = (
                Point("model_accuracy")
                .tag("symbol", symbol)
                .tag("model", model)
                .field("mae_d1", float(mae))
                .field("sample_count", int(sample_count))
                .time(datetime.now(timezone.utc), WritePrecision.NS)
            )
            self._svc.write_api.write(
                bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p
            )
            logger.info(
                f"[RL] ✓ model_accuracy updated — {symbol}/{model}: MAE=${mae:.3f}, n={sample_count}"
            )
            return True
        except Exception as e:
            logger.error(f"[RL] ✗ write_model_accuracy error for {symbol}/{model}: {e}")
            return False

    # ── Queries ───────────────────────────────────────────────────────────────

    def query_forecast_records(self, symbol: str, days: int = 10) -> List[dict]:
        """Returns forecast record rows from the last N days."""
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[RL] query_forecast_records rejected — {e}")
            return []
        days = max(1, int(days))
        query = f"""
        from(bucket: "{Config.INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r["_measurement"] == "forecast_record" and r["symbol"] == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> sort(columns: ["_time"], desc: false)
        """
        try:
            tables = self._svc.query_api.query(query)
            rows = [r.values for t in tables for r in t.records]
            logger.info(
                f"[RL] query_forecast_records — {symbol}: {len(rows)} records in last {days}d"
            )
            return rows
        except Exception as e:
            logger.error(f"[RL] ✗ query_forecast_records error for {symbol}: {e}")
            return []

    def query_price_outcomes(self, symbol: str, days: int = 15) -> Dict[object, float]:
        """Returns {date: actual_close} from price_outcome measurement."""
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[RL] query_price_outcomes rejected — {e}")
            return {}
        days = max(1, int(days))
        query = f"""
        from(bucket: "{Config.INFLUXDB_BUCKET}")
          |> range(start: -{days}d)
          |> filter(fn: (r) => r["_measurement"] == "price_outcome" and r["symbol"] == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """
        try:
            tables = self._svc.query_api.query(query)
            result: Dict[object, float] = {}
            for t in tables:
                for r in t.records:
                    t_val = r.values.get("_time")
                    close = r.values.get("actual_close", 0.0)
                    if t_val is not None:
                        result[t_val.date()] = float(close)
            logger.info(
                f"[RL] query_price_outcomes — {symbol}: {len(result)} outcomes in last {days}d"
            )
            return result
        except Exception as e:
            logger.error(f"[RL] ✗ query_price_outcomes error for {symbol}: {e}")
            return {}

    def query_naive_mae(self, symbol: str, days: int = 90) -> Optional[float]:
        """
        Naive-persistence MAE: mean(|actual_close - last_price|) over matched d1
        forecast records.  Returns None when there are no matched records.
        Fails closed — any exception logs a warning and returns None.
        """
        try:
            records  = self.query_forecast_records(symbol, days=days)
            outcomes = self.query_price_outcomes(symbol, days=days + 10)
            outcomes_sorted = sorted(outcomes.items())
            errors: List[float] = []
            for rec in records:
                pred_time      = rec.get("_time")
                last_price_raw = rec.get("last_price")
                if pred_time is None or last_price_raw is None:
                    continue
                try:
                    pred_date  = pred_time.date()
                    last_price = float(last_price_raw)
                except (AttributeError, TypeError, ValueError):
                    continue
                if last_price <= 0:
                    continue
                for d, close in outcomes_sorted:
                    if d > pred_date and close > 0:
                        errors.append(abs(float(close) - last_price))
                        break
            return round(sum(errors) / len(errors), 4) if errors else None
        except Exception as exc:
            logger.warning("[RL] query_naive_mae failed for %s: %s", symbol, exc)
            return None

    def query_model_accuracy(self, symbol: str, lookback_days: int = 90) -> Dict[str, dict]:
        """
        Returns most-recent per-model accuracy record.
        { "prophet": {"mae": float, "samples": int}, "sarima": {...}, "rf": {...} }
        """
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[RL] query_model_accuracy rejected — {e}")
            return {}
        lookback_days = max(1, int(lookback_days))
        result: Dict[str, dict] = {}
        for model in ("prophet", "sarima", "rf"):
            _validate_model(model)
            query = f"""
            from(bucket: "{Config.INFLUXDB_BUCKET}")
              |> range(start: -{lookback_days}d)
              |> filter(fn: (r) =>
                  r["_measurement"] == "model_accuracy"
                  and r["symbol"] == "{symbol}"
                  and r["model"] == "{model}")
              |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> sort(columns: ["_time"], desc: true)
              |> limit(n: 1)
            """
            try:
                tables = self._svc.query_api.query(query)
                for t in tables:
                    for r in t.records:
                        vals = r.values
                        result[model] = {
                            "mae":     float(vals.get("mae_d1",      999.0)),
                            "samples": int(vals.get("sample_count", 0)),
                        }
            except Exception as e:
                logger.warning(
                    f"[RL] query_model_accuracy error for {symbol}/{model}: {e}"
                )
        logger.debug(f"[RL] query_model_accuracy — {symbol}: {result}")
        return result

    def query_ensemble_mae(self, symbol: str, lookback_days: int = 90) -> Dict[str, dict]:
        """
        Returns most-recent per-horizon ensemble accuracy.
        { "ensemble_d1": {"mae": float, "samples": int}, ..., "ensemble_d5": {...} }
        Empty dict or missing keys = no data yet for that horizon.
        """
        try:
            _validate_tag(symbol, "symbol")
        except ValueError as e:
            logger.error(f"[RL] query_ensemble_mae rejected — {e}")
            return {}
        lookback_days = max(1, int(lookback_days))
        result: Dict[str, dict] = {}
        for model in ("ensemble_d1", "ensemble_d2", "ensemble_d3", "ensemble_d4", "ensemble_d5"):
            query = f"""
            from(bucket: "{Config.INFLUXDB_BUCKET}")
              |> range(start: -{lookback_days}d)
              |> filter(fn: (r) =>
                  r["_measurement"] == "model_accuracy"
                  and r["symbol"] == "{symbol}"
                  and r["model"] == "{model}")
              |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> sort(columns: ["_time"], desc: true)
              |> limit(n: 1)
            """
            try:
                tables = self._svc.query_api.query(query)
                for t in tables:
                    for r in t.records:
                        vals = r.values
                        result[model] = {
                            "mae":     float(vals.get("mae_d1", 999.0)),
                            "samples": int(vals.get("sample_count", 0)),
                        }
            except Exception as e:
                logger.warning(f"[RL] query_ensemble_mae error for {symbol}/{model}: {e}")
        logger.debug(f"[RL] query_ensemble_mae — {symbol}: {result}")
        return result


# ---------------------------------------------------------------------------
# YFinance Service  —  free historical OHLCV + fundamentals
# ---------------------------------------------------------------------------

# Maps yfinance exchange codes → Google-Finance exchange suffixes. SerpAPI's
# google_finance engine only returns results for the "TICKER:EXCHANGE" format;
# a bare ticker errors with "hasn't returned any results".
_GOOGLE_EXCHANGE = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NAS": "NASDAQ",
    "NYQ": "NYSE",   "NYS": "NYSE",
    "PCX": "NYSEARCA",
    "ASE": "NYSEAMERICAN",
    "BTS": "BATS",
}


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

    @newrelic.agent.function_trace()
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
        logger.debug(
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
                df = df.loc[:, ~df.columns.duplicated(keep='first')]

            df.index = pd.to_datetime(df.index)
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")

            keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df   = df[keep].dropna(subset=["Close"])

            close_col = df['Close']
            logger.info(
                f"[YFINANCE] ✓ fetch_history — {len(df)} rows for {ticker} | "
                f"date range: {df.index.min().date()} → {df.index.max().date()} | "
                f"close: ${float(close_col.iloc[0]):.2f} (oldest) → "
                f"${float(close_col.iloc[-1]):.2f} (latest) | "
                f"columns: {list(df.columns)}"
            )
            return df

        except Exception as e:
            logger.error(f"[YFINANCE] ✗ fetch_history error for {ticker}: {e}")
            return pd.DataFrame()

    @newrelic.agent.function_trace()
    def fetch_info(self, symbol: str) -> dict:
        """
        Returns a dict of fundamentals:
        market_cap, pe_ratio, dividend_yield, prev_close, range_52w, current_price,
        plus extended quant fields: beta, forward_pe, peg_ratio, price_to_book,
        ev_to_ebitda, free_cash_flow, revenue_growth, total_debt, industry.
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("[YFINANCE] fetch_info SKIPPED — yfinance not installed")
            return {}

        ticker = self._to_yf_symbol(symbol)
        logger.debug(f"[YFINANCE] fetch_info — ticker={ticker}")

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
            # Compute dividend yield from annualized rate ÷ price (accurate for
            # any stock post-split). yfinance's dividendYield field is unreliable
            # — it can be 100× too large on low-yield tickers like NVDA.
            _div_rate = (
                info.get("trailingAnnualDividendRate")
                or info.get("dividendRate")
                or 0.0
            )
            _price_for_yield = float(current) if float(current) > 0 else 0.0
            if _div_rate and float(_div_rate) > 0 and _price_for_yield > 0:
                dividend_yield = float(_div_rate) / _price_for_yield  # decimal fraction
            else:
                dividend_yield = "N/A"

            result = {
                "current_price":   float(current),
                "market_cap":      info.get("marketCap",           "N/A"),
                "pe_ratio":        info.get("trailingPE",          "N/A"),
                "dividend_yield":  dividend_yield,
                "prev_close":      prev_close or "N/A",
                "range_52w":       range_52w,
                "short_name":      info.get("shortName",       ticker),
                "sector":          info.get("sector",          "N/A"),
                "industry":        info.get("industry",        "N/A"),
                "currency":        info.get("currency",        "USD"),
                # Google-Finance exchange suffix (e.g. NASDAQ/NYSE) derived from
                # yfinance's exchange code — needed for the SerpAPI google_finance
                # query, which requires the TICKER:EXCHANGE format. "" when unknown.
                "exchange":        _GOOGLE_EXCHANGE.get(info.get("exchange") or "", ""),
                # Extended quant fundamentals
                "beta":            info.get("beta",                 "N/A"),
                "forward_pe":      info.get("forwardPE",            "N/A"),
                "peg_ratio":       info.get("pegRatio",             "N/A"),
                "price_to_book":   info.get("priceToBook",          "N/A"),
                "ev_to_ebitda":    info.get("enterpriseToEbitda",   "N/A"),
                "free_cash_flow":  info.get("freeCashflow",         "N/A"),
                "revenue_growth":  info.get("revenueGrowth",        "N/A"),
                "total_debt":      info.get("totalDebt",            "N/A"),
            }
            logger.info(
                f"[YFINANCE] ✓ fetch_info — {ticker}: "
                f"price=${result['current_price']:.2f}, "
                f"market_cap={result['market_cap']}, pe={result['pe_ratio']}, "
                f"fwd_pe={result['forward_pe']}, peg={result['peg_ratio']}, "
                f"beta={result['beta']}, ev/ebitda={result['ev_to_ebitda']}, "
                f"sector={result['sector']}, industry={result['industry']}"
            )
            return result

        except Exception as e:
            logger.error(f"[YFINANCE] ✗ fetch_info error for {ticker}: {e}")
            return {}

    @newrelic.agent.function_trace()
    def fetch_earnings_dates(self, symbol: str) -> List[str]:
        """
        Returns upcoming (and recent) earnings dates as 'MM/DD' strings,
        matching the chart date format used by PriceChartCard.
        Returns at most 4 dates; empty list on any failure.
        """
        if not YFINANCE_AVAILABLE:
            return []
        ticker = self._to_yf_symbol(symbol)
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is None:
                return []
            # yfinance returns a dict with 'Earnings Date' key → list of Timestamps
            dates_raw = cal.get("Earnings Date", [])
            if not isinstance(dates_raw, (list, tuple)):
                dates_raw = [dates_raw]
            result = []
            for d in dates_raw:
                try:
                    if hasattr(d, "strftime"):
                        result.append(d.strftime("%m/%d"))
                    else:
                        from datetime import datetime
                        result.append(datetime.strptime(str(d)[:10], "%Y-%m-%d").strftime("%m/%d"))
                except Exception as _exc:
                    logger.debug("[YFINANCE] earnings date parse error for %r: %s", d, _exc)
                    continue
            result = list(dict.fromkeys(result))[:4]  # deduplicate, cap at 4
            logger.info(f"[YFINANCE] ✓ fetch_earnings_dates — {ticker}: {result}")
            return result
        except Exception as e:
            logger.warning(f"[YFINANCE] fetch_earnings_dates failed for {ticker}: {e}")
            return []

    @newrelic.agent.function_trace()
    def fetch_earnings_surprise(self, symbol: str) -> List[dict]:
        """
        Last 4 quarters of earnings surprise from yfinance (free, no API key).

        Returns a list of {quarter, estimate, actual, surprise_pct} dicts,
        most-recent first. Empty list on any failure or when unavailable
        (logged at DEBUG, never raises).
        """
        if not YFINANCE_AVAILABLE:
            return []
        ticker = self._to_yf_symbol(symbol)
        try:
            hist = yf.Ticker(ticker).earnings_history
            if hist is None or getattr(hist, "empty", True):
                return []
            # yfinance returns a DataFrame indexed by quarter date with columns
            # epsEstimate / epsActual / surprisePercent (names vary by version).
            cols = {c.lower(): c for c in hist.columns}
            est_col = cols.get("epsestimate")
            act_col = cols.get("epsactual")
            sur_col = cols.get("surprisepercent")
            result: List[dict] = []
            for idx, row in hist.tail(4).iloc[::-1].iterrows():
                try:
                    quarter = (
                        idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime")
                        else str(idx)[:10]
                    )
                    est = float(row[est_col]) if est_col and pd.notna(row[est_col]) else None
                    act = float(row[act_col]) if act_col and pd.notna(row[act_col]) else None
                    if sur_col and pd.notna(row[sur_col]):
                        surprise = float(row[sur_col])
                    elif est not in (None, 0) and act is not None:
                        surprise = (act - est) / abs(est) * 100
                    else:
                        surprise = None
                    result.append({
                        "quarter":      quarter,
                        "estimate":     round(est, 4) if est is not None else None,
                        "actual":       round(act, 4) if act is not None else None,
                        "surprise_pct": round(surprise, 2) if surprise is not None else None,
                    })
                except Exception as _exc:
                    logger.debug("[YFINANCE] earnings surprise row parse error: %s", _exc)
                    continue
            logger.info(f"[YFINANCE] ✓ fetch_earnings_surprise — {ticker}: {len(result)} quarters")
            return result
        except Exception as e:
            logger.debug(f"[YFINANCE] fetch_earnings_surprise failed for {ticker}: {e}")
            return []

    @newrelic.agent.function_trace()
    def fetch_news(self, symbol: str) -> List[dict]:
        """
        Fetch recent news headlines from yfinance (free, no API key).
        Returns list of dicts with title, source, source_label.
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("[YFINANCE] fetch_news SKIPPED — yfinance not installed")
            return []
        ticker = self._to_yf_symbol(symbol)
        try:
            raw = yf.Ticker(ticker).news
            if not raw or not isinstance(raw, list):
                logger.info(f"[YFINANCE] fetch_news — {ticker}: 0 articles returned")
                return []
            result = []
            for item in raw[:12]:
                # yfinance 1.x uses a nested 'content' dict; older versions use a flat dict.
                content = item.get("content") if isinstance(item.get("content"), dict) else item
                title = (
                    content.get("title") or item.get("title") or ""
                ).strip()
                if not title:
                    continue
                source = (
                    (content.get("provider") or {}).get("displayName")
                    or item.get("publisher")
                    or "yfinance"
                )
                link = (
                    (content.get("clickThroughUrl") or {}).get("url")
                    or item.get("link")
                    or ""
                )
                result.append({
                    "title":        title,
                    "link":         link,
                    "source":       source,
                    "thumbnail":    "",
                    "date":         "",
                    "source_label": "yfinance",
                })
            logger.info(f"[YFINANCE] ✓ fetch_news — {ticker}: {len(result)} articles")
            return result
        except Exception as e:
            logger.warning(f"[YFINANCE] fetch_news failed for {ticker}: {e}")
            return []

    @newrelic.agent.function_trace()
    def get_live_price(self, symbol: str) -> float:
        """Fast path to get the latest price from yfinance."""
        if not YFINANCE_AVAILABLE:
            logger.warning("[YFINANCE] get_live_price SKIPPED — yfinance not installed")
            return 0.0

        ticker = self._to_yf_symbol(symbol)
        logger.debug(f"[YFINANCE] get_live_price — ticker={ticker}")

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
        logger.debug(
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
            logger.debug(f"[CLEANER] NaN/zero Close rows removed: {nan_removed}")
        else:
            logger.debug("[CLEANER] NaN/zero check — 0 rows removed (all Close values valid)")

        if df.empty:
            logger.warning("[CLEANER] DataFrame empty after NaN/zero drop — returning empty")
            return df

        # 2. Remove outliers: Close values > 4σ from rolling 30-day median.
        #    Rows where the band can't be computed (fewer than min_periods in the
        #    window → NaN bounds) are KEPT, not dropped: a NaN comparison is False,
        #    so without this guard a short history (e.g. a just-listed ticker with
        #    <5 bars) would mask out every row → empty df → spurious 404.
        rolling_med = df["Close"].rolling(30, min_periods=5, center=True).median()
        rolling_std = df["Close"].rolling(30, min_periods=5, center=True).std()
        upper = rolling_med + 4 * rolling_std
        lower = rolling_med - 4 * rolling_std
        band_unknown = upper.isna() | lower.isna()
        mask  = band_unknown | ((df["Close"] >= lower) & (df["Close"] <= upper))
        removed = int((~mask).sum())
        if removed:
            logger.debug(
                f"[CLEANER] Outlier rows removed (>4σ from 30d rolling median): {removed}"
            )
        else:
            logger.debug(
                "[CLEANER] Outlier check — 0 rows removed (all within 4σ rolling bands)"
            )
        df = df[mask]
        after_outlier = len(df)

        if df.empty:
            logger.warning("[CLEANER] DataFrame empty after outlier removal — returning empty")
            return df

        # 3. Reindex to business-day frequency and forward-fill gaps.
        #    IMPORTANT: Only price columns (Open/High/Low/Close) are
        #    forward-filled. Volume is LEFT AS NaN on synthetic rows and then
        #    set to 0 — forward-filling volume copies real traded volume onto
        #    non-trading days, which biases Prophet/SARIMAX/RF (they'd see
        #    repeated high-volume bars that never actually happened).
        #    Downstream (main.py) replaces zero-volume rows with a rolling
        #    mean so the synthetic markers don't contaminate normalisation.
        try:
            full_idx = pd.bdate_range(
                start=df.index.min(), end=df.index.max(), freq="B"
            )
            full_idx = full_idx.tz_localize("UTC") if full_idx.tz is None else full_idx

            price_cols = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]
            has_volume = "Volume" in df.columns

            df = df.reindex(full_idx)
            if price_cols:
                df[price_cols] = df[price_cols].ffill()
            if has_volume:
                # Mark synthetic rows with volume=0 (not ffill).
                df["Volume"] = df["Volume"].fillna(0.0)

            after_ffill = len(df)
            synthetic   = after_ffill - after_outlier
            logger.debug(
                f"[CLEANER] Gap-fill (bdate_range ffill) — "
                f"rows before={after_outlier}, after={after_ffill} "
                f"(+{synthetic} synthetic rows; price ffill, volume=0 on synthetics)"
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
            logger.debug("[CLEANER] OHLC integrity enforced — High≥Close≥Low corrected")

        logger.info(
            f"[CLEANER] ✓ clean() complete — output: {len(df)} rows "
            f"(from {input_rows} input, net delta={len(df) - input_rows:+d})"
        )
        return df

    @staticmethod
    def to_history_list(df: pd.DataFrame) -> list:
        """Convert cleaned DataFrame → list of dicts used by main.py and models."""
        if df.empty:
            logger.warning("[CLEANER] to_history_list() — empty DataFrame, returning []")
            return []

        logger.debug(f"[CLEANER] to_history_list() — converting {len(df)} rows to dicts")
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

        if out:
            logger.info(
                f"[CLEANER] ✓ to_history_list() — {len(out)} dict rows produced | "
                f"close: ${out[0]['close']:.2f} (oldest) → ${out[-1]['close']:.2f} (latest)"
            )
        else:
            logger.warning("[CLEANER] to_history_list() — 0 rows produced from non-empty df")
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

    @staticmethod
    def _parse_trending(data: dict) -> List[dict]:
        """Build a trending-ticker list from the google_finance `discover_more`
        block (related/most-active tickers). Each item carries symbol, price and
        a signed change string the frontend sparklines understand."""
        trending: List[dict] = []
        seen: set = set()
        for block in data.get("discover_more", []) or []:
            for it in (block.get("items", []) if isinstance(block, dict) else []):
                stock = str(it.get("stock", ""))          # e.g. "TSLA:NASDAQ"
                sym = stock.split(":")[0].strip().upper()
                if not sym or sym in seen:
                    continue
                mv = it.get("price_movement", {}) or {}
                pct = mv.get("percentage")
                up = str(mv.get("movement", "")).lower() == "up"
                change = (f"{'+' if up else '-'}{pct}%") if pct is not None else ""
                trending.append({
                    "symbol": sym,
                    "price":  it.get("price", ""),
                    "change": change,
                })
                seen.add(sym)
        return trending

    async def fetch_data(self, query: str, exchange: str = "NASDAQ") -> dict:
        """
        Query SerpAPI Google Finance for news and trending market data.
        Returns a dict with keys:
          - news_results : list of news articles
          - markets      : dict of category → list of tickers (legacy)
          - trending     : list of trending tickers (from `discover_more`)
        Falls back to empty structure if the API key is missing or the call fails.

        The google_finance engine requires a "TICKER:EXCHANGE" query — a bare
        ticker returns an error — so the exchange suffix is appended when absent.
        """
        if not Config.SERP_API_KEY:
            logger.info(
                "[SERP] API key not set — news/trending fetch SKIPPED "
                "(returning empty news_results and markets)"
            )
            return {"news_results": [], "markets": {}, "trending": []}

        # google_finance needs TICKER:EXCHANGE. Honor an already-qualified query;
        # otherwise append the resolved exchange (default NASDAQ).
        gq = query if ":" in query else f"{query.upper()}:{(exchange or 'NASDAQ').upper()}"

        logger.debug(
            f"[SERP] fetch_data — query='{gq}', engine=google_finance, timeout=25s"
        )
        params = {
            "engine":  "google_finance",
            "q":       gq,
            "api_key": Config.SERP_API_KEY,
        }
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.get("https://serpapi.com/search", params=params)
                resp.raise_for_status()
                data = resp.json()

            if data.get("error"):
                logger.warning(f"[SERP] google_finance returned no results for '{gq}': {data['error']}")
                return {"news_results": [], "markets": {}, "trending": []}

            trending      = self._parse_trending(data)
            news_count    = len(data.get("news_results", []))
            logger.info(
                f"[SERP] ✓ fetch_data — query='{gq}' | "
                f"news_articles={news_count} | "
                f"trending_tickers={len(trending)}"
            )
            return {
                "news_results": data.get("news_results", []),
                "markets":      data.get("markets",      {}),
                "trending":     trending,
            }

        except Exception as e:
            logger.warning(f"[SERP] fetch_data failed ('{gq}'): {e} → fallback: 0 articles, empty trending")
            return {"news_results": [], "markets": {}, "trending": []}


# ---------------------------------------------------------------------------
# Finnhub Service  —  company news via Finnhub REST API
# ---------------------------------------------------------------------------

class FinnhubService:
    """
    Fetches company news from Finnhub (last 7 days).
    Requires FINNHUB_API_KEY; gracefully skips if not set.
    """
    _BASE_URL = "https://finnhub.io/api/v1/company-news"

    async def fetch_company_news(self, symbol: str) -> List[dict]:
        if not Config.FINNHUB_API_KEY:
            logger.info("[FINNHUB] API key not set — company news fetch SKIPPED")
            return []
        sym = symbol.split(":")[0].upper()
        to_date   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        from_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        params = {
            "symbol": sym,
            "from":   from_date,
            "to":     to_date,
            "token":  Config.FINNHUB_API_KEY,
        }
        logger.debug(f"[FINNHUB] fetch_company_news — symbol={sym}, from={from_date}, to={to_date}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self._BASE_URL, params=params)
                resp.raise_for_status()
                articles = resp.json()
            result = []
            for a in (articles or [])[:10]:
                headline = a.get("headline", "").strip()
                if not headline:
                    continue
                result.append({
                    "title":        headline,
                    "link":         a.get("url", ""),
                    "source":       a.get("source", "Finnhub"),
                    "thumbnail":    a.get("image", ""),
                    "date":         "",
                    "source_label": "Finnhub",
                })
            logger.info(f"[FINNHUB] ✓ fetch_company_news — {sym}: {len(result)} articles")
            return result
        except Exception as e:
            logger.warning(f"[FINNHUB] fetch_company_news failed for {sym}: {e} — returning []")
            return []


# ---------------------------------------------------------------------------
# StockTwits Service  —  social sentiment from StockTwits feed
# ---------------------------------------------------------------------------

class StockTwitsService:
    """
    Fetches the StockTwits symbol stream, counts Bullish/Bearish tags on the
    last N messages and returns a ratio in [-1, 1]: +1 = all bullish,
    -1 = all bearish.

    NOTE: the public `api.stocktwits.com` endpoint now returns 403 Forbidden
    without authentication, so the caller gates this behind
    `Config.STOCKTWITS_ENABLED` (off by default). The parsing logic below is
    kept intact for when an authed/working source is wired up.
    """
    _BASE_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"

    async def fetch_sentiment(self, symbol: str) -> dict:
        empty = {"bullish": 0, "bearish": 0, "sentiment": 0.0}
        sym = symbol.split(":")[0].upper()
        url = self._BASE_URL.format(symbol=sym)
        logger.debug(f"[STOCKTWITS] fetch_sentiment — symbol={sym}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            messages = data.get("messages", [])
            bullish = sum(
                1 for m in messages
                if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish"
            )
            bearish = sum(
                1 for m in messages
                if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish"
            )
            total = bullish + bearish
            ratio = round((bullish - bearish) / total, 3) if total > 0 else 0.0
            logger.info(
                f"[STOCKTWITS] ✓ {sym}: {len(messages)} msgs | "
                f"bullish={bullish}, bearish={bearish}, ratio={ratio:+.3f}"
            )
            return {"bullish": bullish, "bearish": bearish, "sentiment": ratio}
        except Exception as e:
            logger.warning(f"[STOCKTWITS] fetch_sentiment failed for {sym}: {e} — returning empty")
            return empty


# ---------------------------------------------------------------------------
# Yahoo Finance RSS Service  —  free headline feed, no API key required
# ---------------------------------------------------------------------------

class YahooRSSService:
    """
    Fetches stock news from Yahoo Finance's public RSS feed.
    No API key needed — works anywhere Yahoo Finance is reachable.
    Falls back gracefully (logs + returns []) on any network error.
    """
    _BASE_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"

    async def fetch_news(self, symbol: str) -> List[dict]:
        sym = symbol.split(":")[0].upper()
        params = {"s": sym, "region": "US", "lang": "en-US"}
        logger.debug(f"[YAHOORSE] fetch_news — symbol={sym}")
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; FiForesight/1.0)"},
            ) as client:
                resp = await client.get(self._BASE_URL, params=params)
                resp.raise_for_status()
            root = ET.fromstring(resp.text)
            channel = root.find("channel")
            if channel is None:
                logger.info(f"[YAHOORSE] {sym}: RSS channel element missing")
                return []
            result = []
            for item in channel.findall("item")[:10]:
                title = (item.findtext("title") or "").strip()
                if not title:
                    continue
                result.append({
                    "title":        title,
                    "link":         item.findtext("link") or "",
                    "source":       "Yahoo Finance",
                    "thumbnail":    "",
                    "date":         item.findtext("pubDate") or "",
                    "source_label": "Yahoo RSS",
                })
            logger.info(f"[YAHOORSE] ✓ fetch_news — {sym}: {len(result)} articles")
            return result
        except Exception as e:
            logger.warning(f"[YAHOORSE] fetch_news failed for {sym}: {e} — returning []")
            return []


# ---------------------------------------------------------------------------
# Alternative Data Sources (Feature 15)
#   FREDService          — FRED macro snapshot (free CSV endpoint, no key needed)
#   InsiderService       — SEC EDGAR Form 4 insider transactions (keyless)
#   ShortInterestService — FINRA weekly short-volume file (free, keyless)
# Each fails closed (returns {}/[]/None, logged) so a bad fetch never blocks
# /predict or the jury. Caching TTLs: FRED 1h, insider 6h, short interest 24h.
# ---------------------------------------------------------------------------


def _parse_fred_csv(text: str, last_n: int = 31) -> List[tuple]:
    """Parse a FRED ``fredgraph.csv`` body into the last ``last_n`` (date, value)
    pairs, skipping the header and the ``.`` missing-value markers.

    FRED CSVs are ``DATE,SERIES_ID`` (older) or ``observation_date,SERIES_ID``
    (newer); either way the first column is the date and the second the value.
    Returns oldest→newest. Empty list on any malformed input.
    """
    rows: List[tuple] = []
    for line in text.strip().splitlines()[1:]:  # skip header
        parts = line.split(",")
        if len(parts) < 2:
            continue
        date_s, val_s = parts[0].strip(), parts[1].strip()
        if not date_s or val_s in ("", "."):
            continue
        try:
            rows.append((date_s, float(val_s)))
        except ValueError:
            continue
    return rows[-last_n:]


class FREDService:
    """Free FRED macro snapshot.

    Pulls a handful of headline series from the public FRED CSV endpoint
    (``fredgraph.csv?id=SERIES``) — no API key required. ``FRED_API_KEY`` is
    optional and only raises the rate limit; the CSV endpoint works without it.

    ``get_macro_snapshot()`` returns per-series ``{value, delta_30d}`` plus a
    yield-curve ``inverted`` flag and the T10Y2Y 31-point trend (for the macro
    dashboard chart). Redis-cached 1h under ``fred:snapshot``.
    """

    _CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    # series id → snapshot key (lower-cased, stable for the frontend)
    _SERIES = {
        "DGS10":    "dgs10",     # 10-Year Treasury constant-maturity yield
        "CPIAUCSL": "cpiaucsl",  # CPI, all urban consumers
        "UNRATE":   "unrate",    # Unemployment rate
        "FEDFUNDS": "fedfunds",  # Effective federal funds rate
        "T10Y2Y":   "t10y2y",    # 10Y minus 2Y spread (negative = inverted)
    }
    _CACHE_KEY = "fred:snapshot"
    _CACHE_TTL = 3600  # 1h

    async def _fetch_series(self, client: "httpx.AsyncClient", series_id: str) -> List[tuple]:
        """Fetch one series' last 31 (date, value) points. [] on any failure.

        A ``cosd`` start-date window is sent so daily series (DGS10/T10Y2Y, whose
        full history runs to ~16k rows) don't download decades of data and time
        out. ~1150 days still yields ≥31 points for the monthly series too.
        """
        cosd = (datetime.now(timezone.utc).date() - timedelta(days=1150)).isoformat()
        params = {"id": series_id, "cosd": cosd}
        if Config.FRED_API_KEY:
            params["api_key"] = Config.FRED_API_KEY
        # Under the 5-way concurrent burst FRED occasionally drops one keep-alive
        # connection (a bare RemoteProtocolError), usually on a daily series.
        # One retry — by then the other requests have drained — recovers it.
        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                resp = await asyncio.wait_for(
                    client.get(self._CSV_URL, params=params), timeout=12.0
                )
                resp.raise_for_status()
                return _parse_fred_csv(resp.text)
            except Exception as exc:
                last_exc = exc
                if attempt == 1:
                    await asyncio.sleep(0.25)
        logger.warning(
            "[FRED] series %s fetch failed after retry: %r", series_id, last_exc
        )
        return []

    async def get_macro_snapshot(self) -> dict:
        """Return the macro snapshot dict (Redis-cached 1h). {} on total failure."""
        from redis_cache import cache_get, cache_set

        cached = await cache_get(self._CACHE_KEY)
        if cached:
            return cached

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(12.0, connect=8.0),
                headers={"User-Agent": "FiForesight/1.0 research@fiforesight.dev"},
            ) as client:
                series_ids = list(self._SERIES.keys())
                # Warm the keep-alive connection with the first series, THEN fan
                # the rest out concurrently. Firing all 5 at once on a cold pool
                # made FRED drop a daily-series connection (ReadTimeout); reusing
                # an established connection for the concurrent batch avoids it.
                first = await self._fetch_series(client, series_ids[0])
                rest = await asyncio.gather(
                    *(self._fetch_series(client, sid) for sid in series_ids[1:])
                )
                results = [first, *rest]
        except Exception as exc:
            logger.warning("[FRED] snapshot fetch failed: %s — returning {}", exc)
            return {}

        snapshot: dict = {}
        t10y2y_trend: List[dict] = []
        for sid, points in zip(series_ids, results):
            key = self._SERIES[sid]
            if not points:
                continue
            current = round(points[-1][1], 4)
            baseline = points[0][1]
            delta = round(current - baseline, 4)
            snapshot[key] = {"value": current, "delta_30d": delta}
            if key == "t10y2y":
                t10y2y_trend = [{"date": d, "value": round(v, 4)} for d, v in points]

        if not snapshot:
            logger.warning("[FRED] all series empty — returning {}")
            return {}

        t10y2y_val = snapshot.get("t10y2y", {}).get("value")
        snapshot["inverted"] = bool(t10y2y_val is not None and t10y2y_val < 0)
        snapshot["t10y2y_trend"] = t10y2y_trend
        snapshot["fetched_at"] = datetime.now(timezone.utc).isoformat()

        await cache_set(self._CACHE_KEY, snapshot, ttl_seconds=self._CACHE_TTL)
        logger.info(
            "[FRED] ✓ macro snapshot — %d series, inverted=%s",
            len(snapshot) - 3, snapshot["inverted"],
        )
        return snapshot


# Transaction-code → (label, simple type) map for Form 4 (SEC Table I codes).
_FORM4_CODE_LABELS = {
    "P": "Purchase",
    "S": "Sale",
    "A": "Award",
    "M": "Option Exercise",
    "G": "Gift",
    "F": "Tax Withholding",
    "X": "Option Exercise",
    "C": "Conversion",
}


class InsiderService:
    """SEC EDGAR Form 4 insider transactions — keyless.

    Uses the EDGAR full-text search index (``efts.sec.gov``) to find recent
    Form 4 filings for a symbol over the last 30 days, mapping each hit onto a
    compact ``{filer, type, shares, price, date, sec_link}`` shape. The
    full-text index carries filing metadata reliably (filer names, date, link);
    transaction code/shares/price are surfaced when present, else ``None``.

    Redis-cached 6h per symbol. Returns ``[]`` on any failure (never raises).
    """

    _SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
    _HEADERS = {"User-Agent": "FiForesight research@fiforesight.dev"}
    _CACHE_TTL = 21600  # 6h

    @staticmethod
    def _map_type(code: Any) -> str:
        """Map a Form 4 transaction code (or free-text) onto a display label."""
        if not code:
            return "Filing"
        c = str(code).strip().upper()
        if c in _FORM4_CODE_LABELS:
            return _FORM4_CODE_LABELS[c]
        # Already a word like "Purchase"/"Sale"/"Award"
        for label in ("Purchase", "Sale", "Award"):
            if label.lower() in c.lower():
                return label
        return "Filing"

    @staticmethod
    def _sec_link(hit: dict, src: dict) -> str:
        """Best-effort link to the filing on sec.gov from the FTS hit."""
        _id = hit.get("_id") or ""
        ciks = src.get("ciks") or []
        cik = str(ciks[0]).lstrip("0") if ciks else ""
        if _id and ":" in _id and cik:
            accession, _, filename = _id.partition(":")
            acc_nodash = accession.replace("-", "")
            return f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{filename}"
        if cik:
            return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4"
        return "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4"

    @staticmethod
    def _to_float(v: Any) -> Optional[float]:
        try:
            f = float(v)
            return None if math.isnan(f) else f  # filter NaN
        except (TypeError, ValueError):
            return None

    def _map_hit(self, hit: dict) -> Optional[dict]:
        src = hit.get("_source") or {}
        names = src.get("display_names") or []
        # display_names is typically ["Issuer (CIK ...)", "Reporting Owner (CIK ...)"];
        # the reporting owner (the insider) is the filer we want.
        filer = ""
        if names:
            filer = str(names[-1]).split(" (")[0].strip()
        shares = self._to_float(src.get("shares") or src.get("transaction_shares"))
        price = self._to_float(src.get("price") or src.get("transaction_price"))
        return {
            "filer":    filer or "Unknown",
            "type":     self._map_type(src.get("transaction_code") or src.get("type")),
            "shares":   int(shares) if shares is not None else None,
            "price":    round(price, 2) if price is not None else None,
            "date":     str(src.get("file_date") or src.get("date") or "")[:10],
            "sec_link": self._sec_link(hit, src),
        }

    async def get_insider_transactions(self, symbol: str) -> List[dict]:
        from redis_cache import cache_get, cache_set

        sym = symbol.split(":")[0].upper()
        cache_key = f"insider:{sym}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        today = datetime.now(timezone.utc).date()
        startdt = (today - timedelta(days=30)).isoformat()
        params = {
            "q": f'"{sym}"',
            "forms": "4",
            "dateRange": "custom",
            "startdt": startdt,
            "enddt": today.isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=self._HEADERS) as client:
                resp = await asyncio.wait_for(
                    client.get(self._SEARCH_URL, params=params), timeout=12.0
                )
                resp.raise_for_status()
                raw = resp.json()
            hits = ((raw or {}).get("hits", {}) or {}).get("hits", []) or []
            result: List[dict] = []
            for hit in hits[:10]:
                try:
                    mapped = self._map_hit(hit)
                    if mapped:
                        result.append(mapped)
                except Exception as exc:
                    logger.debug("[INSIDER] hit map error: %s", exc)
                    continue
            logger.info("[INSIDER] ✓ %s — %d Form 4 filings", sym, len(result))
            # Cache real results 6h; an empty list briefly (1h) so a transient
            # failure self-heals rather than sticking for the full window.
            await cache_set(cache_key, result, ttl_seconds=self._CACHE_TTL if result else 3600)
            return result
        except Exception as exc:
            logger.warning("[INSIDER] fetch failed for %s: %s — returning []", sym, exc)
            return []


class ShortInterestService:
    """FINRA weekly short-volume — free, keyless.

    FINRA publishes a consolidated NMS short-volume file each trading day at
    ``cdn.finra.org/equity/regsho/weekly/CNMSshvol{YYYYMMDD}.txt`` (tab/pipe
    delimited). We download the most recent available file, parse it into a
    ``{symbol: {short_volume, total_volume}}`` map, and cache it in Redis as a
    JSON blob (24h TTL). Per-symbol lookups derive ``short_ratio`` and
    ``days_to_cover`` (short_volume ÷ average daily volume).

    Returns ``None`` for symbols absent from the file (non-US / OTC) and on any
    failure — never raises.
    """

    _BASE_URL = "https://cdn.finra.org/equity/regsho/weekly/CNMSshvol{date}.txt"
    _CACHE_TTL = 86400  # 24h

    async def _load_map(self) -> dict:
        """Return ``{report_date, symbols: {sym: {short_volume, total_volume}}}``.

        Tries the last ~8 calendar days (most-recent first) until a file
        downloads. Caches the parsed blob in Redis keyed by the file's date.
        """
        from redis_cache import cache_get, cache_set

        today = datetime.now(timezone.utc).date()
        async with httpx.AsyncClient(
            timeout=15.0, headers={"User-Agent": "FiForesight/1.0"}
        ) as client:
            for back in range(0, 8):
                d = today - timedelta(days=back)
                date_str = d.strftime("%Y%m%d")
                cache_key = f"finra:short:{date_str}"
                cached = await cache_get(cache_key)
                if cached:
                    return cached
                url = self._BASE_URL.format(date=date_str)
                try:
                    resp = await asyncio.wait_for(client.get(url), timeout=12.0)
                    if resp.status_code != 200 or not resp.text.strip():
                        continue
                    parsed = self._parse_finra(resp.text, date_str)
                    if parsed["symbols"]:
                        await cache_set(cache_key, parsed, ttl_seconds=self._CACHE_TTL)
                        logger.info(
                            "[SHORT] ✓ FINRA file %s — %d symbols",
                            date_str, len(parsed["symbols"]),
                        )
                        return parsed
                except Exception as exc:
                    logger.debug("[SHORT] FINRA %s unavailable: %s", date_str, exc)
                    continue
        logger.warning("[SHORT] no recent FINRA file found in last 8 days")
        return {"report_date": "", "symbols": {}}

    @staticmethod
    def _parse_finra(text: str, date_str: str) -> dict:
        """Parse the pipe-delimited FINRA short-volume file.

        Columns: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market.
        """
        symbols: dict = {}
        lines = text.strip().splitlines()
        for line in lines[1:]:  # skip header
            parts = line.split("|")
            if len(parts) < 5:
                continue
            sym = parts[1].strip().upper()
            if not sym:
                continue
            try:
                short_vol = float(parts[2])
                total_vol = float(parts[4])
            except (ValueError, IndexError):
                continue
            symbols[sym] = {"short_volume": short_vol, "total_volume": total_vol}
        report_date = (
            f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}" if len(date_str) == 8 else date_str
        )
        return {"report_date": report_date, "symbols": symbols}

    def _avg_daily_volume(self, symbol: str) -> Optional[float]:
        """Average daily volume from yfinance (for days-to-cover). None on failure."""
        if not YFINANCE_AVAILABLE:
            return None
        try:
            info = yf.Ticker(symbol.split(":")[0].upper()).info
            avg = info.get("averageVolume") or info.get("averageDailyVolume10Day")
            return float(avg) if avg else None
        except Exception as exc:
            logger.debug("[SHORT] avg volume fetch failed for %s: %s", symbol, exc)
            return None

    async def get_short_interest(self, symbol: str) -> Optional[dict]:
        """Return short-interest metrics for ``symbol`` or ``None`` if absent.

        The computed result (incl. the yfinance-backed days-to-cover) is cached
        per symbol for 24h so repeated lookups don't re-hit yfinance — matching
        the documented short-interest caching contract.
        """
        from redis_cache import cache_get, cache_set

        sym = symbol.split(":")[0].upper()
        cache_key = f"short:interest:{sym}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        data = await self._load_map()
        entry = data.get("symbols", {}).get(sym)
        if not entry:
            # Absent symbols never reach yfinance, so there's nothing expensive
            # to memoise (and cache_get discards a cached None anyway).
            logger.info("[SHORT] %s not in FINRA file — returning None", sym)
            return None

        short_vol = entry["short_volume"]
        total_vol = entry["total_volume"]
        short_ratio = round(short_vol / total_vol, 4) if total_vol else None
        avg_vol = await asyncio.wait_for(
            asyncio.to_thread(self._avg_daily_volume, sym), timeout=12.0
        )
        days_to_cover = (
            round(short_vol / avg_vol, 2) if avg_vol and avg_vol > 0 else None
        )
        result = {
            "short_volume":  int(short_vol),
            "total_volume":  int(total_vol),
            "short_ratio":   short_ratio,
            "days_to_cover": days_to_cover,
            "report_date":   data.get("report_date", ""),
        }
        await cache_set(cache_key, result, ttl_seconds=self._CACHE_TTL)
        return result


# ---------------------------------------------------------------------------
# Regime Service  —  3-state Gaussian HMM market-regime detection (Feature 16)
# ---------------------------------------------------------------------------

# Stable regime labels, lowest → highest mean log-return.
REGIME_TRENDING_DOWN = "trending_down"
REGIME_RANGING       = "ranging"
REGIME_TRENDING_UP   = "trending_up"
REGIME_UNKNOWN       = "unknown"

_REGIME_UNKNOWN_RESULT: Dict[str, Any] = {"regime": REGIME_UNKNOWN, "confidence": 0.0}


class RegimeService:
    """Live 3-state market-regime detection via a Gaussian HMM.

    A ``GaussianHMM(n_components=3)`` is fit per request on the last 60 bars of
    a symbol using two features per bar — the daily log return and a 5-day
    realised-volatility proxy (rolling std of log returns, mean-normalised),
    both standardised. The three hidden states are mapped to stable labels by
    sorting on mean log return: highest → ``trending_up``, lowest →
    ``trending_down``, middle → ``ranging``.

    ``get_regime()`` returns::

        {
          "regime": "trending_up",
          "confidence": 0.83,                # predict_proba()[-1].max()
          "state_means": {...},              # label → mean log return
          "bars_in_current_regime": 7,       # trailing consecutive same-state bars
        }

    The fit is fully wrapped — any hmmlearn / numerical failure (or < 30 bars)
    degrades to ``{"regime": "unknown", "confidence": 0.0}`` and is logged at
    WARNING, so it never raises from ``/predict``. Result is Redis-cached 4h
    under ``regime:{symbol}:{date}``.
    """

    _MIN_BARS  = 30
    _WINDOW    = 60
    _VOL_SPAN  = 5
    _CACHE_TTL = 4 * 3600  # 4h

    async def get_regime(self, symbol: str, closes: List[float]) -> dict:
        """Detect the current regime for ``symbol`` from its close series.

        Redis-cached 4h per symbol per UTC date. Never raises — returns the
        unknown fallback on any failure.
        """
        from redis_cache import cache_get, cache_set

        try:
            _validate_tag(symbol, "symbol")
        except ValueError as exc:
            logger.warning("[REGIME] rejected symbol — %s", exc)
            return dict(_REGIME_UNKNOWN_RESULT)

        today = datetime.now(timezone.utc).date().isoformat()
        cache_key = f"regime:{symbol.upper()}:{today}"
        # Isolate Redis failures so a cache blip never erases a valid HMM result.
        try:
            cached = await cache_get(cache_key)
        except Exception as exc:
            logger.warning("[REGIME] cache_get failed for %s: %s", symbol, exc)
            cached = None
        if isinstance(cached, dict) and cached.get("regime"):
            return cached

        result = await asyncio.to_thread(self._detect, list(closes or []))

        # Only cache real detections — a transient failure shouldn't stick for 4h.
        if result.get("regime") != REGIME_UNKNOWN:
            try:
                await cache_set(cache_key, result, ttl_seconds=self._CACHE_TTL)
            except Exception as exc:
                logger.warning("[REGIME] cache_set failed for %s: %s", symbol, exc)
        return result

    def _detect(self, closes: List[float]) -> dict:
        """Synchronous HMM fit + state assignment. Pure CPU; runs in a thread."""
        if len(closes) < self._MIN_BARS:
            logger.info(
                "[REGIME] only %d bars (<%d) — regime unknown",
                len(closes), self._MIN_BARS,
            )
            return dict(_REGIME_UNKNOWN_RESULT)

        try:
            import numpy as np
            from hmmlearn.hmm import GaussianHMM
            from sklearn.preprocessing import StandardScaler

            arr = np.asarray(closes[-self._WINDOW:], dtype=float)
            if np.any(arr <= 0):
                logger.warning("[REGIME] non-positive prices in window — regime unknown")
                return dict(_REGIME_UNKNOWN_RESULT)

            # Feature 1: daily log return.
            log_ret = np.diff(np.log(arr))
            # Feature 2: 5-day rolling std of log returns, mean-normalised.
            vol = pd.Series(log_ret).rolling(self._VOL_SPAN).std().to_numpy()
            valid = ~np.isnan(vol)
            log_ret_v = log_ret[valid]
            vol_v = vol[valid]
            mean_vol = float(np.mean(vol_v)) if vol_v.size else 0.0
            if mean_vol > 0:
                vol_v = vol_v / mean_vol

            if log_ret_v.size < self._MIN_BARS - self._VOL_SPAN:
                logger.info(
                    "[REGIME] only %d usable feature rows — regime unknown",
                    int(log_ret_v.size),
                )
                return dict(_REGIME_UNKNOWN_RESULT)

            features = np.column_stack([log_ret_v, vol_v])
            scaled = StandardScaler().fit_transform(features)

            model = GaussianHMM(
                n_components=3, covariance_type="full",
                n_iter=100, random_state=42,
            )
            model.fit(scaled)
            states = model.predict(scaled)
            proba = model.predict_proba(scaled)

            # Map states → labels by ascending mean log return. StandardScaler is
            # monotonic per feature, so ordering on scaled means_[:, 0] matches
            # ordering on raw log returns.
            order = list(np.argsort(model.means_[:, 0]))  # low → high
            label_by_state = {
                order[0]: REGIME_TRENDING_DOWN,
                order[1]: REGIME_RANGING,
                order[2]: REGIME_TRENDING_UP,
            }

            current_state = int(states[-1])
            regime = label_by_state[current_state]
            confidence = round(float(proba[-1].max()), 4)

            # Raw mean log return per labelled state (for the API / debugging).
            state_means: Dict[str, float] = {}
            for st, label in label_by_state.items():
                mask = states == st
                state_means[label] = (
                    round(float(np.mean(log_ret_v[mask])), 6) if mask.any() else 0.0
                )

            # Trailing run length of the current state.
            bars_in_current_regime = 0
            for s in states[::-1]:
                if int(s) == current_state:
                    bars_in_current_regime += 1
                else:
                    break

            logger.info(
                "[REGIME] ✓ %s (conf=%.2f, %d bars in state) — state_means=%s",
                regime, confidence, bars_in_current_regime, state_means,
            )
            return {
                "regime": regime,
                "confidence": confidence,
                "state_means": state_means,
                "bars_in_current_regime": bars_in_current_regime,
            }
        except Exception as exc:  # hmmlearn not installed, convergence error, etc.
            logger.warning("[REGIME] detection failed (%s) — regime unknown", exc)
            return dict(_REGIME_UNKNOWN_RESULT)


# ---------------------------------------------------------------------------
# Sentiment Service  —  VADER-based news headline scoring
# ---------------------------------------------------------------------------

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer as _VADER
    _VADER_AVAILABLE = True
except ImportError:
    _VADER = None  # type: ignore
    _VADER_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "[SENTIMENT] vaderSentiment not installed — run: pip install vaderSentiment"
    )


class SentimentService:
    """
    VADER-based sentiment scoring for news headlines.
    VADER (Valence Aware Dictionary and sEntiment Reasoner) is purpose-built
    for short financial/social text and requires no external API or model download.

    score_headlines() returns:
      compound      : float [-1, 1]  — aggregate sentiment
      label         : str            — 'Bullish' | 'Bearish' | 'Neutral'
      scores        : list[dict]     — per-headline scores
      headline_count: int
    """

    def __init__(self):
        self._analyzer = _VADER() if _VADER_AVAILABLE else None
        if self._analyzer:
            logger.info("[SENTIMENT] ✓ VADER SentimentIntensityAnalyzer ready")
        else:
            logger.warning("[SENTIMENT] VADER unavailable — sentiment scoring disabled")

    def score_headlines(self, headlines: List[str]) -> dict:
        empty = {"compound": 0.0, "label": "Neutral", "scores": [], "headline_count": 0}
        if not self._analyzer or not headlines:
            return empty

        scores = []
        for h in headlines:
            vs = self._analyzer.polarity_scores(h)
            scores.append({"text": h[:120], "compound": round(vs["compound"], 4)})

        compounds = [s["compound"] for s in scores]
        avg = sum(compounds) / len(compounds)
        label = "Bullish" if avg >= 0.05 else "Bearish" if avg <= -0.05 else "Neutral"

        logger.info(
            f"[SENTIMENT] ✓ scored {len(scores)} headlines — "
            f"compound={avg:.4f} ({label})"
        )
        return {
            "compound":       round(avg, 4),
            "label":          label,
            "scores":         scores,
            "headline_count": len(scores),
        }


# ---------------------------------------------------------------------------
# Analyst Jury  —  3 personas, each pinned to a different model & provider
#
# Free-tier rate limits (Groq on-demand plan, as of 2025-06):
#   LLAMA-4-SCOUT → meta-llama/llama-4-scout-17b-16e-instruct  30 RPM | 30K TPM |  1K RPD
#   LLAMA-70B     → llama-3.3-70b-versatile                    30 RPM | 12K TPM |  1K RPD
#   LLAMA-8B      → llama-3.1-8b-instant                       30 RPM |  6K TPM | 14.4K RPD ← best daily budget
#
# llama-3.1-8b-instant was chosen for the Quant slot because its 14,400 RPD (vs 1K for all
# other models) makes it resilient to back-to-back predicts without exhausting the daily budget.
# GPT-OSS-20B (1K RPD, reasoning model) was replaced: reasoning tokens consumed the entire
# max_tokens budget, leaving zero for content, and required per-model workarounds.
#
#   _ai_note uses Groq llama-3.3-70b independently (header note, not jury)
# ---------------------------------------------------------------------------

ANALYST_PERSONAS = [
    {
        "id":           "LLAMA-4-SCOUT",
        "avatar":       "L4",
        "title":        "Macro & Risk Lens",
        "model_label":  "Groq · Llama 4 Scout",
        "provider":     "groq",
        "api_model":    "meta-llama/llama-4-scout-17b-16e-instruct",
        "color":        "#94a3b8",
        # Persona-specific fallback so users can tell WHICH analyst failed
        # and what type of analysis is missing (not all three looking identical).
        "fallback_note": (
            "Macro & risk analysis unavailable this run — "
            "downside signals, systemic headwinds, and risk-adjusted positioning "
            "could not be evaluated."
        ),
        "system": (
            "You are a macro-economic and risk analyst running on Meta Llama 4 Scout. "
            "Your lens is downside scenarios, warning signals, and risk-adjusted positioning. "
            "Analyse the provided market data and news results. "
            "Identify systemic risks, fundamental red flags, and external headwinds "
            "that could materially impact this asset. "
            "Flag RSI extremes, negative trend slope, elevated volatility, or concerning forecast skew. "
            "Examine BB band squeeze/expansion, proximity to support/resistance, whether volume confirms "
            "or contradicts the move, and any fundamental red flags. "
            "If a bearish RSI or MACD divergence is flagged, treat it as a warning of a potential "
            "reversal lower and weight your risk stance accordingly. "
            "When a macro snapshot is provided, reference the 10Y Treasury yield (DGS10), "
            "the 10Y-2Y curve inversion status, and the unemployment rate (UNRATE) in one "
            "sentence on systemic backdrop. "
            "When a market regime is provided, adjust your risk assessment accordingly — "
            "trending regimes carry trend-continuation risk, ranging regimes carry whipsaw risk. "
            "Focus on what could go wrong, not growth upside. "
            "Be specific, actionable, and advisory — not generic. "
            "Conclude with a clear rating (Strong Sell / Sell / Hold) and your recommended risk stance."
        ),
    },
    {
        "id":           "LLAMA-70B",
        "avatar":       "70B",
        "title":        "Growth Lens",
        "model_label":  "Groq · llama-3.3-70b",
        "provider":     "groq",
        "api_model":    "llama-3.3-70b-versatile",
        "color":        "#00f2ff",
        "fallback_note": (
            "Growth analysis unavailable this run — "
            "momentum catalysts, earnings trajectory, and upside price targets "
            "could not be evaluated."
        ),
        "system": (
            "You are LLAMA-70B, a fundamental growth equity analyst running on Llama 3.3 70B. "
            "Your lens is momentum, corporate catalysts, and upside potential. "
            "Analyse the provided market data and SERP news results. "
            "Identify fundamental tailwinds, earnings momentum, product or sector catalysts, "
            "and breakout potential. Correlate positive news flow with price momentum and volume trends. "
            "Reference MACD momentum, SMA50/200 positioning, RSI strength, and forecast confidence. "
            "If a bullish RSI or MACD divergence is flagged, treat it as confirmation that downside "
            "momentum may be exhausting and an upside reversal is forming. "
            "When a macro snapshot is provided, note in one sentence how the CPI 30-day delta "
            "(inflation trend) could pressure or relieve this company's margins. "
            "When a market regime is provided, note that in trending regimes momentum signals are "
            "more reliable, so weight breakout/continuation setups higher than in a ranging regime. "
            "Ignore macro doomsday scenarios — focus on this asset's specific growth trajectory "
            "and why it has the potential to outperform. "
            "Be specific, actionable, and advisory — not generic. "
            "Conclude with a clear rating (Strong Buy / Buy / Hold) and an upside price target or range."
        ),
    },
    {
        "id":           "LLAMA-8B",
        "avatar":       "8B",
        "title":        "Quant Lens",
        "model_label":  "Groq · Llama 3.1 8B",
        "provider":     "groq",
        "api_model":    "llama-3.1-8b-instant",
        # Standard 320 max_tokens — llama-3.1-8b-instant is not a reasoning model so
        # no extra token budget is needed; output is direct JSON, no hidden reasoning.
        "color":        "#10b981",
        "fallback_note": (
            "Quantitative signal analysis unavailable this run — "
            "RSI regime, MACD crossover, Bollinger Band position, and statistical signals "
            "could not be processed."
        ),
        "system": (
            "You are a quantitative signal analyst running on Llama 3.1 8B Instant. "
            "Your lens is pure technical indicators and statistical signals — no macro bias, no news sentiment. "
            "Analyse the provided OHLCV data and indicator outputs. "
            "Interpret RSI regime, MACD histogram crossover state, Bollinger Band width and price position, "
            "SMA50/200 crossover proximity and % distance, annualised volatility, "
            "and volume confirmation of the trend. Cite the forecast confidence label explicitly. "
            "When an RSI or MACD divergence is flagged, state its directional implication and factor it "
            "into your probabilistic read. "
            "When a macro snapshot is provided, note in one sentence how the fed funds rate "
            "(FEDFUNDS) affects the discount rate and this asset's valuation sensitivity. "
            "When a market regime is provided, note that the ensemble weights have already been "
            "tilted to reflect it (SARIMA-favoured in trending, RF-favoured in ranging). "
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


# Appended to the user prompt only when live tools are available to the analyst.
# Encourages (but does not force) tool use before the final JSON verdict.
TOOL_PROMPT_HINT = (
    "\n\nYou have access to live market data tools: get_vix (volatility regime), "
    "get_put_call_ratio (options positioning), get_insider_flow (insider buy/sell), "
    "and get_macro_snapshot (rates & yield curve). Call any tools that would "
    "strengthen your analysis BEFORE giving your verdict. When you have gathered "
    "what you need, respond with the final JSON verdict described below."
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
    @newrelic.agent.function_trace()
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

        logger.debug(
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

        logger.debug(
            f"[{provider_label}] ✓ Response — model={model}, "
            f"response_chars={len(content)}, "
            f"http_status={resp.status_code}"
        )
        return content

    # ------------------------------------------------------------------
    # Internal: provider-specific wrapper
    # ------------------------------------------------------------------

    async def call_groq(
        self, model: str, system: str, user: str, max_tokens: int = 320
    ) -> str:
        """Public entry point for a single Groq chat completion."""
        return await self._call_groq(model, system, user, max_tokens)

    async def _call_groq(
        self, model: str, system: str, user: str, max_tokens: int = 320
    ) -> str:
        logger.debug(
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
        logger.debug(
            f"[GROQ] ✓ _call_groq complete — model={model}, "
            f"response_chars={len(result)}"
        )
        return result

    # ------------------------------------------------------------------
    # Internal: raw OpenAI-compatible POST returning the full JSON body
    # (needed for tool calling — callers inspect message.tool_calls)
    # ------------------------------------------------------------------
    @newrelic.agent.function_trace()
    async def _post_groq_raw(self, body: dict) -> dict:
        """POST a fully-formed chat-completions body to Groq, return parsed JSON.

        Raises httpx.HTTPStatusError on non-2xx so callers can inspect status codes
        (e.g. 429 rate-limit handling in the jury graph).
        """
        if not Config.GROQ_API_KEY:
            raise ValueError("GROQ API key not configured")
        headers = {
            "Authorization": f"Bearer {Config.GROQ_API_KEY}",
            "Content-Type":  "application/json",
        }
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(self.GROQ_BASE_URL, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Public: agentic Groq call with OpenAI-compatible function/tool use
    # ------------------------------------------------------------------
    @newrelic.agent.function_trace()
    async def call_groq_with_tools(
        self,
        model: str,
        system: str,
        user: str,
        tools: List[dict],
        tool_dispatcher,
        max_tokens: int = 320,
        max_rounds: int = 2,
        force_first: bool = False,
    ) -> tuple:
        """Run a tool-using analyst loop against Groq's OpenAI-compatible API.

        Loop:
          1. Send messages with `tools`. tool_choice is "required" on the first
             round when `force_first` is set (guarantees ≥1 tool call), else "auto".
          2. If the model returns tool_calls, dispatch each via `tool_dispatcher`
             (an async callable `(name, args_dict) -> str`), append the results as
             role=tool messages, and re-send.
          3. After `max_rounds` tool rounds, send once more WITHOUT tools so the
             model is forced to return its final text answer.

        Returns a tuple `(final_content, tools_used)` where `tools_used` is the
        ordered, de-duplicated list of tool names the model actually invoked.
        """
        messages: List[dict] = [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
        tools_used: List[str] = []

        # max_rounds tool rounds + 1 forced final (no-tools) round
        for round_idx in range(max_rounds + 1):
            include_tools = round_idx < max_rounds
            # In the forced final round (no tools), append an explicit instruction
            # so reasoning models don't keep trying to call more tools.
            final_messages = messages
            if not include_tools and len(messages) > 2:
                final_messages = messages + [
                    {
                        "role":    "user",
                        "content": (
                            "Tool data gathered. "
                            "Now produce ONLY the final JSON verdict: "
                            '{"rating": "...", "confidence": N, "note": "..."}'
                        ),
                    }
                ]
            body = {
                "model":       model,
                "messages":    final_messages,
                "max_tokens":  max_tokens,
                "temperature": 0.65,
            }
            if include_tools:
                body["tools"]       = tools
                # Force at least one tool call on the opening round when asked
                # (used by the "re-analyze with tools" path); auto otherwise.
                body["tool_choice"] = "required" if (force_first and round_idx == 0) else "auto"
            elif tools_used:
                # Forced final round — include the tools schema with tool_choice="none"
                # so the model knows the signatures but is explicitly prevented from
                # calling them. Without this, reasoning models (e.g. GPT-OSS-20B) may
                # keep issuing tool_calls and the loop exhausts with empty content.
                body["tools"]       = tools
                body["tool_choice"] = "none"

            logger.debug(
                f"[GROQ-TOOLS] round={round_idx} model={model} "
                f"include_tools={include_tools} msgs={len(messages)}"
            )
            # Some Groq models reject tool params with a 400 (e.g. Qwen3-32B does
            # not support tool_choice="required", and reasoning models may reject
            # function calling entirely). Degrade gracefully so the analyst still
            # returns a real verdict instead of crashing to a Hold/25 fallback:
            #   required → auto → no tools.
            # 429 rate-limit: honour Retry-After (up to 20 s) and retry once.
            try:
                data = await self._post_groq_raw(body)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # ── 429 rate-limit: wait Retry-After (capped at 20 s) then retry ──
                if status == 429:
                    retry_after = 6.0
                    try:
                        m = re.search(r"try again in (\d+(?:\.\d+)?)s", exc.response.text)
                        if m:
                            retry_after = min(float(m.group(1)) + 0.5, 20.0)
                    except Exception as parse_exc:
                        logger.debug(
                            f"[GROQ-TOOLS] Could not parse Retry-After from 429 body "
                            f"({parse_exc!r}) — using default {retry_after:.1f}s backoff"
                        )
                    logger.warning(
                        f"[GROQ-TOOLS] {model} hit 429 rate-limit — "
                        f"sleeping {retry_after:.1f}s then retrying"
                    )
                    await asyncio.sleep(retry_after)
                    data = await self._post_groq_raw(body)  # re-raise on second 429
                elif status not in (400, 422):
                    raise
                elif "tools" not in body:
                    # 400 in the forced final (no-tools) round — the model tried to call a
                    # tool even without a tools schema ("Tool choice is none, but model
                    # called a tool"). Return empty so LAST-RESORT parser gives a fallback.
                    logger.warning(
                        f"[GROQ-TOOLS] {model} attempted tool call in no-tools round "
                        f"(400) — returning empty for LAST-RESORT fallback"
                    )
                    return "", tools_used
                else:
                    data = None
                    # Step 1: if we were forcing, try relaxing to tool_choice=auto.
                    if body.get("tool_choice") == "required":
                        logger.warning(
                            f"[GROQ-TOOLS] {model} rejected tool_choice=required "
                            f"({status}) — retrying with tool_choice=auto"
                        )
                        body["tool_choice"] = "auto"
                        try:
                            data = await self._post_groq_raw(body)
                        except httpx.HTTPStatusError as exc2:
                            if exc2.response.status_code not in (400, 422):
                                raise
                            data = None
                    # Step 2: still rejected (or model can't do tools at all) — drop them.
                    if data is None:
                        logger.warning(
                            f"[GROQ-TOOLS] {model} rejected tools (400) — "
                            f"retrying without tools (plain completion)"
                        )
                        body.pop("tools", None)
                        body.pop("tool_choice", None)
                        data = await self._post_groq_raw(body)
            msg  = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                content = (msg.get("content") or "").strip()
                # de-dupe preserving first-seen order
                seen: List[str] = []
                for t in tools_used:
                    if t not in seen:
                        seen.append(t)
                logger.info(
                    f"[GROQ-TOOLS] ✓ complete — model={model}, rounds={round_idx}, "
                    f"tools_used={seen}, response_chars={len(content)}"
                )
                return content, seen

            # Model requested tools — record the assistant turn, then dispatch each.
            messages.append({
                "role":       "assistant",
                "content":    msg.get("content") or "",
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "")
                try:
                    fn_args = json.loads(tc.get("function", {}).get("arguments") or "{}")
                    if not isinstance(fn_args, dict):
                        fn_args = {}
                except (json.JSONDecodeError, TypeError):
                    fn_args = {}
                logger.info(f"[GROQ-TOOLS] dispatch — {fn_name}({fn_args})")
                try:
                    result = await tool_dispatcher(fn_name, fn_args)
                except Exception as exc:   # tool failures are non-fatal
                    logger.warning(f"[GROQ-TOOLS] tool {fn_name} failed: {exc}")
                    result = json.dumps({"error": "tool unavailable"})
                tools_used.append(fn_name)
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.get("id", ""),
                    "name":         fn_name,
                    "content":      result if isinstance(result, str) else json.dumps(result),
                })

        # Fallback: loop exhausted without a final text answer (should not happen).
        seen = list(dict.fromkeys(tools_used))
        logger.warning(
            f"[GROQ-TOOLS] loop exhausted with no final content — model={model}, "
            f"tools_used={seen}"
        )
        return "", seen

    # ------------------------------------------------------------------
    # Internal: robust structured response parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_analyst_response(raw: str, persona_id: str = "?", model: str = "?") -> dict:
        import json

        logger.debug(
            f"[JURY/{persona_id}] _parse_analyst_response — "
            f"raw_chars={len(raw)}, "
            f"has_think_block={'yes' if '<think>' in raw else 'no'}"
        )

        # Strip reasoning-model thinking blocks (Qwen3 emits <think>...</think>)
        if "<think>" in raw:
            if "</think>" in raw:
                cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                logger.debug(
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
                    logger.debug(
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
                logger.debug(
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
        # Both JSON paths failed → the model emitted malformed/structurally-broken
        # output. Track it (keyed by model) so a chronically-misbehaving model is
        # visible in New Relic, then salvage a clean note without leaking JSON
        # punctuation (e.g. stray "}}" from an unbalanced object) into the UI.
        logger.warning(
            f"[JURY/{persona_id}] ⚠ Parse path: LAST-RESORT (regex plain-text extraction) — "
            f"both JSON parse paths failed (model={model}, raw_chars={len(raw)}, "
            f"had_think_block={'<think>' in raw})"
        )
        try:
            newrelic.agent.record_custom_event("JuryMalformedOutput", {
                "persona_id":      persona_id,
                "model":           model,
                "raw_chars":       len(raw),
                "had_think_block": "<think>" in raw,
            })
        except Exception:  # observability must never break parsing
            pass

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

        # Salvage the note: first try to lift the "note" field out of the broken
        # JSON; otherwise drop the JSON-ish span (greedy) and scrub any remaining
        # brace/bracket/quote so fragments like "}}" can never reach the user.
        note_match = re.search(r'"note"\s*:\s*"([^"]{1,420})"', cleaned, flags=re.DOTALL)
        if note_match:
            note = note_match.group(1).strip()
        else:
            note = re.sub(r"\{.*\}", " ", cleaned, flags=re.DOTALL)   # greedy: whole JSON blob
            note = re.sub(r"[{}\[\]\"]", " ", note)                   # any stray JSON punctuation
            note = re.sub(r"\s{2,}", " ", note).strip()
        note = note[:420] or "Quantitative analysis unavailable this run."

        result = {
            "rating":     rating,
            "note":       note,
            "confidence": min(max(confidence, 10), 95),
        }
        logger.debug(
            f"[JURY/{persona_id}] Last-resort result — "
            f"rating={result['rating']}, confidence={result['confidence']}"
        )
        return result

    # ------------------------------------------------------------------
    # Public: dispatch one persona and return a structured verdict
    # ------------------------------------------------------------------
    @newrelic.agent.function_trace()
    async def get_analyst_verdict(
        self,
        persona: dict,
        market_ctx: str,
        *,
        tools: Optional[List[dict]] = None,
        tool_dispatcher=None,
        force_tools: bool = False,
    ) -> dict:
        """
        Dispatches a single analyst persona to its assigned provider and model.
        All 3 personas use Groq. Provider field reserved for future expansion.
        Returns a fully structured verdict dict ready for the API response.

        When `tools` and `tool_dispatcher` are supplied, the analyst runs an
        agentic tool-using loop (Groq function calling) and the returned verdict
        carries a `tools_used` list naming the tools the model invoked.
        """
        use_tools   = bool(tools and tool_dispatcher)
        hint        = TOOL_PROMPT_HINT if use_tools else ""
        user_prompt = market_ctx + hint + NOTE_PROMPT_SUFFIX
        model_used  = persona["api_model"]
        max_tok     = persona.get("max_tokens", 320)
        raw         = ""
        tools_used: List[str] = []

        logger.info(
            f"[JURY/{persona['id']}] ── Dispatching — "
            f"provider={persona['provider']}, model={model_used}, "
            f"max_tokens={max_tok}, tools={'on' if use_tools else 'off'}, "
            f"title='{persona['title']}' ──"
        )
        logger.debug(
            f"[JURY/{persona['id']}] Context sent — "
            f"market_ctx_chars={len(market_ctx)}, total_prompt_chars={len(user_prompt)}"
        )

        try:
            if persona["provider"] == "groq":
                if use_tools:
                    max_rounds_model = persona.get("max_rounds", 2)
                    raw, tools_used = await self.call_groq_with_tools(
                        model_used, persona["system"], user_prompt,
                        tools, tool_dispatcher, max_tok,
                        force_first=force_tools,
                        max_rounds=max_rounds_model,
                    )
                else:
                    raw = await self._call_groq(model_used, persona["system"], user_prompt, max_tok)
            else:
                raise ValueError(f"Unknown provider: {persona['provider']}")

            logger.debug(
                f"[JURY/{persona['id']}] ✓ Raw response received — "
                f"model={model_used}, raw_chars={len(raw)}, tools_used={tools_used}"
            )

        except Exception as e:
            # Log the HTTP response body for easier diagnosis of 4xx/429 errors
            _body = ""
            if isinstance(e, httpx.HTTPStatusError):
                try:
                    _body = f" | response_body={e.response.text[:300]}"
                except Exception as body_err:
                    logger.debug(f"[JURY] Could not read response body for error logging: {body_err!r}")
                    _body = " | response_body=<unavailable>"
            logger.error(
                f"[JURY/{persona['id']}] ✗ FAILED — model={model_used}, error={e}{_body} | "
                f"FALLBACK: returning Hold/25 with persona-specific note"
            )
            # Use each persona's own fallback_note so the three cards stay visually
            # distinct even when a model is down — user can tell WHICH analyst failed
            # and what type of analysis is missing, rather than all three reading
            # identically as "Model unavailable — no verdict at this time."
            _fallback_note = persona.get(
                "fallback_note", "Model unavailable — no verdict at this time."
            )
            raw = (
                '{"rating": "Hold", '
                f'"note": {__import__("json").dumps(_fallback_note)}, '
                '"confidence": 25}'
            )
            model_used = "error"
            tools_used = []

        parsed = self._parse_analyst_response(raw, persona_id=persona["id"], model=model_used)

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
            "tools_used":  tools_used,
        }
        logger.info(
            f"[JURY/{persona['id']}] Final verdict — "
            f"rating={verdict['rating']}, confidence={verdict['confidence']}%, "
            f"model={verdict['model']}, note_chars={len(verdict['note'])}, "
            f"tools_used={tools_used}"
        )
        return verdict
