# backend/routers/predict.py  # noqa: E501
import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi.util import get_remote_address
from pydantic import BaseModel

from config import Config
from models import (
    calculate_rsi, calculate_rsi_series, run_ensemble_forecast,
    calculate_macd, calculate_bollinger_bands, calculate_sma_series,
    calculate_ema_series, calculate_support_resistance,
    calculate_atr, calculate_stochastic, calculate_adx, calculate_obv,
    detect_divergences,
    _skill_to_weights,
)
from services import DataCleaner, ANALYST_PERSONAS
from dependencies import (
    influx_svc, forecast_store, serp_svc, yf_svc,
    analyst_jury_svc, sentiment_svc, finnhub_svc, stocktwits_svc, yahoo_rss_svc,
    fred_svc, insider_svc, short_interest_svc, regime_svc,
    limiter, get_user_id, _user_rate_key,
)
from jury_graph import run_jury_graph, detect_dissent
from redis_cache import cache_get, cache_set
from reversal import compute_reversal_risk
from direction import compute_direction_forecast

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


class JuryReanalyzeRequest(BaseModel):
    symbol: str
    # True  → force Groq function-calling tools (each analyst must consult ≥1
    #         live feed). Default preserves the original "Use tools" semantics.
    # False → plain single-completion jury run (cheapest: 3 Groq calls total).
    use_tools: bool = True


class RegimeInfoResponse(BaseModel):
    regime: str
    confidence: float
    state_means: Optional[Dict[str, float]] = None
    bars_in_current_regime: Optional[int] = None


class JuryDissentResponse(BaseModel):
    analyst: str
    verdict: str
    rationale: str


class GapAlertResponse(BaseModel):
    gapPct:      float
    direction:   str          # "up" | "down"
    explanation: str
    headlines:   List[str]


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
    reversalRisk:       Optional[dict] = None
    directionForecast:  Optional[dict] = None
    # Alternative data (Feature 15) — populated fire-and-forget, never blocking.
    insiderTransactions: List[dict]    = []
    shortInterest:       Optional[dict] = None
    # Market regime intelligence (Feature 16)
    regime:        Optional[RegimeInfoResponse]  = None   # HMM regime label + confidence
    juryDissent:   Optional[JuryDissentResponse] = None   # minority view on a 2-1 split, else None
    # Gap Explainer (Feature 22) — populated only on a >=3% daily move, else None
    gap_alert:     Optional[GapAlertResponse]    = None


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


async def _compute_gap_alert(
    symbol: str,
    hist_df,
    news_headlines: List[str],
    groq_call=None,
) -> Optional[dict]:
    """Return a gap-alert dict when the latest daily move is >= 3% (abs), else None.

    `hist_df` is the cleaned OHLCV DataFrame (needs a ``Close`` column); the gap is
    yesterday's close (``iloc[-2]``) vs the most recent close (``iloc[-1]``).
    `groq_call` is an async callable ``(model, system, user, max_tokens) -> str``
    — i.e. ``AnalystJuryService.call_groq``. When it's None or there are no
    headlines the alert is still returned, just with an empty explanation. Any
    failure (data or Groq) degrades to ``None``/empty explanation — never raises
    into /predict (Feature 22).
    """
    try:
        if hist_df is None or len(hist_df) < 2:
            return None
        prev_close = float(hist_df["Close"].iloc[-2])
        # Use the last available close (today's close or most recent price).
        last_close = float(hist_df["Close"].iloc[-1])
        if prev_close == 0:
            return None
        gap_pct = (last_close - prev_close) / prev_close * 100
        if abs(gap_pct) < 3.0:
            return None

        direction = "up" if gap_pct > 0 else "down"
        top_headlines = [h for h in news_headlines if h][:3]
        explanation = ""
        if groq_call and top_headlines:
            headlines_text = "; ".join(top_headlines)
            system = (
                "You are a concise financial analyst. "
                "Reply in one sentence only, max 20 words — no markdown."
            )
            user = (
                f"{symbol} moved {gap_pct:+.1f}% today. "
                f"Headlines: {headlines_text}. "
                "In one sentence (max 20 words), explain the most likely cause."
            )
            try:
                raw = await asyncio.wait_for(
                    groq_call(
                        "meta-llama/llama-4-scout-17b-16e-instruct",
                        system, user, 60,
                    ),
                    timeout=8.0,
                )
                explanation = (raw or "").strip()
            except Exception as e:
                logger.warning(f"[GAP] gap explainer groq failed for {symbol}: {e}")
                explanation = ""

        return {
            "gapPct": round(gap_pct, 2),
            "direction": direction,
            "explanation": explanation,
            "headlines": top_headlines,
        }
    except Exception as e:
        logger.warning(f"[GAP] _compute_gap_alert {symbol}: {e}")
        return None


async def _ai_note(symbol: str, closes: List[float], rsi: float, forecast: dict) -> str:
    """
    Header analyst note via Groq llama-3.1-8b-instant (14,400 RPD free — highest budget).
    Uses 8B instead of 70B to preserve llama-3.3-70b-versatile's 1K RPD exclusively for
    the LLAMA-70B jury analyst.  Falls back to the ensemble model's own note if unavailable.
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
        f"model=llama-3.1-8b-instant, symbol={symbol}, RSI={rsi:.1f}, "
        f"forecast_high=${forecast['high']:.2f}, forecast_low=${forecast['low']:.2f}, "
        f"conf={forecast.get('conf', 'low')} | "
        f"data_sent: last 20 closes of {len(closes)} total"
    )
    try:
        raw = await analyst_jury_svc._call_groq(
            "llama-3.1-8b-instant", system, prompt
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
    divergences: Optional[dict] = None,
    macro: Optional[dict] = None,
    regime: Optional[dict] = None,
    ctx_only: bool = False,
) -> List[dict]:
    """
    Run all 3 analyst personas concurrently via AnalystJuryService.

    With `ctx_only=True` the market-context string is assembled and cached
    (for POST /jury/reanalyze) but no Groq calls are made — returns [].
    This is the default path now that the jury is on-demand.
      - LLAMA-4-SCOUT → Groq meta-llama/llama-4-scout-17b-16e-instruct (macro & risk lens, Meta)
      - LLAMA-70B     → Groq llama-3.3-70b-versatile  (growth lens, Meta)
      - LLAMA-8B      → Groq llama-3.1-8b-instant        (quant lens, 14.4K RPD)

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

    # Divergence signals (Feature 14) — only surfaced when at least one fired.
    div_line = ""
    if divergences:
        active = [
            label for key, label in (
                ("rsi_bullish",  "Bullish RSI divergence"),
                ("rsi_bearish",  "Bearish RSI divergence"),
                ("macd_bullish", "Bullish MACD divergence"),
                ("macd_bearish", "Bearish MACD divergence"),
            ) if divergences.get(key)
        ]
        if active:
            div_line = f"Divergence signals: {', '.join(active)}\n"

    # Macro backdrop (Feature 15) — live FRED snapshot, only when available.
    macro_line = ""
    if macro:
        def _m(key: str) -> str:
            d = macro.get(key)
            if not isinstance(d, dict) or d.get("value") is None:
                return "N/A"
            return f"{d['value']:.2f} ({d['delta_30d']:+.2f} 30d)"
        curve = macro.get("t10y2y", {})
        curve_str = (
            f"{curve.get('value'):+.2f}" if isinstance(curve, dict) and curve.get("value") is not None else "N/A"
        )
        macro_line = (
            f"Macro (FRED): 10Y={_m('dgs10')} | CPI={_m('cpiaucsl')} | "
            f"Unemployment={_m('unrate')} | FedFunds={_m('fedfunds')} | "
            f"10Y-2Y curve={curve_str}{' [INVERTED]' if macro.get('inverted') else ''}\n"
        )

    # Market regime (Feature 16) — live HMM label, only when detected.
    regime_line = ""
    if regime and regime.get("regime") and regime.get("regime") != "unknown":
        regime_line = (
            f"Market regime (3-state HMM): {regime['regime'].replace('_', ' ')} "
            f"({regime.get('confidence', 0) * 100:.0f}% confidence, "
            f"{regime.get('bars_in_current_regime', 0)} bars in current state). "
            f"Ensemble weights have been tilted to favour the model that suits this regime.\n"
        )

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
        f"{div_line}"
        f"{macro_line}"
        f"{regime_line}"
        f"{sentiment_line}"
        f"{news_block}"
        + (f"{track_record}\n" if track_record else "")
    )

    # ------------------------------------------------------------------
    # Dispatch all personas via LangGraph jury graph (parallel fan-out).
    # Each analyst is an independent node; failures are isolated per-node.
    # Swap .ainvoke() → .stream() here in future for SSE streaming.
    # ------------------------------------------------------------------
    # Stash the assembled context so POST /jury/reanalyze can re-run the jury
    # with tools forced on, without recomputing every indicator from scratch.
    # Wrap in a dict — cache_get discards non-list/dict payloads, so a bare
    # string would be silently dropped on read.
    try:
        await cache_set(f"jury_ctx:{symbol.upper()}", {"ctx": ctx}, ttl_seconds=28800)  # 8h
    except Exception as exc:
        logger.debug(f"[JURY-GRAPH] ctx cache_set failed (non-fatal): {exc}")

    if ctx_only:
        logger.info(f"[JURY-GRAPH] ctx_only — context cached for {symbol}, jury deferred to /jury/reanalyze")
        return []

    try:
        # Prepend UTC minute-timestamp to the live context so Groq never returns a
        # server-side cached completion when the same ticker is queried repeatedly
        # within a short window (prices identical → prompts would otherwise match).
        # The cached `ctx` above stays clean (no timestamp) for /jury/reanalyze.
        ts_prefix = (
            f"[Analysis timestamp: "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC]\n"
        )
        # 30s budget accommodates tool-call round-trips (Groq function calling).
        return await asyncio.wait_for(
            run_jury_graph(analyst_jury_svc, ANALYST_PERSONAS, ts_prefix + ctx, symbol=symbol),
            timeout=30.0,
        )
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
                "tools_used":  [],
            }
            for persona in ANALYST_PERSONAS
        ]


# ---------------------------------------------------------------------------
# Jury re-analysis — re-run the jury with live tools forced on
# ---------------------------------------------------------------------------

@router.post("/jury/reanalyze")
@limiter.limit(lambda: Config.RATE_LIMIT_JURY, key_func=_user_rate_key)
async def reanalyze_jury(request: Request, payload: JuryReanalyzeRequest, user: str = Depends(get_user_id)):
    """
    Run the analyst jury on demand for a symbol.

    Auth tiers (the jury was a public feature before it moved on-demand, so the
    cheap path stays public; the expensive live-tools path is a signed-in perk):
      - `use_tools=false` (the default "Run analyst jury" button) → anonymous
        OK. Each analyst makes a single plain completion (3 Groq calls total).
      - `use_tools=true` ("Use tools" re-run) → requires a signed-in user.
        Groq function-calling tools are FORCED on (each analyst must invoke ≥1
        live tool: VIX, put/call, insider, or macro). Gated because it can fire
        up to ~9 Groq calls and would otherwise let anonymous traffic drain the
        free-tier quota.

    Reuses the market-context string assembled by the most recent /predict for
    this symbol — call /predict first. Anonymous callers are IP-rate-limited
    (RATE_LIMIT_JURY), same as /predict.

    Returns {"juryAnalysts": [...]} with populated `tools_used` per analyst.
    """
    symbol = (payload.symbol or "").strip().upper()
    if not symbol or not re.fullmatch(r"[A-Za-z0-9.\-:]{1,15}", symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol.")

    if payload.use_tools and not user:
        raise HTTPException(
            status_code=401,
            detail="Sign in to run the live-tools analysis.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    cached = await cache_get(f"jury_ctx:{symbol}")
    ctx = cached.get("ctx") if isinstance(cached, dict) else None
    if not ctx:
        raise HTTPException(
            status_code=409,
            detail="No analysis context for this symbol yet — run a prediction first.",
        )

    use_tools = bool(payload.use_tools)
    logger.info(
        f"[JURY-REANALYZE] {symbol} — running jury on demand "
        f"(tools {'forced on' if use_tools else 'off'})"
    )
    try:
        jury = await asyncio.wait_for(
            run_jury_graph(
                analyst_jury_svc, ANALYST_PERSONAS, ctx,
                symbol=symbol, enable_tools=use_tools, force_tools=use_tools,
            ),
            timeout=40.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"[JURY-REANALYZE] {symbol} timed out after 40s")
        raise HTTPException(status_code=504, detail="Re-analysis timed out — please try again.")
    except Exception as exc:
        logger.error(f"[JURY-REANALYZE] {symbol} failed: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail="Re-analysis failed — please try again.")

    tools_total = sum(len(v.get("tools_used", [])) for v in jury)
    logger.info(f"[JURY-REANALYZE] ✓ {symbol} — {len(jury)} verdicts, {tools_total} tool calls")
    return {"juryAnalysts": jury, "juryDissent": detect_dissent(jury)}


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


def _fetch_intraday_bars(symbol: str) -> dict:
    """Fetch 1-day 5-min OHLCV for symbol; return {price, change_pct, bars}.

    Runs synchronously — call via asyncio.to_thread.
    Strips pre/post-market bars (keeps 09:30–16:00 ET only).
    Returns {} on any failure so callers can skip gracefully.
    """
    import yfinance as _yf

    try:
        df = _yf.download(
            symbol, period="1d", interval="5m",
            progress=False, auto_adjust=True, timeout=10,
        )
        if df is None or df.empty:
            return {}

        # Flatten MultiIndex columns if present (yfinance ≥ 0.2.38)
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        # Strip pre/post-market: keep 09:30–16:00 ET
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        idx_et = idx.tz_convert("America/New_York")
        mask = (
            ((idx_et.hour == 9)  & (idx_et.minute >= 30)) |
            ((idx_et.hour > 9)   & (idx_et.hour < 16))    |
            ((idx_et.hour == 16) & (idx_et.minute == 0))
        )
        df = df[mask][:78]  # max 78 bars (full trading day)

        if df.empty:
            return {}

        close_col = "Close" if "Close" in df.columns else "close"
        closes_s  = df[close_col].dropna()
        if len(closes_s) < 2:
            return {}

        first_close = float(closes_s.iloc[0])
        last_close  = float(closes_s.iloc[-1])
        change_pct  = ((last_close - first_close) / first_close * 100) if first_close else 0.0

        bars = [
            {"t": ts.strftime("%Y-%m-%dT%H:%M:%S"), "c": round(float(v), 4)}
            for ts, v in zip(
                closes_s.index.tz_convert("UTC").tz_localize(None),
                closes_s,
            )
        ]
        return {"price": round(last_close, 4), "change_pct": round(change_pct, 4), "bars": bars}
    except Exception as exc:
        logger.debug("[sparklines] _fetch_intraday_bars(%s) error: %s", symbol, exc)
        return {}


@router.get("/sparklines")
@limiter.limit(lambda: Config.RATE_LIMIT_READONLY, key_func=get_remote_address)
async def sparklines(request: Request, tickers: str = "", extra: str = "") -> List[Dict[str, Any]]:
    """Return intraday 1d/5m bar data for trending tickers + optional extra symbols.

    Query params:
      tickers — comma-separated base list (legacy; kept for backwards compat)
      extra   — comma-separated additional symbols (frontend appends watchlist here)

    Response per symbol:
      { symbol, price, change_pct, bars: [{t, c}] }

    Partial failures are skipped silently; the rest still return.
    Each symbol is cached individually for 5 minutes to avoid redundant yfinance calls.
    """
    # Build deduplicated symbol list (base + extras, max 24)
    base   = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    extras = [t.strip().upper() for t in extra.split(",") if t.strip()]
    seen: set = set()
    symbols: List[str] = []
    for s in base + extras:
        if s and s not in seen:
            seen.add(s)
            symbols.append(s)
    symbols = symbols[:24]

    _SPARKLINE_TTL = 300  # 5 minutes

    async def _get_one(sym: str) -> Optional[dict]:
        cache_key = f"sparkline:{sym}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached
        data = await asyncio.wait_for(
            asyncio.to_thread(_fetch_intraday_bars, sym),
            timeout=12.0,
        )
        if data:
            payload = {"symbol": sym, **data}
            await cache_set(cache_key, payload, ttl_seconds=_SPARKLINE_TTL)
            return payload
        return None

    tasks = [asyncio.create_task(_get_one(s)) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: List[dict] = []
    for sym, res in zip(symbols, results):
        if isinstance(res, Exception):
            logger.warning("[sparklines] %s failed: %s", sym, res)
        elif res is not None:
            output.append(res)
    return output


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
    if not re.fullmatch(r"[A-Za-z0-9.\-:]{1,15}", symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol.")
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
    # All three queries run concurrently — no inter-dependency.
    logger.debug(f"[RL] Querying historical model accuracy for {symbol} ...")

    async def _rl_query(fn, default):
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, symbol), timeout=12.0)
        except Exception as exc:
            logger.warning("[RL] metric query failed (%s): %s — using default", fn.__name__, exc)
            return default

    model_acc, ensemble_mae, naive_mae_val = await asyncio.gather(
        _rl_query(forecast_store.query_model_accuracy, {}),
        _rl_query(forecast_store.query_ensemble_mae,   {}),
        _rl_query(forecast_store.query_naive_mae,      None),
    )

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
            maes = [
                p_acc.get("mae", 999.0),
                s_acc.get("mae", 999.0),
                r_acc.get("mae", 999.0),
            ]
            historical_weights = _skill_to_weights(maes, naive_mae_val)
            using_skill = naive_mae_val is not None and naive_mae_val > 0
            logger.debug(
                "[RL] %s weights — prophet=%.3f sarima=%.3f rf=%.3f | "
                "naive_mae=%s | samples=%d",
                "Skill-based" if using_skill else "Inv-MAE (no naive baseline yet)",
                historical_weights[0], historical_weights[1], historical_weights[2],
                "N/A" if naive_mae_val is None else f"{naive_mae_val:.4f}",
                rl_sample_count,
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
    # ── Market regime detection (Feature 16) ─────────────────────────────────
    # 3-state Gaussian HMM on the last 60 bars → {regime, confidence, ...}.
    # Self-contained + Redis-cached 4h; degrades to {"regime":"unknown"} on any
    # failure (or <30 bars), so it never blocks or breaks the forecast.
    regime_result = await _safe_fetch(
        regime_svc.get_regime(symbol, closes),
        empty={"regime": "unknown", "confidence": 0.0}, name="REGIME",
    )
    logger.info(
        "[STEP-4a] Regime — %s (conf=%.2f, %s bars)",
        regime_result.get("regime"), regime_result.get("confidence", 0.0),
        regime_result.get("bars_in_current_regime", 0),
    )

    forecast = await asyncio.to_thread(
        run_ensemble_forecast,
        closes, symbol,
        opens=opens, highs=highs, lows=lows, volumes=volumes,
        historical_weights=historical_weights,
        sample_count=rl_sample_count,
        ensemble_mae=ensemble_mae,
        regime=regime_result.get("regime"),
        regime_confidence=regime_result.get("confidence", 0.0),
    )

    # Persist the regime label (fire-and-forget) for a future Insights timeline.
    if regime_result.get("regime") and regime_result["regime"] != "unknown":
        _safe_background(
            asyncio.to_thread(
                influx_svc.write_market_regime,
                symbol, regime_result["regime"],
                float(regime_result.get("confidence", 0.0)),
            ),
            name="REGIME-WRITE",
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

    # ── Step 4b+. RSI series + reversal-risk classifier ──────────────────────
    # Compute RSI series here (also reused for chart at Step 8) so the reversal
    # classifier has it available without a second pass through closes.
    rsi_full = calculate_rsi_series(closes)

    # ── Step 4b#. Advanced technical signals (Feature 14) ─────────────────────
    # ATR (volatility stops), Stochastic, ADX, OBV, and RSI/MACD divergence.
    # Each helper is self-contained and returns None / all-false on failure, so
    # the whole block is non-fatal — a bad indicator never aborts /predict.
    atr_14 = await asyncio.to_thread(calculate_atr, highs, lows, closes)
    stoch  = await asyncio.to_thread(calculate_stochastic, highs, lows, closes)
    adx    = await asyncio.to_thread(calculate_adx, highs, lows, closes)
    obv_history = await asyncio.to_thread(calculate_obv, closes, volumes)
    divergences = await asyncio.to_thread(
        detect_divergences, closes, rsi_full, macd_data["hist"]
    )
    logger.info(
        "[STEP-4b#] ✓ Advanced signals — ATR-14=%s | Stoch %%K=%s %%D=%s | "
        "ADX=%s | OBV=%s pts | divergences=%s",
        atr_14, stoch.get("stoch_k"), stoch.get("stoch_d"),
        adx.get("adx_14"), len(obv_history) if obv_history else 0, divergences,
    )

    try:
        reversal_risk = await asyncio.to_thread(
            compute_reversal_risk,
            closes, rsi_full, bb_data["upper"], bb_data["lower"],
            macd_data["hist"], volumes,
        )
        if reversal_risk:
            logger.info(
                "[STEP-4b+] ✓ Reversal risk: %d%% (%s) — trained on %d bars",
                reversal_risk["risk_pct"], reversal_risk["signal"], reversal_risk["trained_on"],
            )
        else:
            logger.info("[STEP-4b+] Reversal risk skipped (insufficient data)")
    except Exception as exc:
        logger.warning("[STEP-4b+] Reversal risk failed for %s: %s", symbol, exc, exc_info=True)
        reversal_risk = None

    # ── Step 4b++. Next-day direction classifier ──────────────────────────────
    try:
        direction_forecast = await asyncio.to_thread(
            compute_direction_forecast,
            closes, rsi_full, bb_data["upper"], bb_data["lower"],
            macd_data["hist"], volumes,
        )
        if direction_forecast:
            logger.info(
                "[STEP-4b++] ✓ Direction: %s %.0f%% confidence (+%d%% edge) — trained on %d bars",
                direction_forecast["direction"].upper(), direction_forecast["confidence_pct"],
                direction_forecast["edge_pct"], direction_forecast["trained_on"],
            )
        else:
            logger.info("[STEP-4b++] Direction forecast skipped (insufficient data)")
    except Exception as exc:
        logger.warning("[STEP-4b++] Direction forecast failed for %s: %s", symbol, exc, exc_info=True)
        direction_forecast = None

    # ── Step 4c. Fire news + earnings fetch concurrently ─────────────────────
    news_cache_key = f"news:{symbol.upper()}"
    cached_news_payload = await cache_get(news_cache_key)
    if cached_news_payload is not None:
        logger.info(f"[STEP-4c] News cache HIT for {symbol}")
    else:
        logger.info(
            "[STEP-4c] News cache MISS — launching SerpAPI, yfinance news, "
            "Finnhub%s tasks" % (", and StockTwits" if Config.STOCKTWITS_ENABLED else "")
        )
        serp_task = asyncio.create_task(
            serp_svc.fetch_data(symbol, exchange=(info.get("exchange") or "NASDAQ"))
        )
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
        # StockTwits' public stream now returns 403 without auth, so the call is
        # gated behind STOCKTWITS_ENABLED to avoid a guaranteed-failing request
        # on every prediction. Enable it only once a working/authed source exists.
        stocktwits_task = (
            asyncio.create_task(
                _safe_fetch(
                    stocktwits_svc.fetch_sentiment(symbol),
                    empty={"bullish": 0, "bearish": 0, "sentiment": 0.0},
                    name="STOCKTWITS",
                )
            )
            if Config.STOCKTWITS_ENABLED
            else None
        )

    earnings_task = asyncio.create_task(
        asyncio.wait_for(
            asyncio.to_thread(yf_svc.fetch_earnings_dates, symbol),
            timeout=12.0,
        )
    )

    # Earnings surprise history (last 4 quarters) — Redis-cached 24h since it
    # only changes once per quarter. Fired concurrently, 12s timeout.
    async def _get_earnings_surprise() -> List[dict]:
        cache_key = f"earnings_surprise:{symbol.upper()}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(yf_svc.fetch_earnings_surprise, symbol),
                timeout=12.0,
            )
        except Exception as exc:
            logger.debug("[STEP-4c] earnings surprise fetch failed: %s", exc)
            data = []
        # Cache real results for 24h. An empty list means either a transient
        # yfinance failure or genuinely no history — cache it only briefly (1h)
        # so a transient failure self-heals instead of sticking for a full day.
        await cache_set(cache_key, data, ttl_seconds=86400 if data else 3600)
        return data

    earnings_surprise_task = asyncio.create_task(_get_earnings_surprise())

    # ── Alternative data (Feature 15) — macro / insider / short interest ──────
    # All fired concurrently and resolved later with short timeouts so EDGAR /
    # FINRA / FRED latency never blocks /predict. Each degrades to {}/[]/None.
    macro_task = asyncio.create_task(
        _safe_fetch(fred_svc.get_macro_snapshot(), empty={}, name="FRED-MACRO")
    )
    insider_task = asyncio.create_task(
        _safe_fetch(
            insider_svc.get_insider_transactions(symbol), empty=[], name="INSIDER"
        )
    )
    short_interest_task = asyncio.create_task(
        _safe_fetch(
            short_interest_svc.get_short_interest(symbol), empty=None, name="SHORT-INT"
        )
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
        logger.info("[STEP-4e] Awaiting news sources (SerpAPI, yfinance, Finnhub, Yahoo RSS) ...")
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
            # Primary trending source: google_finance `discover_more` (related/
            # most-active tickers), parsed in SerpService. Dedupe by symbol against
            # anything already added from the legacy markets block.
            _seen_syms = {t.get("symbol") for t in trending}
            for t in serp_data.get("trending", []):
                sym = t.get("symbol")
                if sym and sym not in _seen_syms:
                    trending.append(t)
                    _seen_syms.add(sym)
                if len(trending) >= 12:
                    break
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
        if stocktwits_task is not None:
            stocktwits_data = await stocktwits_task

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

    # Resolve earnings surprise history (fired concurrently at Step 4c)
    try:
        earnings_surprise: List[dict] = await earnings_surprise_task
    except Exception as e:
        logger.warning(f"[STEP-4e] earnings_surprise_task failed: {e}")
        earnings_surprise = []

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
    # Fall back to closes[-2] (yesterday's bar) when fetch_info prev_close is unavailable
    if _prev_f <= 0 and len(closes) >= 2:
        _prev_f = float(closes[-2])
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

    # ── Step 4f-2. Gap Explainer (F22) — structured >=3% move alert ───────────
    # Reuses the cleaned 2y history `df` (yesterday vs latest close) + top
    # headlines. Fired concurrently with the jury; resolved before the response.
    gap_alert_task = asyncio.create_task(
        _compute_gap_alert(
            symbol, df,
            [n["title"] for n in news[:3] if n.get("title")],
            analyst_jury_svc.call_groq,
        )
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
    # Resolve the FRED macro snapshot before the jury so its context (cached for
    # /jury/reanalyze) carries the live macro backdrop. Cheap — 1h Redis cache.
    macro_snapshot: dict = await macro_task

    _jury_fp = hashlib.md5(
        f"{rsi:.1f}|{forecast['high']:.2f}|{forecast['low']:.2f}|{closes[-1]:.2f}|{sentiment.get('label', '')}".encode()
    ).hexdigest()[:12]
    jury_cache_key       = f"jury:{symbol.upper()}:{_jury_fp}"
    jury_stale_cache_key = f"jury_stale:{symbol.upper()}"   # symbol-level, 8h TTL

    if not Config.JURY_AUTO_RUN:
        # On-demand jury: assemble + cache the market context (so POST
        # /jury/reanalyze can run later without recomputing indicators) but
        # make zero Groq jury calls. The frontend shows a "Run jury" button.
        logger.info(f"[STEP-5] Jury auto-run disabled — caching context only for {symbol}")
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
                divergences=divergences,
                macro=macro_snapshot,
                regime=regime_result,
                ctx_only=True,
            ),
        )
    elif (cached_jury := await cache_get(jury_cache_key)) is not None:
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
                divergences=divergences,
                macro=macro_snapshot,
                regime=regime_result,
            ),
        )

        all_fallback = jury and all(
            v.get("note") in ("Analysis unavailable.", "Rate limit reached — daily Groq quota exhausted.")
            for v in jury
        )

        if jury and not all_fallback:
            # Successful jury — warm both hot cache (2h) and stale fallback (8h)
            await cache_set(jury_cache_key,       jury, ttl_seconds=7200)   # 2h hot
            await cache_set(jury_stale_cache_key, jury, ttl_seconds=28800)  # 8h stale
            logger.info(f"[STEP-5] Jury cached for {symbol} (hot=2h, stale=8h)")
        elif all_fallback:
            # All analysts hit rate-limit / error — check for a recent stale verdict
            stale_jury = await cache_get(jury_stale_cache_key)
            if stale_jury:
                for v in stale_jury:
                    v["note"] = f"[Cached] {v.get('note', '')}"
                jury = stale_jury
                logger.info(f"[STEP-5] Using stale jury for {symbol} — Groq quota likely exhausted")
            # Cache fallback/stale result for 5 min to prevent re-hammering Groq on every request
            await cache_set(jury_cache_key, jury, ttl_seconds=300)
            logger.info(f"[STEP-5] Jury failure cached for {symbol} (5 min — quota likely exhausted)")
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
            move_explanation = await asyncio.wait_for(move_explanation_task, timeout=12.0)
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

    # ── Step 5c. Resolve gap explainer (F22) ─────────────────────────────────
    gap_alert: Optional[dict] = None
    try:
        gap_alert = await asyncio.wait_for(gap_alert_task, timeout=10.0)
    except Exception as _ge:
        logger.warning(f"[STEP-5c] Gap alert failed: {_ge}")
    if gap_alert:
        logger.info(
            f"[STEP-5c] ✓ Gap alert — {symbol} {gap_alert['gapPct']:+.2f}% "
            f"{gap_alert['direction']} ({len(gap_alert['explanation'])} char note)"
        )

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

    # Persist the VADER sentiment score over time (powers the Insights trend
    # chart). Only when at least one headline was scored, so we don't pollute the
    # series with neutral 0.0 points on news-less requests.
    if sentiment.get("headline_count", 0) > 0:
        _safe_background(
            asyncio.to_thread(
                influx_svc.write_sentiment_score,
                symbol, sentiment["compound"], sentiment["label"],
            ),
            name="SENTIMENT-WRITE",
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
            "time":        int(p["_time"].timestamp()) if hasattr(p["_time"], "timestamp") else None,
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

    # RSI series — last 90 points aligned to chart window (rsi_full computed at Step 4b+)
    rsi_series = rsi_full[slice_start:]
    logger.info(
        f"[STEP-8] ✓ Chart history built — {len(history)} bars | "
        f"RSI series: {len(rsi_series)} points"
    )

    # ── Alternative data resolution (Feature 15) ─────────────────────────────
    # Fired at Step 4c; resolved here. _safe_fetch already bounds each to 12s and
    # falls back to []/None, so a slow EDGAR/FINRA call can't stall the response.
    insider_transactions: List[dict] = await insider_task
    short_interest: Optional[dict]   = await short_interest_task
    logger.info(
        "[STEP-7b] Alt-data — insider=%d filings, short_interest=%s, macro=%s",
        len(insider_transactions), "yes" if short_interest else "none",
        "yes" if macro_snapshot else "none",
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
            # ── Advanced technical signals (Feature 14) ──
            "atr_14":      atr_14,
            "stoch_k":     stoch.get("stoch_k"),
            "stoch_d":     stoch.get("stoch_d"),
            "adx_14":      adx.get("adx_14"),
            "plus_di":     adx.get("plus_di"),
            "minus_di":    adx.get("minus_di"),
            "obv_history": obv_history,
            "divergences": divergences,
            "rf_feature_importance": forecast.get("rf_feature_importance", []),
            "earnings_surprise":     earnings_surprise,
        },
        lastUpdated  = now.isoformat(),
        juryAnalysts  = jury,
        modelWeights  = forecast.get("weights", {"prophet": 0.0, "sarima": 0.0, "rf": 0.0}),
        sentiment    = sentiment,
        stocktwits   = stocktwits_data,
        monteCarlo      = forecast.get("monte_carlo"),
        earningsDates   = earnings_dates,
        moveExplanation = move_explanation,
        reversalRisk       = reversal_risk,
        directionForecast  = direction_forecast,
        insiderTransactions = insider_transactions,
        shortInterest       = short_interest,
        regime             = regime_result,
        juryDissent        = detect_dissent(jury),
        gap_alert          = gap_alert,
    )


@router.post("/predict", response_model=PredictionResponse)
@limiter.limit(lambda: Config.RATE_LIMIT_PREDICT_AUTH, key_func=_user_rate_key)
async def predict(request: Request, payload: PredictRequest):
    symbol = payload.data.strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9.\-:]{1,15}", symbol):
        raise HTTPException(status_code=422, detail="Invalid symbol.")
    payload.data = symbol  # normalised for _predict_inner
    try:
        # 60s overall budget: the tool-using jury alone may take up to 30s
        # (Groq function-calling round-trips) on top of data + forecast steps.
        return await asyncio.wait_for(_predict_inner(payload), timeout=60.0)
    except asyncio.TimeoutError:
        logger.error("[PREDICT] Request timed out after 60s")
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
