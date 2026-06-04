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
import logging
from typing import Annotated, Dict, List, TypedDict

from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)


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

def _make_analyst_node(persona: dict, analyst_jury_svc):
    """
    Returns an async graph node function pinned to `persona`.
    The node writes its verdict (or error fallback) into state["verdicts"].
    """
    pid = persona["id"]

    async def _node(state: JuryState) -> dict:
        logger.info(f"[JURY-GRAPH/{pid}] node entered — model={persona['api_model']}")
        try:
            # Hard 12s ceiling on the external LLM fetch so one hung upstream call
            # can't stall the whole jury (applies to both the graph and the
            # direct-fallback execution paths).
            verdict = await asyncio.wait_for(
                analyst_jury_svc.get_analyst_verdict(persona, state["ctx"]),
                timeout=12.0,
            )
            logger.info(
                f"[JURY-GRAPH/{pid}] ✓ verdict — "
                f"rating={verdict['rating']}, confidence={verdict['confidence']}%"
            )
            return {"verdicts": {pid: verdict}}
        except Exception as exc:
            logger.error(f"[JURY-GRAPH/{pid}] ✗ node failed: {exc}", exc_info=True)
            # Surface a useful message: timeout, 429 = quota, else generic
            exc_str = str(exc)
            if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
                fallback_note = "Analysis timed out."
            elif "429" in exc_str or "rate_limit" in exc_str.lower() or "rate limit" in exc_str.lower():
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

def build_jury_graph(analyst_jury_svc, personas: List[dict]):
    """
    Build and compile the jury StateGraph.

    Each persona becomes a node fanned out in parallel from START.
    All nodes write into the shared `verdicts` dict via the merge reducer.
    """
    builder = StateGraph(JuryState)

    node_names = []
    for persona in personas:
        name = f"analyst_{persona['id'].lower().replace('-', '_')}"
        builder.add_node(name, _make_analyst_node(persona, analyst_jury_svc))
        builder.add_edge(START, name)
        builder.add_edge(name, END)
        node_names.append(name)

    graph = builder.compile()
    logger.info(
        f"[JURY-GRAPH] Compiled — {len(personas)} analyst nodes: {node_names}"
    )
    return graph


# ---------------------------------------------------------------------------
# Fallback executor (no LangGraph)
# ---------------------------------------------------------------------------

async def _run_nodes_direct(analyst_jury_svc, personas: List[dict], ctx: str) -> dict:
    """Run each analyst node concurrently WITHOUT LangGraph.

    LangGraph's ``graph.ainvoke`` fails under New Relic's wrapt-based APM
    instrumentation in the deployed image ("FunctionWrapperBase() missing
    required argument 'wrapper'"), which would otherwise degrade the entire
    jury to Hold/25. This path reuses the exact same per-analyst node logic
    (including its per-node error isolation) via ``asyncio.gather`` so the jury
    keeps working under APM. Returns the same ``{"verdicts", "errors"}`` shape
    as the graph's final state.
    """
    nodes = [_make_analyst_node(p, analyst_jury_svc) for p in personas]
    base_state: JuryState = {"ctx": ctx, "verdicts": {}, "errors": {}}
    results = await asyncio.gather(
        *(node(base_state) for node in nodes), return_exceptions=True
    )
    verdicts: Dict[str, dict] = {}
    errors: Dict[str, str] = {}
    for persona, res in zip(personas, results):
        if isinstance(res, BaseException):
            errors[persona["id"]] = str(res)
            continue
        verdicts.update(res.get("verdicts", {}))
        errors.update(res.get("errors", {}))
    return {"ctx": ctx, "verdicts": verdicts, "errors": errors}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_jury_graph(
    analyst_jury_svc,
    personas: List[dict],
    ctx: str,
) -> List[dict]:
    """
    Run the jury graph and return verdicts in the same order as `personas`.

    Equivalent to the old:
        results = await asyncio.gather(*[svc.get_analyst_verdict(p, ctx) for p in personas])

    but with explicit state, per-node error isolation, and graph observability.
    """
    graph = build_jury_graph(analyst_jury_svc, personas)

    initial_state: JuryState = {
        "ctx":      ctx,
        "verdicts": {},
        "errors":   {},
    }

    logger.info(
        f"[JURY-GRAPH] Invoking — {len(personas)} analysts, "
        f"ctx_chars={len(ctx)}"
    )
    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        # LangGraph's Pregel runner is wrapped by New Relic's APM in the deployed
        # image and raises "FunctionWrapperBase() missing required argument
        # 'wrapper'", which would degrade the whole jury to Hold/25. Fall back to
        # running the same nodes directly so the jury still produces real verdicts.
        logger.error(
            f"[JURY-GRAPH] graph.ainvoke failed ({exc}) — "
            f"falling back to direct concurrent execution",
            exc_info=True,
        )
        final_state = await _run_nodes_direct(analyst_jury_svc, personas, ctx)

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
            }
        verdicts.append(v)

    logger.info(
        "[JURY-GRAPH] ✓ Complete — "
        + ", ".join(f"{v['id']}={v['rating']}({v['confidence']}%)" for v in verdicts)
    )
    return verdicts
