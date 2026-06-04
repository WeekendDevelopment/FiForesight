# backend/jury_graph.py
"""
LangGraph-based analyst jury.

Replaces the bare asyncio.gather() approach with a proper StateGraph so that:
  - State is explicit and inspectable (JuryState TypedDict)
  - Each analyst node runs independently; failures are isolated per-node
  - Adding retry edges, synthesis nodes, or streaming is one graph change
  - `.stream()` drop-in replaces `.invoke()` for future SSE support

Graph shape (parallel fan-out):
  START → [llama4scout | llama70b | qwen3] → END
All three analyst nodes fire concurrently via LangGraph's parallel fan-out.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Awaitable, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:  # pragma: no cover - yfinance always present in prod
    yf = None  # type: ignore
    _YF_AVAILABLE = False

logger = logging.getLogger(__name__)


# ===========================================================================
# Tool-using jury — OpenAI-compatible function/tool definitions
#
# Each analyst node can call these tools (Groq function calling) during its
# analysis to pull live market data the static context string doesn't carry.
# Dispatchers below are backed by free yfinance feeds (^VIX, options chain,
# insider transactions, Treasury yield indices) — no paid APIs.
# ===========================================================================

JURY_TOOLS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_vix",
            "description": "Returns current VIX level and 30-day change",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_put_call_ratio",
            "description": "Returns the current put/call ratio for a given symbol",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_insider_flow",
            "description": "Returns recent insider buy/sell count for a symbol (last 90 days)",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_macro_snapshot",
            "description": "Returns current macro indicators: 10Y yield, CPI, fed funds, yield curve",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatchers — blocking yfinance work runs in a thread; results returned
# as JSON strings (the shape Groq expects for role=tool messages).
# ---------------------------------------------------------------------------

def _norm_yield(value: float) -> float:
    """Yahoo Treasury indices (^TNX/^FVX/^IRX) quote yield ×10 (e.g. 42.5 = 4.25%).
    Newer feeds sometimes return the raw percent. Normalise to a plain percent."""
    return round(value / 10.0, 3) if value > 15 else round(value, 3)


def _vix_sync() -> dict:
    hist = yf.Ticker("^VIX").history(period="1mo")
    if hist is None or hist.empty:
        return {"error": "VIX data unavailable"}
    closes = hist["Close"].dropna()
    current = float(closes.iloc[-1])
    month_ago = float(closes.iloc[0])
    change_pct = ((current - month_ago) / month_ago * 100) if month_ago else 0.0
    if current < 15:
        regime = "low / complacent"
    elif current < 20:
        regime = "normal"
    elif current < 30:
        regime = "elevated"
    else:
        regime = "high fear"
    return {
        "vix": round(current, 2),
        "change_30d_pct": round(change_pct, 2),
        "regime": regime,
    }


def _put_call_sync(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    expirations = ticker.options
    if not expirations:
        return {"error": f"no options chain for {symbol}"}
    expiry = expirations[0]
    chain = ticker.option_chain(expiry)
    put_oi  = float(chain.puts.get("openInterest").fillna(0).sum())  if "openInterest" in chain.puts  else 0.0
    call_oi = float(chain.calls.get("openInterest").fillna(0).sum()) if "openInterest" in chain.calls else 0.0
    put_vol  = float(chain.puts.get("volume").fillna(0).sum())  if "volume" in chain.puts  else 0.0
    call_vol = float(chain.calls.get("volume").fillna(0).sum()) if "volume" in chain.calls else 0.0
    pcr_oi  = round(put_oi / call_oi, 3)   if call_oi  else None
    pcr_vol = round(put_vol / call_vol, 3) if call_vol else None
    primary = pcr_oi if pcr_oi is not None else pcr_vol
    if primary is None:
        signal = "no data"
    elif primary > 1.0:
        signal = "bearish (more puts)"
    elif primary < 0.7:
        signal = "bullish (more calls)"
    else:
        signal = "neutral"
    return {
        "symbol": symbol.upper(),
        "expiry": expiry,
        "put_call_ratio_oi": pcr_oi,
        "put_call_ratio_volume": pcr_vol,
        "signal": signal,
    }


def _insider_sync(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    df = ticker.insider_transactions
    if df is None or getattr(df, "empty", True):
        return {"symbol": symbol.upper(), "buys": 0, "sells": 0, "note": "no insider data"}
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    date_col = next((c for c in ("Start Date", "Date") if c in df.columns), None)
    buys = sells = 0
    for _, row in df.iterrows():
        if date_col is not None:
            try:
                ts = row[date_col]
                ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else datetime.fromisoformat(str(ts)[:10])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
            except Exception:
                pass  # undated row — count it rather than drop it
        text = f"{row.get('Text', '')} {row.get('Transaction', '')}".lower()
        if any(k in text for k in ("purchase", "buy", "acquisition", "bought")):
            buys += 1
        elif any(k in text for k in ("sale", "sell", "disposition", "sold")):
            sells += 1
    if buys > sells:
        bias = "net buying"
    elif sells > buys:
        bias = "net selling"
    else:
        bias = "balanced"
    return {"symbol": symbol.upper(), "buys": buys, "sells": sells, "bias": bias, "window_days": 90}


def _macro_sync() -> dict:
    def _last_close(sym: str) -> Optional[float]:
        try:
            hist = yf.Ticker(sym).history(period="5d")
            if hist is None or hist.empty:
                return None
            return _norm_yield(float(hist["Close"].dropna().iloc[-1]))
        except Exception:
            return None

    tnx = _last_close("^TNX")   # 10Y Treasury yield
    fvx = _last_close("^FVX")   # 5Y Treasury yield
    irx = _last_close("^IRX")   # 13-week T-bill (short-end / fed-funds proxy)
    curve = round(tnx - irx, 3) if (tnx is not None and irx is not None) else None
    return {
        "ten_year_yield_pct": tnx,
        "five_year_yield_pct": fvx,
        "thirteen_week_yield_pct": irx,
        "fed_funds_proxy_pct": irx,
        "yield_curve_10y_minus_13w_pct": curve,
        "curve_inverted": (curve is not None and curve < 0),
        "cpi": "unavailable (no free real-time source)",
    }


async def _run_sync_tool(fn, *args) -> dict:
    if not _YF_AVAILABLE:
        return {"error": "market data provider unavailable"}
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as exc:
        logger.warning(f"[JURY-TOOLS] {fn.__name__} failed: {exc}")
        return {"error": "tool fetch failed"}


def make_tool_dispatcher(symbol: str) -> Callable[[str, dict], Awaitable[str]]:
    """Build an async dispatcher bound to the request's `symbol`.

    Returns `async dispatch(name, args) -> json_str`. Results are memoised for
    the lifetime of the dispatcher so the three analysts sharing it don't each
    re-fetch the same market-wide data (VIX, macro) within one request.
    """
    cache: Dict[str, str] = {}

    async def dispatch(name: str, args: dict) -> str:
        # Symbol-bearing tools trust the request symbol over model-supplied args
        # (guards against the model hallucinating a different ticker).
        if name == "get_vix":
            key, result = "get_vix", None
            if key not in cache:
                result = await _run_sync_tool(_vix_sync)
        elif name == "get_macro_snapshot":
            key, result = "get_macro_snapshot", None
            if key not in cache:
                result = await _run_sync_tool(_macro_sync)
        elif name == "get_put_call_ratio":
            key = f"put_call:{symbol}"
            result = await _run_sync_tool(_put_call_sync, symbol) if key not in cache else None
        elif name == "get_insider_flow":
            key = f"insider:{symbol}"
            result = await _run_sync_tool(_insider_sync, symbol) if key not in cache else None
        else:
            return json.dumps({"error": f"unknown tool: {name}"})

        if key not in cache:
            cache[key] = json.dumps(result)
        return cache[key]

    return dispatch


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _merge_verdicts(a: Dict, b: Dict) -> Dict:
    """Reducer: merge two partial verdict dicts (for parallel fan-out)."""
    return {**a, **b}


class JuryState(TypedDict):
    ctx: str                                              # shared market context
    verdicts: Annotated[Dict[str, dict], _merge_verdicts] # analyst_id → verdict
    errors:   Dict[str, str]                              # analyst_id → error msg (diagnostic)


# ---------------------------------------------------------------------------
# Node factory — one async node per analyst persona
# ---------------------------------------------------------------------------

def _make_analyst_node(persona: dict, analyst_jury_svc, tools=None, tool_dispatcher=None):
    """
    Returns an async graph node function pinned to `persona`.
    The node writes its verdict (or error fallback) into state["verdicts"].

    When `tools` and `tool_dispatcher` are provided the analyst runs the
    Groq function-calling loop; otherwise it makes a single completion call.
    """
    pid = persona["id"]

    async def _node(state: JuryState) -> dict:
        logger.info(
            f"[JURY-GRAPH/{pid}] node entered — model={persona['api_model']}, "
            f"tools={'on' if tools and tool_dispatcher else 'off'}"
        )
        try:
            verdict = await analyst_jury_svc.get_analyst_verdict(
                persona, state["ctx"],
                tools=tools, tool_dispatcher=tool_dispatcher,
            )
            logger.info(
                f"[JURY-GRAPH/{pid}] ✓ verdict — "
                f"rating={verdict['rating']}, confidence={verdict['confidence']}%, "
                f"tools_used={verdict.get('tools_used', [])}"
            )
            return {"verdicts": {pid: verdict}}
        except Exception as exc:
            logger.error(f"[JURY-GRAPH/{pid}] ✗ node failed: {exc}", exc_info=True)
            # Surface a useful message: 429 = daily quota exhausted, else generic
            exc_str = str(exc)
            if "429" in exc_str or "rate_limit" in exc_str.lower() or "rate limit" in exc_str.lower():
                fallback_note = "Rate limit reached — daily Groq quota exhausted."
            else:
                fallback_note = "Analysis unavailable."
            fallback = {
                "id":          persona["id"],
                "avatar":      persona["avatar"],
                "title":       persona["title"],
                "model_label": persona["model_label"],
                "color":       persona["color"],
                "rating":      "Hold",
                "note":        fallback_note,
                "confidence":  25,
                "model":       "error",
                "tools_used":  [],
            }
            return {
                "verdicts": {pid: fallback},
                "errors":   {pid: str(exc)},
            }

    _node.__name__ = f"analyst_{pid.lower().replace('-', '_')}"
    return _node


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_jury_graph(analyst_jury_svc, personas: List[dict], tools=None, tool_dispatcher=None):
    """
    Build and compile the jury StateGraph.

    Each persona becomes a node fanned out in parallel from START.
    All nodes write into the shared `verdicts` dict via the merge reducer.
    When `tools`/`tool_dispatcher` are passed, every analyst node is tool-enabled.
    """
    builder = StateGraph(JuryState)

    node_names = []
    for persona in personas:
        name = f"analyst_{persona['id'].lower().replace('-', '_')}"
        builder.add_node(name, _make_analyst_node(persona, analyst_jury_svc, tools, tool_dispatcher))
        builder.add_edge(START, name)
        builder.add_edge(name, END)
        node_names.append(name)

    graph = builder.compile()
    logger.info(
        f"[JURY-GRAPH] Compiled — {len(personas)} analyst nodes: {node_names} "
        f"(tools={'on' if tools and tool_dispatcher else 'off'})"
    )
    return graph


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_jury_graph(
    analyst_jury_svc,
    personas: List[dict],
    ctx: str,
    symbol: Optional[str] = None,
    enable_tools: bool = True,
) -> List[dict]:
    """
    Run the jury graph and return verdicts in the same order as `personas`.

    Equivalent to the old:
        results = await asyncio.gather(*[svc.get_analyst_verdict(p, ctx) for p in personas])

    but with explicit state, per-node error isolation, and graph observability.

    When `symbol` is supplied and `enable_tools` is True, every analyst is given
    the Groq function-calling toolset (`JURY_TOOLS`) backed by a per-request
    dispatcher, so analysts can pull live VIX / put-call / insider / macro data.
    """
    tools = tool_dispatcher = None
    if enable_tools and symbol and _YF_AVAILABLE:
        tools = JURY_TOOLS
        tool_dispatcher = make_tool_dispatcher(symbol)

    graph = build_jury_graph(analyst_jury_svc, personas, tools, tool_dispatcher)

    initial_state: JuryState = {
        "ctx":      ctx,
        "verdicts": {},
        "errors":   {},
    }

    logger.info(
        f"[JURY-GRAPH] Invoking — {len(personas)} analysts, "
        f"ctx_chars={len(ctx)}"
    )
    final_state = await graph.ainvoke(initial_state)

    if final_state.get("errors"):
        for pid, err in final_state["errors"].items():
            logger.warning(f"[JURY-GRAPH] {pid} error recorded: {err}")

    # Return verdicts in the same order as personas list
    verdicts = []
    for persona in personas:
        pid = persona["id"]
        v = final_state["verdicts"].get(pid)
        if v is None:
            # Safety: should never happen if node ran
            logger.error(f"[JURY-GRAPH] Missing verdict for {pid} — inserting fallback")
            v = {
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
        verdicts.append(v)

    logger.info(
        "[JURY-GRAPH] ✓ Complete — "
        + ", ".join(f"{v['id']}={v['rating']}({v['confidence']}%)" for v in verdicts)
    )
    return verdicts
