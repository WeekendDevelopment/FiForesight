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

import logging
from typing import Annotated, Dict, List, Optional, TypedDict

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
            verdict = await analyst_jury_svc.get_analyst_verdict(persona, state["ctx"])
            logger.info(
                f"[JURY-GRAPH/{pid}] ✓ verdict — "
                f"rating={verdict['rating']}, confidence={verdict['confidence']}%"
            )
            return {"verdicts": {pid: verdict}}
        except Exception as exc:
            logger.error(f"[JURY-GRAPH/{pid}] ✗ node failed: {exc}", exc_info=True)
            fallback = {
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
            }
        verdicts.append(v)

    logger.info(
        f"[JURY-GRAPH] ✓ Complete — "
        + ", ".join(f"{v['id']}={v['rating']}({v['confidence']}%)" for v in verdicts)
    )
    return verdicts
