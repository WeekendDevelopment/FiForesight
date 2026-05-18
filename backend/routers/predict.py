# backend/routers/predict.py
import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import Config
from models import (
    calculate_rsi, calculate_rsi_series, run_ensemble_forecast,
    calculate_macd, calculate_bollinger_bands, calculate_sma_series,
    calculate_ema_series, calculate_support_resistance,
)
from services import DataCleaner, ANALYST_PERSONAS
from dependencies import (
    influx_svc, forecast_store, serp_svc, yf_svc,
    analyst_jury_svc, sentiment_svc, finnhub_svc, stocktwits_svc, yahoo_rss_svc,
)
from jury_graph import run_jury_graph
from redis_cache import cache_get, cache_set

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state for in-progress guard
# ---------------------------------------------------------------------------
_in_progress: set = set()
_in_progress_lock: asyncio.Lock = asyncio.Lock()


async def _resolve_with_lock(symbol: str) -> None:
    async with _in_progress_lock:
        if symbol in _in_progress:
            logger.info(f"[RL] resolve_past_forecasts already running for {symbol} — skipping duplicate")
            return
        _in_progress.add(symbol)
    try:
        await resolve_past_forecasts(symbol)
    finally:
        async with _in_progress_lock:
            _in_progress.discard(symbol)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class PredictRequest(BaseModel):
    data: str = "SPY"


class PredictionResponse(BaseModel):
    symbol:       str
    currentPrice: str
    rsi:          str
    prediction:   dict
    analystNote:  str
    confidence:   str
    history:      List[dict]
    forecastDays: List[dict]
    modelStats:   dict
    metrics:      dict
    news:         List[dict]
    trending:     List[dict]
    indicators:   dict
    lastUpdated:  str
    juryAnalysts:  List[dict]
    modelWeights:  dict
    sentiment:     dict
    stocktwits:      dict           = {}
    monteCarlo:      Optional[dict] = None
    earningsDates:   List[str]      = []
    moveExplanation: Optional[str]  = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_market_cap(cap) -> str:
    try:
        v = float(cap)
        if v >= 1e12:
            return f"${v/1e12:.2f}T"
        if v >= 1e9:
            return f"${v/1e9:.2f}B"
        if v >= 1e6:
            return f"${v/1e6:.2f}M"
        return f"${v:,.0f}"
    except Exception:
        return str(cap) if cap else "N/A"


def _fmt_pct(val) -> str:
    try:
        return f"{float(val)*100:.2f}%"
    except Exception:
        return "N/A"


def _fmt_ratio(val, decimals: int = 2, suffix: str = "") -> str:
    """Format a numeric ratio/multiple (beta, P/E, P/B, EV/EBITDA, etc.)."""
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except Exception:
        return "N/A"


def _dedup_news(items: List[dict]) -> List[dict]:
    """Deduplicate news items by lowercased title, preserving insertion order."""
    seen: set = set()
    out: List[dict] = []
    for item in items:
        key = item.get("title", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


async def _safe_fetch(coro, *, empty, name: str):
    """Await a coroutine with 12 s timeout; return empty on any failure."""
    try:
        return await asyncio.wait_for(coro, timeout=12.0)
    except Exception as e:
        logger.warning(f"[{name}] fetch failed or timed out: {e} — returning empty")
        return empty


def _safe_background(coro_or_future, *, name: str = "background"):
    """Wrap a coroutine in a task that logs exceptions instead of dropping them."""
    async def _wrapper():
        try:
            await coro_or_future
        except Exception as e:
            logger.error(f"[{name}] Background task failed: {e}", exc_info=True)
    return asyncio.create_task(_wrapper())


async def _ai_note(symbol: str, closes: List[float], rsi: float, forecast: dict) -> str:
    """
    Header analyst note via Groq llama-3.3-70b (14,400 RPD free, no quota issues).
    Replaces Gemini which has a 20 RPD free-tier limit — too scarce for per-request use.
    Falls back to the ensemble model's own note if Groq is unavailable.
    """
    recent    = closes[-20:]
    price_str = ", ".join(f"{p:.2f}" for p in recent)
    system = (
        "You are a concise quantitative financial analyst. "
        "Respond in 2 plain-text sentences only — no markdown, no bullet points, no JSON."
    )
    prompt = (
        f"Symbol: {symbol} | RSI: {rsi:.1f}\n"
        f"Recent 20-day closes: {price_str}\n"
        f"5-day ensemble forecast: high=${forecast['high']:.2f}, low=${forecast['low']:.2f} "
        f"[Confidence: {forecast.get('conf', 'low')}]\n"
        f"Write a concise 2-sentence analyst note covering the price outlook and the key risk."
    )
    logger.info(
        f"[AI-NOTE] Requesting header note — "
        f"model=llama-3.3-70b-versatile, symbol={symbol}, RSI={rsi:.1f}, "
        f"forecast_high=${forecast['high']:.2f}, forecast_low=${forecast['low']:.2f}, "
        f"conf={forecast.get('conf', 'low')} | "
        f"data_sent: last 20 closes of {len(closes)} total"
    )
    try:
        raw = await analyst_jury_svc._call_groq(
            "llama-3.3-70b-versatile", system, prompt
        )
        note = raw.strip()
        logger.info(
            f"[AI-NOTE] ✓ Header note received — {len(note)} chars | "
            f"ensemble note fallback SKIPPED"
        )
        return note
    except Exception as e:
        logger.warning(
            f"[AI-NOTE] ✗ Groq header note failed: {e} — "
            f"FALLBACK: using ensemble note ({len(forecast['note'])} chars)"
        )
        return forecast["note"]


async def _run_analyst_jury(
    symbol: str,
    closes: List[float],
    rsi: float,
    forecast: dict,
    stats: dict,
    info: dict,
    macd_data: dict,
    bb_data: dict,
    sma50: List,
    sma200: List,
    historical_prices: list,
    sr_levels: dict,
    *,
    news_task=None,
    news_headlines: Optional[List[str]] = None,
    track_record: str = "",
    sentiment: Optional[dict] = None,
    stocktwits: Optional[dict] = None,
) -> List[dict]:
    """
    Run all 3 analyst personas concurrently via AnalystJuryService.
      - KIMI-K2    → Groq moonshotai/kimi-k2-instruct  (macro & risk lens, Moonshot AI)
      - LLAMA-70B  → Groq llama-3.3-70b-versatile    (growth lens, Meta)
      - QWEN3-32B  → Groq qwen/qwen3-32b             (quant lens, Alibaba)

    All provider routing and response parsing are handled inside
    AnalystJuryService — no per-provider branching needed here.
    """

    # ------------------------------------------------------------------
    # Build shared market context string
    # ------------------------------------------------------------------

    def _last(series):
        """Last non-None value from a series."""
        for v in reversed(series):
            if v is not None:
                return v
        return None

    price     = closes[-1]
    recent    = closes[-10:]
    price_str = ", ".join(f"{p:.2f}" for p in recent)

    # Indicator snapshots
    cur_macd   = _last(macd_data["macd"])
    cur_signal = _last(macd_data["signal"])
    cur_hist   = _last(macd_data["hist"])
    cur_upper  = _last(bb_data["upper"])
    cur_middle = _last(bb_data["middle"])
    cur_lower  = _last(bb_data["lower"])
    cur_sma50  = _last(sma50)
    cur_sma200 = _last(sma200)

    # Derived labels
    macd_label = (
        ("Bullish" if cur_macd > cur_signal else "Bearish")
        if cur_macd is not None and cur_signal is not None else "N/A"
    )
    bb_pos_str = (
        f"{(price - cur_lower) / (cur_upper - cur_lower) * 100:.1f}% of band"
        if cur_upper and cur_lower and cur_upper != cur_lower else "N/A"
    )
    sma50_pct  = f"{(price - cur_sma50)  / cur_sma50  * 100:+.2f}%"  if cur_sma50  is not None else "N/A"
    sma200_pct = f"{(price - cur_sma200) / cur_sma200 * 100:+.2f}%"  if cur_sma200 is not None else "N/A"

    # Volume trend
    vols   = [float(p.get("volume", 0)) for p in historical_prices if p.get("volume", 0) > 0]
    vol10  = sum(vols[-10:]) / len(vols[-10:]) if len(vols) >= 10 else None
    vol30  = sum(vols[-30:]) / len(vols[-30:]) if len(vols) >= 30 else None
    vol_line = (
        f"10d avg {vol10/1e6:.2f}M vs 30d avg {vol30/1e6:.2f}M "
        f"({(vol10-vol30)/vol30*100:+.1f}%)"
        if vol10 and vol30 else "N/A"
    )

    # Support / resistance (top 2 each)
    sup_str = " / ".join(f"${v:.2f}" for v in sr_levels.get("support",    [])[:2]) or "N/A"
    res_str = " / ".join(f"${v:.2f}" for v in sr_levels.get("resistance", [])[:2]) or "N/A"

    # Fundamentals
    pe_str  = str(info.get("pe_ratio", "N/A"))
    cap_str = _fmt_market_cap(info.get("market_cap"))
    rng_str = info.get("range_52w", "N/A")
    sec_str = info.get("sector",    "N/A")
    div_str = (
        _fmt_pct(info.get("dividend_yield"))
        if info.get("dividend_yield") not in (None, "N/A") else "N/A"
    )

    # News headlines — prefer pre-resolved list, fall back to opportunistic task check
    news_block = ""
    if news_headlines:
        lines = [f"  - {h}" for h in news_headlines[:4]]
        news_block = "Recent news:\n" + "\n".join(lines) + "\n"
    elif news_task is not None and news_task.done() and not news_task.cancelled():
        try:
            raw_headlines = news_task.result().get("news_results", [])[:4]
            if raw_headlines:
                lines = []
                for h in raw_headlines:
                    src = (
                        h.get("source", {}).get("name", "")
                        if isinstance(h.get("source"), dict)
                        else str(h.get("source", ""))
                    )
                    lines.append(f"  - {h.get('title', '')} [{src}]")
                news_block = "Recent news:\n" + "\n".join(lines) + "\n"
        except Exception:
            logging.debug("Failed to build opportunistic news block", exc_info=True)

    # Formatted indicator lines
    macd_line = (
        f"MACD: {cur_macd:.4f} | Signal: {cur_signal:.4f} | Hist: {cur_hist:.4f} [{macd_label}]"
        if cur_macd is not None and cur_signal is not None and cur_hist is not None
        else "MACD: N/A"
    )
    bb_line = (
        f"BB: Upper={cur_upper:.2f} Mid={cur_middle:.2f} Lower={cur_lower:.2f} | Price: {bb_pos_str}"
        if cur_upper is not None else "BB: N/A"
    )
    # Each arm is only formatted if its value actually exists
    sma50_str  = f"SMA50: {cur_sma50:.2f} ({sma50_pct})"    if cur_sma50  is not None else "SMA50: N/A"
    sma200_str = f"SMA200: {cur_sma200:.2f} ({sma200_pct})" if cur_sma200 is not None else "SMA200: N/A"
    sma_line   = f"{sma50_str} | {sma200_str}"


    sentiment_line = ""
    if sentiment and sentiment.get("headline_count", 0) > 0:
        st_suffix = ""
        if stocktwits:
            total_st = stocktwits.get("bullish", 0) + stocktwits.get("bearish", 0)
            if total_st > 0:
                st_suffix = (
                    f" | StockTwits: {stocktwits['bullish']}B / {stocktwits['bearish']}Be "
                    f"(ratio={stocktwits['sentiment']:+.2f})"
                )
        sentiment_line = (
            f"News Sentiment (VADER, {sentiment['headline_count']} headlines): "
            f"compound={sentiment['compound']:+.3f} [{sentiment['label']}]"
            f"{st_suffix}\n"
        )

    _mc = forecast.get("monte_carlo")
    mc_line = (
        f"Monte Carlo (1000 sims, 5d): "
        f"prob_gain={_mc['prob_gain']:.1f}%, VaR95=${_mc['var_95']:.2f}\n"
    ) if _mc else ""

    ctx = (
        f"Symbol: {symbol} | Price: ${price:.2f} | RSI: {rsi:.1f} | Sector: {sec_str}\n"
        f"Fundamentals: PE={pe_str} | Cap={cap_str} | Div={div_str} | 52w={rng_str}\n"
        f"10-day closes: {price_str}\n"
        f"Forecast 5d → High: ${forecast['high']:.2f}, Low: ${forecast['low']:.2f} "
        f"[Confidence: {forecast.get('conf', 'low')}]\n"
        f"{mc_line}"
        f"Volatility: {stats.get('ann_volatility_pct', 0):.1f}% ann | "
        f"Slope: {stats.get('trend_slope', 0):.4f}/day | "
        f"vs SMA20: {stats.get('price_vs_sma20_pct', 0):+.2f}%\n"
        f"{macd_line}\n"
        f"{bb_line}\n"
        f"{sma_line}\n"
        f"Volume: {vol_line}\n"
        f"Support: {sup_str} | Resistance: {res_str}\n"
        f"{sentiment_line}"
        f"{news_block}"
        + (f"{track_record}\n" if track_record else "")
    )

    # ------------------------------------------------------------------
    # Dispatch all personas via LangGraph jury graph (parallel fan-out).
    # Each analyst is an independent node; failures are isolated per-node.
    # Swap .ainvoke() → .stream() here in future for SSE streaming.
    # ------------------------------------------------------------------
    try:
        return await run_jury_graph(analyst_jury_svc, ANALYST_PERSONAS, ctx)
    except Exception as exc:
        logger.error("[JURY-GRAPH] invocation failed: %s", exc, exc_info=True)
        return [
            {
                "id":          persona["id"],
                "avatar":      persona["avatar"],
                "title":       persona["title"],
                "model_label": persona["model_label"],
                "color":       persona["color"],
                "rating":      "Hold",
                "note":        "Analysis unavailable.",
                "confidence":  25,
                "model":       "error",
            }
            for persona in ANALYST_PERSONAS
        ]


# ---------------------------------------------------------------------------
# RL feedback: resolve past forecasts against actual closes
# ---------------------------------------------------------------------------

async def resolve_past_forecasts(symbol: str) -> None:
    """
    Background task — matches forecast records against actual market closes,
    then writes/updates model_accuracy in InfluxDB.

    Runs once per /predict request (non-blocking, fire-and-forget).
    """
    try:
        logger.debug(f"[RL] resolve_past_forecasts — starting for {symbol}")

        records = await asyncio.to_thread(
            forecast_store.query_forecast_records, symbol, 10
        )
        if not records:
            logger.info(f"[RL] No forecast records to resolve for {symbol}")
            return

        existing_outcomes = await asyncio.to_thread(
            forecast_store.query_price_outcomes, symbol, 15
        )

        # Resolution markers prevent double-applying errors under concurrent
        # /predict calls (each call spawns resolve_past_forecasts as a task).
        resolved_set = await asyncio.to_thread(
            forecast_store.query_resolved_timestamps, symbol, 30
        )

        # Fetch 30d yfinance history → build date → actual_close map
        df = await asyncio.to_thread(yf_svc.fetch_history, symbol, "30d")
        actual_map: Dict[date, float] = {}
        if not df.empty:
            for ts, row in df.iterrows():
                actual_map[ts.date()] = float(
                    row.get("Close", row.get("close", 0)) or 0
                )

        # Merge already-stored outcomes (takes precedence)
        actual_map.update(existing_outcomes)

        now_date = datetime.now(timezone.utc).date()
        new_outcomes: list = []
        errors_per_model: dict = {"prophet": [], "sarima": [], "rf": []}
        # Per-horizon ensemble errors: ensemble_d1 … ensemble_d5
        errors_per_horizon: dict = {f"ensemble_d{i}": [] for i in range(1, 6)}
        band_hits: list = []  # 1=actual inside [low,high], 0=missed

        def nth_market_day(base_date: date, n: int) -> date:
            """
            Return the n-th actual trading day after base_date, determined by
            actual_map (yfinance data) so holidays are excluded automatically.
            Falls back to weekday-skip logic if actual_map lacks enough data.
            """
            d = base_date
            hops = 0
            for _ in range(20):  # safety: never loop more than 20 calendar days
                d += timedelta(days=1)
                if d in actual_map and actual_map[d] > 0:
                    hops += 1
                    if hops == n:
                        return d
            # Fallback: weekday-based (handles edge case where actual_map is sparse)
            d = base_date
            hops = 0
            while hops < n:
                d += timedelta(days=1)
                while d.weekday() >= 5:
                    d += timedelta(days=1)
                hops += 1
            return d

        def resolve_actual(target_date: date) -> Optional[float]:
            """
            Return actual close for target_date, or None.
            Searches forward up to 3 calendar days for the first entry in
            actual_map with a positive price (handles remaining holiday gaps).
            """
            d = target_date
            for _ in range(4):
                if d in actual_map and actual_map[d] > 0:
                    return actual_map[d]
                d += timedelta(days=1)
            return None

        # resolved_set: {pred_time -> max_horizon_resolved} (0 = not started)
        newly_resolved: dict = {}  # {pred_time: max_horizon} for this pass
        for rec in records:
            pred_time = rec.get("_time")
            if pred_time is None:
                continue
            # Skip records where all 5 horizons are already resolved
            max_resolved = resolved_set.get(pred_time, 0)
            if max_resolved >= 5:
                continue
            pred_date = pred_time.date()

            # ── d1: per-model errors + price_outcome (first time only) ────────
            target_d1 = nth_market_day(pred_date, 1)
            if target_d1 > now_date:
                continue  # d1 close not available yet

            actual_d1 = resolve_actual(target_d1)
            if actual_d1 is None:
                continue

            if max_resolved < 1:
                # Write price_outcome once per record
                if target_d1 not in existing_outcomes:
                    outcome_dt = datetime(
                        target_d1.year, target_d1.month, target_d1.day,
                        tzinfo=timezone.utc
                    )
                    new_outcomes.append((outcome_dt, actual_d1))

                # Per-model d1 errors (only on first pass)
                for model_name, field_key in [
                    ("prophet", "p_d1"),
                    ("sarima",  "s_d1"),
                    ("rf",      "r_d1"),
                ]:
                    pred_val = float(rec.get(field_key, 0) or 0)
                    if pred_val > 0:
                        err = abs(pred_val - actual_d1)
                        errors_per_model[model_name].append(err)
                        logger.debug(
                            f"[RL] {symbol}/{model_name}: pred={pred_val:.2f}, "
                            f"actual={actual_d1:.2f}, err={err:.4f} ({target_d1})"
                        )

                # Band accuracy check (once per record)
                e_d1_high = float(rec.get("e_d1_high", 0) or 0)
                e_d1_low  = float(rec.get("e_d1_low",  0) or 0)
                if e_d1_high > 0 and e_d1_low > 0:
                    hit = 1 if e_d1_low <= actual_d1 <= e_d1_high else 0
                    band_hits.append(hit)
                    logger.debug(
                        f"[RL] {symbol} band check: actual=${actual_d1:.2f} "
                        f"vs [{e_d1_low:.2f}-{e_d1_high:.2f}] → {'HIT' if hit else 'MISS'}"
                    )

            # ── d1-d5 ensemble horizon resolution (resume from last resolved) ─
            for horizon in range(max(max_resolved, 0) + 1, 6):
                target_dn = nth_market_day(pred_date, horizon)
                if target_dn > now_date:
                    break  # this and later horizons not yet closed
                field_key = f"e_d{horizon}"
                pred_val  = float(rec.get(field_key, 0) or 0)
                if pred_val <= 0:
                    newly_resolved[pred_time] = max(newly_resolved.get(pred_time, 0), horizon)
                    continue
                actual_dn = resolve_actual(target_dn)
                if actual_dn is None:
                    break  # can't find data — stop this record for now
                err = abs(pred_val - actual_dn)
                errors_per_horizon[f"ensemble_d{horizon}"].append(err)
                logger.debug(
                    f"[RL] {symbol}/ensemble_d{horizon}: pred={pred_val:.2f}, "
                    f"actual={actual_dn:.2f}, err={err:.4f} ({target_dn})"
                )
                newly_resolved[pred_time] = max(newly_resolved.get(pred_time, 0), horizon)

        # Persist new outcomes
        for outcome_dt, actual_close in new_outcomes:
            await asyncio.to_thread(
                forecast_store.write_price_outcome, symbol, outcome_dt, actual_close
            )

        # Update per-model accuracy (exponential decay MAE) BEFORE persisting
        # resolution markers.  If an accuracy write fails the markers are never
        # advanced, so the next cron pass can safely retry from scratch.
        # Decay=0.85 means recent errors count ~6× more than 10-day-old errors.
        existing_acc = await asyncio.to_thread(
            forecast_store.query_model_accuracy, symbol
        )
        ema_decay = 0.85

        def _apply_ema(prev: Dict[str, float], errs: List[float]) -> Tuple[float, int]:
            prev_n   = prev.get("samples", 0)
            prev_mae = prev.get("mae", 0.0)
            cur_mae, cur_n = prev_mae, prev_n
            for err in errs:
                cur_mae = err if cur_n == 0 else ema_decay * cur_mae + (1.0 - ema_decay) * err
                cur_n += 1
            return cur_mae, cur_n

        # all_accuracy_ok gates mark_forecast_resolved: if any write_model_accuracy
        # call returns False the markers are not advanced so the next cron pass
        # retries all accuracy writes from scratch (idempotent EMA replay).
        all_accuracy_ok = True

        for model_name, errs in errors_per_model.items():
            if not errs:
                continue
            cur_mae, cur_n = _apply_ema(existing_acc.get(model_name, {}), errs)
            ok = await asyncio.to_thread(
                forecast_store.write_model_accuracy, symbol, model_name, cur_mae, cur_n
            )
            if ok:
                logger.info(
                    f"[RL] {symbol}/{model_name} MAE → ${cur_mae:.3f} (n={cur_n})"
                )
            else:
                logger.warning(
                    f"[RL] {symbol}/{model_name} accuracy write failed — "
                    "resolution markers will not be advanced this pass"
                )
                all_accuracy_ok = False

        # Update per-horizon ensemble accuracy
        existing_ens = await asyncio.to_thread(
            forecast_store.query_ensemble_mae, symbol
        )
        for horizon_key, errs in errors_per_horizon.items():
            if not errs:
                continue
            cur_mae, cur_n = _apply_ema(existing_ens.get(horizon_key, {}), errs)
            ok = await asyncio.to_thread(
                forecast_store.write_model_accuracy, symbol, horizon_key, cur_mae, cur_n
            )
            if ok:
                logger.info(
                    f"[RL] {symbol}/{horizon_key} MAE → ${cur_mae:.3f} (n={cur_n})"
                )
            else:
                logger.warning(
                    f"[RL] {symbol}/{horizon_key} accuracy write failed — "
                    "resolution markers will not be advanced this pass"
                )
                all_accuracy_ok = False

        # Advance resolution markers only when every accuracy write succeeded.
        # mark_forecast_resolved is idempotent (same timestamp+tag overwrites in
        # InfluxDB), so a future retry is safe.
        if all_accuracy_ok:
            for rt, max_h in newly_resolved.items():
                await asyncio.to_thread(
                    forecast_store.mark_forecast_resolved, symbol, rt, max_h
                )
        else:
            logger.warning(
                f"[RL] {symbol}: skipping {len(newly_resolved)} resolution marker(s) "
                "due to accuracy write failure(s) — will retry on next pass"
            )

        band_pct = (
            f"{sum(band_hits)/len(band_hits)*100:.0f}% ({sum(band_hits)}/{len(band_hits)})"
            if band_hits else "no data yet"
        )
        ens_summary = ", ".join(
            f"d{i}={len(errors_per_horizon[f'ensemble_d{i}'])}err"
            for i in range(1, 6)
            if errors_per_horizon[f"ensemble_d{i}"]
        ) or "none"
        logger.info(
            f"[RL] ✓ resolve_past_forecasts complete — {symbol}: "
            f"{len(new_outcomes)} new outcomes | {len(newly_resolved)} records advanced | "
            + ", ".join(f"{m}={len(e)}err" for m, e in errors_per_model.items())
            + f" | ensemble horizons: {ens_summary}"
            + f" | band hit rate: {band_pct}"
        )

    except Exception as e:
        logger.warning(
            f"[RL] resolve_past_forecasts failed for {symbol}: {e}", exc_info=True
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/sparklines")
async def sparklines(tickers: str):
    """Return last-5-close prices for a comma-separated list of tickers."""
    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()][:18]
    result: Dict[str, List[float]] = {}
    for sym in symbols:
        try:
            closes = await asyncio.to_thread(yf_svc.fetch_history, sym, "7d")
            if closes is not None and not closes.empty:
                vals = closes["Close"].dropna().tolist()[-5:]
                result[sym] = [round(float(v), 2) for v in vals]
        except Exception as e:
            logger.warning("[sparklines] %s fetch failed: %s", sym, e, exc_info=True)
    return result


@router.get("/debug")
async def debug():
    """Checks every service dependency — hit this in the browser to diagnose 500s."""
    from models import MODELS_AVAILABLE
    from services import YFINANCE_AVAILABLE

    results: dict = {
        "yfinance_installed":   YFINANCE_AVAILABLE,
        "ml_models_available":  MODELS_AVAILABLE,
        "serp_api_key_set":     bool(Config.SERP_API_KEY),
        "groq_key_set":         bool(Config.GROQ_API_KEY),
        "influxdb_token_set":   bool(Config.INFLUXDB_TOKEN),
    }

    # Test InfluxDB connectivity
    try:
        await asyncio.to_thread(influx_svc.has_recent_data, "DEBUG_TEST")
        results["influxdb_reachable"] = True
    except Exception as e:
        results["influxdb_reachable"] = False
        results["influxdb_error"]     = str(e)

    # Test yfinance (quick 5-day fetch)
    if YFINANCE_AVAILABLE:
        try:
            import yfinance as _yf
            df = await asyncio.to_thread(
                lambda: _yf.download(
                    "AAPL", period="5d", interval="1d",
                    progress=False, auto_adjust=True, timeout=10,
                )
            )
            results["yfinance_reachable"] = not df.empty
            results["yfinance_rows"]      = int(len(df))
        except Exception as e:
            results["yfinance_reachable"] = False
            results["yfinance_error"]     = str(e)

    return results


async def _predict_inner(payload: PredictRequest) -> PredictionResponse:
    import numpy as np

    symbol = payload.data.upper()
    now    = datetime.now(timezone.utc)

    logger.info("[REQUEST] ════════════════════════════════════════════")
    logger.info(f"[REQUEST] /predict → symbol={symbol} | {now.isoformat()}")
    logger.info("[REQUEST] ════════════════════════════════════════════")

    # ── Step 1. Fetch OHLCV history ───────────────────────────────────────────
    # FIX (Issue 4): yfinance is always the primary historical source.
    # InfluxDB Cloud has a 29-day retention window — it cannot hold 2y of data.
    # query_history(365d) was returning only ~21 rows, always triggering the
    # yfinance fallback anyway (double-fetch every request). Now:
    #   • yfinance 2y fetch runs once unconditionally (models need 500+ rows)
    #   • has_recent_data() guards the InfluxDB write — skip if already fresh
    #     (avoids redundant batch writes on repeated requests within 20h)
    #   • InfluxDB write_ohlcv_batch writes the last 29d for downstream analytics
    #   • InfluxDB write_price (Step 7) still tracks intraday live-price history
    # Steps 1 + 3 in parallel — fetch_info is skipped if cached in Redis (1h TTL).
    info_cache_key = f"info:{symbol.upper()}"
    cached_info    = await cache_get(info_cache_key)

    if cached_info is not None:
        logger.info(f"[STEP-1+3] fetch_info cache HIT for {symbol} — fetching history only")
        df_result = await asyncio.to_thread(yf_svc.fetch_history, symbol, "2y")
        df         = df_result
        info: dict = cached_info
    else:
        logger.info("[STEP-1+3] fetch_info cache MISS — fetching history + fundamentals concurrently ...")
        _gather_results = await asyncio.gather(
            asyncio.to_thread(yf_svc.fetch_history, symbol, "2y"),
            asyncio.to_thread(yf_svc.fetch_info, symbol),
            return_exceptions=True,
        )
        df         = _gather_results[0]
        _info_result = _gather_results[1]
        if isinstance(_info_result, Exception):
            logger.error(f"[STEP-3] fetch_info failed for {symbol}: {_info_result} — using empty fundamentals")
            info = {}
        else:
            info = _info_result
            if info:
                await cache_set(info_cache_key, info, ttl_seconds=3600)
                logger.info(f"[STEP-3] fetch_info cached for {symbol} (TTL=1h)")

    if isinstance(df, Exception):
        logger.error(f"[STEP-1] fetch_history failed for {symbol}: {df}")
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}.")

    if df.empty:
        logger.error(f"[STEP-1] yfinance returned empty df for {symbol} — returning 404")
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}.")

    try:
        df = DataCleaner.clean(df)
    except Exception as e:
        logger.warning(f"[STEP-1] DataCleaner.clean failed for {symbol}: {e} — using raw df")

    if df.empty:
        logger.error(f"[STEP-1] DataCleaner returned empty df for {symbol} — returning 404")
        raise HTTPException(status_code=404, detail=f"No usable data for {symbol} after cleaning.")

    historical_prices: list = DataCleaner.to_history_list(df)
    logger.info(
        f"[STEP-1] ✓ yfinance fetch complete — {len(historical_prices)} rows | "
        f"range: {str(historical_prices[0]['_time'])[:10]} → "
        f"{str(historical_prices[-1]['_time'])[:10]} | "
        f"close: ${historical_prices[0]['close']:.2f} → ${historical_prices[-1]['close']:.2f}"
    )

    # Cache recent rows to InfluxDB (last 29d) for downstream analytics
    logger.debug(f"[STEP-1] [INFLUXDB] Checking cache freshness for {symbol} ...")
    has_fresh = await asyncio.to_thread(influx_svc.has_recent_data, symbol)
    if not has_fresh:
        logger.debug(
            "[STEP-1] [INFLUXDB] Cache MISS — "
            "writing last 29d rows to InfluxDB for analytics ..."
        )
        await asyncio.to_thread(influx_svc.write_ohlcv_batch, symbol, df)
    else:
        logger.debug(
            "[STEP-1] [INFLUXDB] Cache HIT — "
            "InfluxDB write SKIPPED (fresh data already present)"
        )

    historical_prices.sort(key=lambda x: x["_time"])

    # ── Step 2. Live price ────────────────────────────────────────────────────
    logger.debug(f"[STEP-2] Fetching live price for {symbol} ...")
    live_price = await asyncio.to_thread(yf_svc.get_live_price, symbol)
    if live_price > 0:
        # If yfinance already returned today's (partial) bar, replace its close
        # with the live price instead of appending a duplicate — otherwise the
        # chart sees two bars with the same date and lightweight-charts fails
        # its strict-ascending assertion.
        last_time: Optional[Any]       = historical_prices[-1]["_time"] if historical_prices else None
        last_date: Optional[date]      = last_time.date() if hasattr(last_time, "date") else None
        if last_date == now.date():
            last_bar: Dict[str, Any]   = historical_prices[-1]
            last_bar["close"] = live_price
            last_bar["high"]  = max(float(last_bar.get("high", live_price)), live_price)
            last_bar["low"]   = min(float(last_bar.get("low",  live_price)), live_price)
            logger.info(
                f"[STEP-2] ✓ Live price ${live_price:.2f} merged into today's "
                f"existing bar (total bars: {len(historical_prices)})"
            )
        else:
            historical_prices.append({
                "_time": now, "close": live_price,
                "open":  live_price, "high": live_price,
                "low":   live_price, "volume": 0.0,
            })
            logger.info(
                f"[STEP-2] ✓ Live price ${live_price:.2f} injected as latest bar "
                f"(total bars now: {len(historical_prices)})"
            )
    else:
        live_price = float(historical_prices[-1]["close"])
        logger.info(
            f"[STEP-2] Live price unavailable — "
            f"using last historical close: ${live_price:.2f}"
        )

    # ── Step 3. Fundamentals (info already fetched concurrently at Step 1+3) ──
    metrics = {
        "market_cap":     _fmt_market_cap(info.get("market_cap")),
        "pe_ratio":       str(info.get("pe_ratio", "N/A")),
        "yield":          _fmt_pct(info.get("dividend_yield")) if info.get("dividend_yield") not in (None, "N/A") else "N/A",
        "prev_close":     str(info.get("prev_close", "N/A")),
        "range_52w":      info.get("range_52w",  "N/A"),
        "sector":         info.get("sector",     "N/A"),
        "industry":       info.get("industry",   "N/A"),
        "currency":       info.get("currency",   "USD"),
        # Extended quant fundamentals
        "beta":           _fmt_ratio(info.get("beta"))          if info.get("beta")          not in (None, "N/A") else "N/A",
        "forward_pe":     _fmt_ratio(info.get("forward_pe"))    if info.get("forward_pe")    not in (None, "N/A") else "N/A",
        "peg_ratio":      _fmt_ratio(info.get("peg_ratio"))     if info.get("peg_ratio")     not in (None, "N/A") else "N/A",
        "price_to_book":  _fmt_ratio(info.get("price_to_book")) if info.get("price_to_book") not in (None, "N/A") else "N/A",
        "ev_to_ebitda":   _fmt_ratio(info.get("ev_to_ebitda"))  if info.get("ev_to_ebitda")  not in (None, "N/A") else "N/A",
        "free_cash_flow": _fmt_market_cap(info.get("free_cash_flow")) if info.get("free_cash_flow") not in (None, "N/A") else "N/A",
        "revenue_growth": _fmt_pct(info.get("revenue_growth"))  if info.get("revenue_growth") not in (None, "N/A") else "N/A",
        "total_debt":     _fmt_market_cap(info.get("total_debt"))     if info.get("total_debt")     not in (None, "N/A") else "N/A",
    }
    logger.info(
        f"[STEP-3] ✓ Fundamentals — sector={metrics['sector']}, industry={metrics['industry']}, "
        f"market_cap={metrics['market_cap']}, pe={metrics['pe_ratio']}, fwd_pe={metrics['forward_pe']}, "
        f"peg={metrics['peg_ratio']}, beta={metrics['beta']}, ev/ebitda={metrics['ev_to_ebitda']}, "
        f"fcf={metrics['free_cash_flow']}, rev_growth={metrics['revenue_growth']}"
    )

    # ── Step 4. Analytics & ensemble forecast ────────────────────────────────
    # FIX (Issue 3): extract full OHLCV arrays — all are now passed to models
    # so Prophet/SARIMAX/RF can use volume and intraday range as additional context.
    closes  = [float(p["close"])              for p in historical_prices]
    opens   = [float(p.get("open",  p["close"])) for p in historical_prices]
    highs   = [float(p.get("high",  p["close"])) for p in historical_prices]
    lows    = [float(p.get("low",   p["close"])) for p in historical_prices]

    # Replace zero-volume rows (e.g. live-price injection) with rolling mean
    # so the synthetic bar doesn't skew normalisation inside the models.
    volumes_raw  = [float(p.get("volume", 0)) for p in historical_prices]
    nonzero_vols = [v for v in volumes_raw if v > 0]
    vol_fill     = float(np.mean(nonzero_vols)) if nonzero_vols else 1.0
    volumes      = [v if v > 0 else vol_fill for v in volumes_raw]

    zero_vol_count = sum(1 for v in volumes_raw if v == 0)
    logger.debug(
        f"[STEP-4] OHLCV arrays built — {len(closes)} rows | "
        f"zero-volume rows filled with mean ({zero_vol_count} filled, mean_vol={vol_fill:.0f}) | "
        f"last OHLCV: O=${opens[-1]:.2f} H=${highs[-1]:.2f} "
        f"L=${lows[-1]:.2f} C=${closes[-1]:.2f} V={volumes[-1]:.0f}"
    )

    # ── RL: load historical model accuracy for weight calibration ────────────
    logger.debug(f"[RL] Querying historical model accuracy for {symbol} ...")
    model_acc = await asyncio.to_thread(forecast_store.query_model_accuracy, symbol)
    ensemble_mae = await asyncio.to_thread(forecast_store.query_ensemble_mae, symbol)

    historical_weights = None
    rl_sample_count    = 0
    track_record       = ""

    if model_acc:
        p_acc = model_acc.get("prophet", {})
        s_acc = model_acc.get("sarima",  {})
        r_acc = model_acc.get("rf",      {})
        min_samples = min(
            p_acc.get("samples", 0),
            s_acc.get("samples", 0),
            r_acc.get("samples", 0),
        )
        rl_sample_count = min_samples
        if rl_sample_count > 0:
            eps      = 1e-6
            inv_maes = [
                1.0 / (p_acc.get("mae", 999.0) + eps),
                1.0 / (s_acc.get("mae", 999.0) + eps),
                1.0 / (r_acc.get("mae", 999.0) + eps),
            ]
            total_inv          = sum(inv_maes)
            historical_weights = [v / total_inv for v in inv_maes] if total_inv > 0 else None
            logger.debug(
                f"[RL] Historical weights (inv-MAE) — "
                f"prophet={historical_weights[0]:.3f}, "
                f"sarima={historical_weights[1]:.3f}, "
                f"rf={historical_weights[2]:.3f} | samples={rl_sample_count}"
            )
        # Build track record string for analyst jury context
        parts = []
        for label, acc in [("Prophet", p_acc), ("SARIMA", s_acc), ("RF", r_acc)]:
            n = acc.get("samples", 0)
            if n > 0:
                parts.append(f"{label} d1_MAE=${acc['mae']:.2f} (n={n})")
        if parts:
            track_record = "Model track record: " + " | ".join(parts)
            logger.debug(f"[RL] Track record for jury: {track_record}")

    rsi = calculate_rsi(closes)
    logger.debug(f"[STEP-4] RSI scalar computed: {rsi:.2f}")

    logger.info(
        "[STEP-4] Running ensemble forecast (Prophet + SARIMAX + RF) "
        "with full OHLCV context ..."
        + (f" | RL blending active ({rl_sample_count} samples)" if rl_sample_count > 0 else "")
    )
    forecast = await asyncio.to_thread(
        run_ensemble_forecast,
        closes, symbol,
        opens=opens, highs=highs, lows=lows, volumes=volumes,
        historical_weights=historical_weights,
        sample_count=rl_sample_count,
        ensemble_mae=ensemble_mae,
    )

    # ── RL: record this forecast + resolve old ones (background) ─────────────
    fweights    = forecast.get("weights",      {"prophet": 0.0, "sarima": 0.0, "rf": 0.0})
    per_model   = forecast.get("per_model_d1", {"prophet": None, "sarima": None, "rf": None})
    forecast_days = forecast.get("forecast_days", [])
    ensemble_d1_preds = [d["predicted"] for d in forecast_days]
    d1_high = forecast_days[0]["high"] if forecast_days else None
    d1_low  = forecast_days[0]["low"]  if forecast_days else None
    _safe_background(asyncio.to_thread(
        forecast_store.write_forecast_record,
        symbol,
        float(closes[-1]),
        per_model.get("prophet"),
        per_model.get("sarima"),
        per_model.get("rf"),
        fweights.get("prophet", 0.0),
        fweights.get("sarima",  0.0),
        fweights.get("rf",      0.0),
        ensemble_d1_preds,
        d1_high,
        d1_low,
    ), name="RL-WRITE")
    _safe_background(_resolve_with_lock(symbol), name="RL-RESOLVE")

    # ── Step 4b. Technical indicators (close-based — correct by definition) ──
    logger.debug(
        "[STEP-4b] Computing technical indicators — "
        "MACD(12,26,9), BB(window=20, std=2), SMA50, SMA200, EMA20, EMA50 ..."
    )
    macd_data = calculate_macd(closes)
    bb_data   = calculate_bollinger_bands(closes)
    sma50     = calculate_sma_series(closes, 50)
    sma200    = calculate_sma_series(closes, 200)
    ema20     = calculate_ema_series(closes, 20)
    ema50     = calculate_ema_series(closes, 50)
    logger.info(f"[STEP-4b] ✓ All indicator series computed ({len(closes)} points each)")

    # ── Step 4c. Fire news + earnings fetch concurrently ─────────────────────
    news_cache_key = f"news:{symbol.upper()}"
    cached_news_payload = await cache_get(news_cache_key)
    if cached_news_payload is not None:
        logger.info(f"[STEP-4c] News cache HIT for {symbol}")
    else:
        logger.info(
            "[STEP-4c] News cache MISS — launching SerpAPI, yfinance news, "
            "Finnhub, and StockTwits tasks"
        )
        serp_task = asyncio.create_task(serp_svc.fetch_data(symbol))
        yf_news_task = asyncio.create_task(
            _safe_fetch(
                asyncio.to_thread(yf_svc.fetch_news, symbol),
                empty=[], name="YF-NEWS",
            )
        )
        finnhub_task = asyncio.create_task(
            _safe_fetch(finnhub_svc.fetch_company_news(symbol), empty=[], name="FINNHUB")
        )
        yahoo_rss_task = asyncio.create_task(
            _safe_fetch(yahoo_rss_svc.fetch_news(symbol), empty=[], name="YAHOORSE")
        )
        stocktwits_task = asyncio.create_task(
            _safe_fetch(
                stocktwits_svc.fetch_sentiment(symbol),
                empty={"bullish": 0, "bearish": 0, "sentiment": 0.0},
                name="STOCKTWITS",
            )
        )

    earnings_task = asyncio.create_task(
        asyncio.to_thread(yf_svc.fetch_earnings_dates, symbol)
    )

    # ── Support/resistance — now uses intraday highs/lows ────────────────────
    logger.debug(
        "[STEP-4d] Computing support/resistance levels "
        "(using intraday High/Low extrema) ..."
    )
    sr_levels = calculate_support_resistance(closes, highs=highs, lows=lows)

    # ── Step 4e. Resolve news + score VADER sentiment ─────────────────────────
    news: list           = []
    trending: list       = []
    sentiment: dict      = {"compound": 0.0, "label": "Neutral", "scores": [], "headline_count": 0}
    stocktwits_data: dict = {"bullish": 0, "bearish": 0, "sentiment": 0.0}

    if cached_news_payload is not None:
        news           = cached_news_payload.get("news", [])
        trending       = cached_news_payload.get("trending", [])
        sentiment      = cached_news_payload.get("sentiment", {"compound": 0.0, "label": "Neutral", "headline_count": 0})
        stocktwits_data = cached_news_payload.get("stocktwits", {"bullish": 0, "bearish": 0, "sentiment": 0.0})
        logger.info(f"[STEP-4e] Using cached news/sentiment/stocktwits for {symbol}")
    else:
        logger.info("[STEP-4e] Awaiting SerpAPI, yfinance news, Finnhub, StockTwits ...")
        serp_data: dict = {"news_results": [], "markets": {}}
        try:
            serp_data = await serp_task
            serp_news = [
                {
                    "title":        n.get("title",  ""),
                    "link":         n.get("link",   ""),
                    "source":       (
                        n.get("source", {}).get("name", "")
                        if isinstance(n.get("source"), dict)
                        else str(n.get("source", ""))
                    ),
                    "thumbnail":    n.get("thumbnail", ""),
                    "date":         n.get("date",   ""),
                    "source_label": "SerpAPI",
                }
                for n in serp_data.get("news_results", [])[:8]
            ]
            for category, items in serp_data.get("markets", {}).items():
                if isinstance(items, list):
                    for t in items[:3]:
                        trending.append({
                            "symbol":   t.get("symbol") or t.get("name", "N/A"),
                            "name":     t.get("name",  ""),
                            "price":    str(t.get("price", "N/A")),
                            "change":   str(t.get("price_change_percentage", "0%")),
                            "category": category,
                        })
            logger.info(
                f"[STEP-4e] ✓ SerpAPI — news={len(serp_news)} articles, "
                f"trending={len(trending)} tickers"
            )
        except Exception as e:
            logger.warning(f"[STEP-4e] SerpAPI failed: {e}")
            serp_news = []

        # Await all non-blocking tasks
        yf_news: List[dict]      = await yf_news_task
        finnhub_news: List[dict] = await finnhub_task
        yahoo_rss: List[dict]    = await yahoo_rss_task
        stocktwits_data          = await stocktwits_task

        logger.info(
            f"[STEP-4e] Sources — serp={len(serp_news)}, "
            f"yfinance={len(yf_news)}, finnhub={len(finnhub_news)}, "
            f"yahoo_rss={len(yahoo_rss)}, "
            f"stocktwits bullish={stocktwits_data['bullish']} bearish={stocktwits_data['bearish']}"
        )

        # Merge and deduplicate: SerpAPI first (has thumbnail/date), then yfinance,
        # Finnhub, then Yahoo RSS (free fallback active when no API keys are set)
        combined = _dedup_news(serp_news + yf_news + finnhub_news + yahoo_rss)
        news = combined[:12]

        # Score VADER on combined headline set
        all_headlines = [n["title"] for n in news if n.get("title")]
        try:
            sentiment = await asyncio.to_thread(sentiment_svc.score_headlines, all_headlines)
            logger.info(
                f"[STEP-4e] ✓ VADER sentiment — compound={sentiment['compound']:.4f} "
                f"({sentiment['label']}), headlines_scored={sentiment['headline_count']}"
            )
        except Exception as e:
            logger.warning(f"[STEP-4e] VADER scoring failed: {e}")

        try:
            await cache_set(
                news_cache_key,
                {
                    "news":       news,
                    "trending":   trending,
                    "sentiment":  sentiment,
                    "stocktwits": stocktwits_data,
                },
                ttl_seconds=1800,
            )
        except Exception as e:
            logger.warning(f"[STEP-4e] cache_set failed: {e}")

    # Resolve earnings dates (fired concurrently at Step 4c)
    try:
        earnings_dates: List[str] = await earnings_task
    except Exception as e:
        logger.warning(f"[STEP-4e] earnings_task failed: {e}")
        earnings_dates = []

    # ── Step 4f. "Why did this move?" explainer (async, runs concurrently) ─────
    try:
        _cur_f = float(live_price)
    except (TypeError, ValueError):
        _cur_f = 0.0
    _prev  = info.get("prev_close", 0)
    try:
        _prev_f = float(_prev) if _prev not in (None, "N/A") else 0.0
    except (ValueError, TypeError):
        _prev_f = 0.0
    price_change_pct = ((_cur_f - _prev_f) / _prev_f * 100) if _prev_f else 0.0

    move_explanation_task = None
    if abs(price_change_pct) >= 3.0:
        news_headlines_str = " | ".join(
            n["title"] for n in news[:3] if n.get("title")
        )
        _move_system = "You are a concise financial analyst. Reply in 2 sentences max."
        _move_user   = (
            f"{symbol} moved {price_change_pct:+.1f}% today "
            f"(from ${_prev_f:.2f} to ${_cur_f:.2f}). "
            f"Top headlines: {news_headlines_str}. "
            f"What is the most likely catalyst?"
        )
        move_explanation_task = asyncio.create_task(
            analyst_jury_svc.call_groq(
                "llama-3.1-8b-instant",
                _move_system,
                _move_user,
                max_tokens=120,
            )
        )
        logger.info(
            f"[STEP-4f] Move explainer task launched — {symbol} {price_change_pct:+.1f}%"
        )

    # ── Step 5. AI analyst note + jury (concurrent) ──────────────────────────
    logger.info(
        f"[STEP-5] Dispatching AI header note (Groq llama-3.3-70b) + "
        f"analyst jury ({len(ANALYST_PERSONAS)} personas) concurrently ..."
    )
    logger.debug(
        f"[STEP-5] Data sent to AI layer — symbol={symbol}, RSI={rsi:.2f}, "
        f"forecast_high=${forecast['high']:.2f}, forecast_low=${forecast['low']:.2f}, "
        f"conf={forecast['conf']}, ann_vol={forecast.get('stats', {}).get('ann_volatility_pct', 'N/A')}%"
    )
    _jury_fp = hashlib.md5(
        f"{rsi:.1f}|{forecast['high']:.2f}|{forecast['low']:.2f}|{closes[-1]:.2f}|{sentiment.get('label', '')}".encode()
    ).hexdigest()[:12]
    jury_cache_key = f"jury:{symbol.upper()}:{_jury_fp}"
    cached_jury = await cache_get(jury_cache_key)
    if cached_jury is not None:
        logger.info(f"[STEP-5] Jury cache HIT for {symbol} — skipping Groq jury calls")
        note = await _ai_note(symbol, closes, rsi, forecast)
        jury = cached_jury
    else:
        logger.info(f"[STEP-5] Jury cache MISS for {symbol} — running full jury")
        note, jury = await asyncio.gather(
            _ai_note(symbol, closes, rsi, forecast),
            _run_analyst_jury(
                symbol, closes, rsi, forecast,
                forecast.get("stats", {}),
                info, macd_data, bb_data, sma50, sma200,
                historical_prices, sr_levels,
                news_headlines=[n["title"] for n in news if n.get("title")],
                track_record=track_record,
                sentiment=sentiment,
                stocktwits=stocktwits_data,
            ),
        )
        if jury:
            await cache_set(jury_cache_key, jury, ttl_seconds=1200)  # 20 min
    logger.info(
        f"[STEP-5] ✓ AI layer complete — "
        f"note={len(note)} chars | jury={len(jury)} verdicts"
    )
    for v in jury:
        logger.info(
            f"[STEP-5] [JURY/{v['id']}] rating={v['rating']}, "
            f"confidence={v['confidence']}%, model={v['model']}"
        )

    # ── Step 5b. Await move explainer if running ─────────────────────────────
    move_explanation: Optional[str] = None
    if move_explanation_task is not None:
        try:
            move_explanation = await asyncio.wait_for(move_explanation_task, timeout=8.0)
            logger.info(f"[STEP-5b] Move explanation received ({len(move_explanation)} chars)")
        except Exception as _me:
            logger.warning(f"[STEP-5b] Move explanation failed: {_me}")
        # Guaranteed fallback: card always shows on big moves even if Groq fails
        if not move_explanation:
            direction = "up" if price_change_pct > 0 else "down"
            top_headline = news[0]["title"] if news else "no headlines available"
            move_explanation = (
                f"{symbol} is {direction} {abs(price_change_pct):.1f}% today. "
                f"Top story: {top_headline}"
            )
            logger.info("[STEP-5b] Using fallback move explanation")

    # ── Step 6. (News/trending already resolved at 4e — nothing to await) ────
    logger.debug(
        f"[STEP-6] News/trending already resolved — "
        f"news={len(news)}, trending={len(trending)}, "
        f"sentiment={sentiment['label']} ({sentiment['compound']:+.3f})"
    )

    # ── Step 7. Background price snapshot ────────────────────────────────────
    logger.debug(
        f"[STEP-7] Scheduling background InfluxDB price snapshot — "
        f"{symbol} @ ${live_price:.2f}"
    )
    _safe_background(
        asyncio.to_thread(influx_svc.write_price, symbol, live_price),
        name="INFLUX-WRITE",
    )

    # ── Step 8. Build chart history (last 90 trading days) ───────────────────
    total       = len(historical_prices)
    slice_start = max(0, total - 90)
    logger.debug(
        f"[STEP-8] Building chart history — total_bars={total}, "
        f"chart_window=90, slice_start={slice_start} "
        f"(showing bars {slice_start}–{total - 1})"
    )
    history = []
    for idx, p in enumerate(historical_prices[slice_start:], start=slice_start):
        history.append({
            "date":        p["_time"].strftime("%m/%d") if hasattr(p["_time"], "strftime") else str(p["_time"])[:10],
            "price":       round(float(p["close"]),                 2),
            "open":        round(float(p.get("open",  p["close"])), 2),
            "high":        round(float(p.get("high",  p["close"])), 2),
            "low":         round(float(p.get("low",   p["close"])), 2),
            "volume":      round(float(p.get("volume", 0)),         0),
            "bb_upper":    bb_data["upper"][idx],
            "bb_middle":   bb_data["middle"][idx],
            "bb_lower":    bb_data["lower"][idx],
            "sma50":       sma50[idx],
            "sma200":      sma200[idx],
            "ema20":       ema20[idx],
            "ema50":       ema50[idx],
            "macd":        macd_data["macd"][idx],
            "macd_signal": macd_data["signal"][idx],
            "macd_hist":   macd_data["hist"][idx],
        })

    # RSI series — last 90 points aligned to chart window
    rsi_full   = calculate_rsi_series(closes)
    rsi_series = rsi_full[slice_start:]
    logger.info(
        f"[STEP-8] ✓ Chart history built — {len(history)} bars | "
        f"RSI series: {len(rsi_series)} points"
    )

    # ── Response summary ──────────────────────────────────────────────────────
    logger.info(
        f"[RESPONSE] {symbol} — price=${live_price:.2f}, RSI={rsi:.2f} | "
        f"forecast: high=${forecast['high']:.2f}, low=${forecast['low']:.2f}, "
        f"conf={forecast['conf']} | "
        f"history={len(history)} bars | news={len(news)} | trending={len(trending)} | "
        f"jury={len(jury)} analysts"
    )
    logger.info(f"[REQUEST] ════════════════ /predict ← {symbol} complete ════════════════")

    return PredictionResponse(
        symbol       = symbol,
        currentPrice = f"{live_price:.2f}",
        rsi          = f"{rsi:.2f}",
        prediction   = {
            "highRange": f"{forecast['high']:.2f}",
            "lowRange":  f"{forecast['low']:.2f}",
            "trend":     "Bullish" if rsi > 50 else "Bearish",
        },
        analystNote  = note,
        confidence   = forecast["conf"],
        history      = history,
        forecastDays = forecast["forecast_days"],
        modelStats   = forecast.get("stats", {}),
        metrics      = metrics,
        news         = news,
        trending     = trending,
        indicators   = {
            "rsi_series": rsi_series,
            "support":    sr_levels["support"],
            "resistance": sr_levels["resistance"],
        },
        lastUpdated  = now.isoformat(),
        juryAnalysts  = jury,
        modelWeights  = forecast.get("weights", {"prophet": 0.0, "sarima": 0.0, "rf": 0.0}),
        sentiment    = sentiment,
        stocktwits   = stocktwits_data,
        monteCarlo      = forecast.get("monte_carlo"),
        earningsDates   = earnings_dates,
        moveExplanation = move_explanation,
    )


@router.post("/predict", response_model=PredictionResponse)
async def predict(payload: PredictRequest):
    try:
        return await asyncio.wait_for(_predict_inner(payload), timeout=50.0)
    except asyncio.TimeoutError:
        logger.error("[PREDICT] Request timed out after 50s")
        raise HTTPException(status_code=503, detail="Analysis timed out — please try again.")


@router.get("/compare")
async def compare_peers(symbols: str = Query(..., description="Comma-separated tickers, max 6")):
    """
    Returns side-by-side fundamentals for up to 6 tickers.
    Each symbol hits Redis cache first (same 1h TTL as /predict).
    """
    raw = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    # Validate: only alphanumeric, hyphens, and dots (e.g. BRK.B, BTC-USD)
    syms = [s for s in raw if re.match(r'^[A-Z0-9.\-]{1,10}$', s)][:6]
    if not syms:
        raise HTTPException(status_code=400, detail="Provide at least one valid symbol (max 6).")

    async def _peer(sym: str) -> dict:
        cached = await cache_get(f"info:{sym}")
        if cached:
            info = cached
        else:
            info = await asyncio.to_thread(yf_svc.fetch_info, sym)
            if info:
                await cache_set(f"info:{sym}", info, ttl_seconds=3600)
        price = info.get("current_price", 0)
        return {
            "symbol":         sym,
            "name":           info.get("short_name", sym),
            "sector":         info.get("sector",      "N/A"),
            "price":          f"{float(price):.2f}" if price else "N/A",
            "market_cap":     _fmt_market_cap(info.get("market_cap")),
            "pe_ratio":       _fmt_ratio(info.get("pe_ratio"))     if info.get("pe_ratio")     not in (None, "N/A") else "N/A",
            "forward_pe":     _fmt_ratio(info.get("forward_pe"))   if info.get("forward_pe")   not in (None, "N/A") else "N/A",
            "peg_ratio":      _fmt_ratio(info.get("peg_ratio"))    if info.get("peg_ratio")    not in (None, "N/A") else "N/A",
            "ev_to_ebitda":   _fmt_ratio(info.get("ev_to_ebitda")) if info.get("ev_to_ebitda") not in (None, "N/A") else "N/A",
            "beta":           _fmt_ratio(info.get("beta"))         if info.get("beta")         not in (None, "N/A") else "N/A",
            "revenue_growth": _fmt_pct(info.get("revenue_growth")) if info.get("revenue_growth") not in (None, "N/A") else "N/A",
            "range_52w":      info.get("range_52w", "N/A"),
        }

    results = await asyncio.gather(*[_peer(s) for s in syms], return_exceptions=True)
    peers = [r for r in results if not isinstance(r, Exception)]
    logger.info(f"[COMPARE] ✓ {len(peers)}/{len(syms)} peers resolved: {[p['symbol'] for p in peers]}")
    return {"peers": peers}
