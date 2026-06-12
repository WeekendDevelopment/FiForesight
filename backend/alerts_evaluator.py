# backend/alerts_evaluator.py
"""
Scheduled alert evaluator (Feature 9).

Loads every active rule (across all users, via the service-role store), groups
them by symbol so each symbol's live data is fetched once, evaluates each rule,
and — when one fires and isn't in its cooldown window — records a fire, stamps
`last_fired`, and delivers a web-push (and optional email) notification.

Design notes
  • Defensive by symbol: a single bad/halted ticker is logged and skipped; the
    rest of the batch still runs. A failure in one rule never aborts the others.
  • `evaluate_rule()` is a pure function (no I/O) so the per-type firing logic is
    unit-testable with mocked signals.
  • Invoked only by the cron-secret-gated POST /alerts/evaluate endpoint — there
    is NO sleep loop. Recommended cadence: every 15 min during market hours.
"""
import asyncio
import html
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import alerts_store
import notifications
from config import Config
from models import calculate_rsi

logger = logging.getLogger(__name__)

# Rule types and the live signals each one needs.
_NEEDS_RSI = {"rsi_threshold"}
_NEEDS_EARNINGS = {"earnings_soon"}
_NEEDS_FORECAST = {"forecast_breakout"}


def _to_float(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Pure rule evaluation — no I/O, fully unit-testable
# ---------------------------------------------------------------------------

def evaluate_rule(rule: Dict[str, Any], signals: Dict[str, Any]) -> tuple[bool, str, Optional[float]]:
    """Decide whether `rule` fires given pre-fetched `signals`.

    Returns (fired, message, value). When a required signal is missing the rule
    degrades to "not fired" (False, "", None) rather than raising.

    signals keys: price, prev_close, pct_move, rsi, earnings_days,
                  forecast_high, forecast_low.
    """
    rtype = rule.get("type")
    op = rule.get("operator")
    thr = _to_float(rule.get("threshold"))
    sym = (rule.get("symbol") or "").upper()
    price = _to_float(signals.get("price"))

    if rtype == "price_cross":
        if price is None or thr is None or op not in ("above", "below"):
            return False, "", None
        fired = price >= thr if op == "above" else price <= thr
        if fired:
            return True, f"{sym} is {op} ${thr:,.2f} (now ${price:,.2f})", round(price, 2)
        return False, "", None

    if rtype == "rsi_threshold":
        rsi = _to_float(signals.get("rsi"))
        if rsi is None or thr is None or op not in ("above", "below"):
            return False, "", None
        fired = rsi >= thr if op == "above" else rsi <= thr
        if fired:
            return True, f"{sym} RSI is {op} {thr:.0f} (now {rsi:.1f})", round(rsi, 2)
        return False, "", None

    if rtype == "pct_move":
        mv = _to_float(signals.get("pct_move"))
        if mv is None or thr is None:
            return False, "", None
        if op == "above":
            fired = mv >= thr
        elif op == "below":
            fired = mv <= -thr
        else:
            fired = abs(mv) >= thr
        if fired:
            arrow = "up" if mv >= 0 else "down"
            return True, f"{sym} moved {arrow} {abs(mv):.2f}% today (threshold {thr:.2f}%)", round(mv, 2)
        return False, "", None

    if rtype == "earnings_soon":
        days = signals.get("earnings_days")
        if days is None:
            return False, "", None
        days = int(days)
        window = int(thr) if (thr is not None and thr >= 1) else 1
        if 0 <= days <= window:
            when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
            return True, f"{sym} reports earnings {when}", float(days)
        return False, "", None

    if rtype == "forecast_breakout":
        hi = _to_float(signals.get("forecast_high"))
        lo = _to_float(signals.get("forecast_low"))
        if price is None or (hi is None and lo is None):
            return False, "", None
        if hi is not None and price > hi:
            return True, f"{sym} broke above its forecast high ${hi:,.2f} (now ${price:,.2f})", round(price, 2)
        if lo is not None and price < lo:
            return True, f"{sym} broke below its forecast low ${lo:,.2f} (now ${price:,.2f})", round(price, 2)
        return False, "", None

    return False, "", None


def _cooldown_active(last_fired: Any, now: datetime, cooldown: timedelta) -> bool:
    """True when the rule fired within the cooldown window (suppress re-fire)."""
    if not last_fired:
        return False
    try:
        s = str(last_fired).replace("Z", "+00:00")
        ts = datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False
    return (now - ts) < cooldown


# ---------------------------------------------------------------------------
# Live signal fetch (blocking — runs in a worker thread)
# ---------------------------------------------------------------------------

def _next_earnings_days(symbol: str, yf_svc: Any, today: Any) -> Optional[int]:
    """Days until the next earnings date (0 = today), or None if unknown."""
    try:
        import yfinance as yf
        cal = yf.Ticker(yf_svc._to_yf_symbol(symbol)).calendar
        if not cal:
            return None
        raw = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
        if not isinstance(raw, (list, tuple)):
            raw = [raw]
        future = []
        for d in raw:
            try:
                dt = d.date() if hasattr(d, "date") else datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
                future.append((dt - today).days)
            except Exception:
                continue
        upcoming = [d for d in future if d >= 0]
        return min(upcoming) if upcoming else None
    except Exception as exc:
        logger.debug("[ALERTS] earnings lookup failed for %s: %s", symbol, exc)
        return None


def _fetch_symbol_signals(symbol: str, needed: Set[str], yf_svc: Any, forecast_store: Any) -> Dict[str, Any]:
    """Fetch the live signals required by the rule types present for `symbol`.

    Blocking (yfinance + InfluxDB). One symbol's failure raises to the caller,
    which logs and skips just that symbol.
    """
    signals: Dict[str, Any] = {
        "price": None, "prev_close": None, "pct_move": None,
        "rsi": None, "earnings_days": None,
        "forecast_high": None, "forecast_low": None,
    }

    # Price + recent closes (needed by nearly every rule type).
    closes: List[float] = []
    try:
        df = yf_svc.fetch_history(symbol, period="3mo")
        if df is not None and not df.empty and "Close" in df.columns:
            closes = [float(c) for c in df["Close"].tolist() if c is not None]
    except Exception as exc:
        logger.debug("[ALERTS] history fetch failed for %s: %s", symbol, exc)

    try:
        live = float(yf_svc.get_live_price(symbol) or 0.0)
    except Exception:
        live = 0.0
    if live <= 0 and closes:
        live = closes[-1]
    signals["price"] = live if live > 0 else None

    if len(closes) >= 2:
        signals["prev_close"] = closes[-2]
        base = closes[-2]
        cur = signals["price"] if signals["price"] is not None else closes[-1]
        if base:
            signals["pct_move"] = round((cur - base) / base * 100.0, 4)

    if needed & _NEEDS_RSI and len(closes) >= 15:
        try:
            signals["rsi"] = float(calculate_rsi(closes))
        except Exception as exc:
            logger.debug("[ALERTS] RSI calc failed for %s: %s", symbol, exc)

    if needed & _NEEDS_EARNINGS:
        signals["earnings_days"] = _next_earnings_days(symbol, yf_svc, datetime.now(timezone.utc).date())

    if needed & _NEEDS_FORECAST and forecast_store is not None:
        try:
            records = forecast_store.query_forecast_records(symbol, days=10)
            if records:
                latest = records[-1]
                signals["forecast_high"] = _to_float(latest.get("e_d1_high"))
                signals["forecast_low"] = _to_float(latest.get("e_d1_low"))
        except Exception as exc:
            logger.debug("[ALERTS] forecast lookup failed for %s: %s", symbol, exc)

    return signals


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

async def _deliver(user_id: str, title: str, body: str, url: str = "/alerts") -> None:
    """Push to all of a user's subscriptions (+ optional email). Best-effort."""
    try:
        subs = await alerts_store.admin_list_push_subscriptions(user_id)
    except Exception as exc:
        logger.warning("[ALERTS] could not load push subs for %s: %s", user_id, exc)
        subs = []
    for sub in subs:
        status = await notifications.send_web_push(sub, title, body, url)
        if status == "gone":
            # Subscription expired/unsubscribed — prune it. Cleanup is best-effort;
            # a failure here must not abort delivery to the user's other devices.
            try:
                await alerts_store.admin_delete_push_subscription(sub.get("endpoint", ""))
            except Exception as exc:
                logger.warning(
                    "[ALERTS] failed to prune dead push subscription %s: %s",
                    sub.get("endpoint", ""), exc,
                )

    if notifications.email_configured():
        email = await alerts_store.admin_get_user_email(user_id)
        if email:
            await notifications.send_email(
                email, title,
                f"<p style='font-family:sans-serif'>{html.escape(body)}</p>"
                f"<p style='color:#888;font-size:12px'>FiForesight — manage alerts in the app.</p>",
            )


async def _fire(rule: Dict[str, Any], message: str, value: Optional[float], now: datetime) -> None:
    """Record the fire, stamp last_fired, and deliver notifications."""
    rule_id = rule["id"]
    user_id = rule["user_id"]
    symbol = rule.get("symbol", "")
    rtype = rule.get("type", "")
    await alerts_store.admin_record_fire(user_id, rule_id, symbol, rtype, message, value)
    await alerts_store.admin_update_last_fired(rule_id, now.isoformat())
    await _deliver(user_id, f"📈 {symbol} alert", message)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def evaluate_alerts(yf_svc: Any, forecast_store: Any, *, now: Optional[datetime] = None) -> Dict[str, int]:
    """Evaluate every active rule and deliver notifications. Returns a summary."""
    now = now or datetime.now(timezone.utc)
    summary = {"rules_checked": 0, "fired": 0, "symbols": 0, "errors": 0, "skipped_cooldown": 0}

    rules = await alerts_store.admin_list_active_rules()
    by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rules:
        sym = (r.get("symbol") or "").upper()
        if sym:
            by_symbol[sym].append(r)
    summary["symbols"] = len(by_symbol)
    cooldown = timedelta(hours=Config.ALERT_COOLDOWN_HOURS)

    for symbol, sym_rules in by_symbol.items():
        needed = {r.get("type") for r in sym_rules}
        try:
            signals = await asyncio.to_thread(_fetch_symbol_signals, symbol, needed, yf_svc, forecast_store)
        except Exception as exc:
            logger.warning("[ALERTS] signal fetch failed for %s: %s — skipping its rules", symbol, exc)
            summary["errors"] += 1
            continue

        for rule in sym_rules:
            summary["rules_checked"] += 1
            try:
                fired, message, value = evaluate_rule(rule, signals)
            except Exception as exc:
                logger.warning("[ALERTS] rule eval error (%s): %s", rule.get("id"), exc)
                summary["errors"] += 1
                continue
            if not fired:
                continue
            if _cooldown_active(rule.get("last_fired"), now, cooldown):
                summary["skipped_cooldown"] += 1
                continue
            try:
                await _fire(rule, message, value, now)
                summary["fired"] += 1
            except Exception as exc:
                logger.warning("[ALERTS] fire/deliver error (%s): %s", rule.get("id"), exc)
                summary["errors"] += 1

    logger.info("[ALERTS] evaluate_alerts complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Daily briefing digest
# ---------------------------------------------------------------------------

def _pct_change_today(symbol: str) -> Optional[float]:
    """Today's % change vs previous close (blocking)."""
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period="5d", interval="1d")
        if hist is None or len(hist) < 2:
            return None
        prev = float(hist["Close"].iloc[-2])
        last = float(hist["Close"].iloc[-1])
        return round((last - prev) / prev * 100.0, 2) if prev else None
    except Exception:
        return None


async def _market_headline() -> str:
    """One-line market summary, reusing the cached /briefing data when present."""
    from redis_cache import cache_get
    cached = await cache_get("briefing:market")
    indices = (cached or {}).get("indices") if isinstance(cached, dict) else None
    if not indices:
        # Compact fallback — fetch a few headline indices directly.
        def _fetch():
            out = []
            for tk, label in (("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow")):
                pct = _pct_change_today(tk)
                if pct is not None:
                    out.append({"label": label, "change_pct": pct})
            return out
        indices = await asyncio.to_thread(_fetch)
    parts = [
        f"{i['label']} {i['change_pct']:+.2f}%"
        for i in (indices or [])
        if i.get("change_pct") is not None
    ][:4]
    return "Markets: " + ", ".join(parts) if parts else "Markets: data unavailable"


async def _user_movers_line(user_id: str, yf_svc: Any) -> str:
    """Top gainer / loser among the user's holdings today."""
    try:
        holdings = await alerts_store.admin_list_holdings(user_id)
    except Exception:
        return ""
    symbols = [h.get("symbol") for h in holdings if h.get("symbol")][:25]
    if not symbols:
        return ""

    def _movers():
        rows = []
        for s in symbols:
            pct = _pct_change_today(yf_svc._to_yf_symbol(s))
            if pct is not None:
                rows.append((s, pct))
        return rows

    rows = await asyncio.to_thread(_movers)
    if not rows:
        return ""
    rows.sort(key=lambda x: x[1])
    loser = rows[0]
    gainer = rows[-1]
    if gainer[0] == loser[0]:
        return f"Your {gainer[0]} {gainer[1]:+.2f}% today."
    return f"Your movers — {gainer[0]} {gainer[1]:+.2f}%, {loser[0]} {loser[1]:+.2f}%."


async def build_and_send_digest(yf_svc: Any, *, now: Optional[datetime] = None) -> Dict[str, int]:
    """Daily push/email digest: market headline + each user's holdings movers."""
    summary = {"users": 0, "delivered": 0, "errors": 0}
    try:
        subs = await alerts_store.admin_list_all_push_subscriptions()
    except Exception as exc:
        logger.error("[ALERTS] digest: could not load subscriptions: %s", exc)
        raise
    user_ids = sorted({s.get("user_id") for s in subs if s.get("user_id")})
    summary["users"] = len(user_ids)

    market_line = await _market_headline()
    for uid in user_ids:
        try:
            movers = await _user_movers_line(uid, yf_svc)
            body = market_line if not movers else f"{market_line} {movers}"
            await _deliver(uid, "🗞️ FiForesight Daily Briefing", body)
            summary["delivered"] += 1
        except Exception as exc:
            logger.warning("[ALERTS] digest delivery failed for %s: %s", uid, exc)
            summary["errors"] += 1

    logger.info("[ALERTS] digest complete: %s", summary)
    return summary
