"""LangGraph StateGraph definition for the Contract Risk Analyzer.

Graph topology
--------------

    [START]
       │
       ▼
   extractor
       │
       ├──────────────────────┐
       ▼                      ▼
  summarizer            risk_analyzer
  (parallel)            (parallel via Send)
       │                      │
       └──────────┬───────────┘
                  ▼
              validator
                  │
                  ▼
            hitl_gate ──(interrupt if needed)──► [WAIT]
                  │                                 │
                  │◄────────────────────────────────┘
                  ▼                     (Command resume)
          report_generator
                  │
                  ▼
              [END]

Notes
-----
- Summarizer and risk_analyzer run in parallel via LangGraph's native
  fan-out support (both listed as successors of extractor).
- The graph uses DynamoDBSaver as the checkpointer for persistence and
  HITL resume support.
- Compile with ``interrupt_before=[]`` so that ``interrupt()`` inside
  hitl_gate is the only pause point.
"""

from __future__ import annotations

import os
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.graph.state import GraphState
from src.nodes.extractor import extractor_node
from src.nodes.hitl_gate import hitl_gate_node
from src.nodes.report_generator import report_generator_node
from src.nodes.risk_analyzer import risk_analyzer_node
from src.nodes.summarizer import summarizer_node
from src.nodes.validator import validator_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


def build_graph(checkpointer: Any | None = None) -> Any:
    """Build and compile the Contract Risk Analyzer StateGraph.

    Parameters
    ----------
    checkpointer:
        An optional LangGraph checkpointer (e.g. ``DynamoDBSaver``).
        When ``None``, the graph runs without persistence (useful for tests).

    Returns
    -------
    CompiledStateGraph
        The compiled, runnable LangGraph application.
    """
    builder = StateGraph(GraphState)

    # ── Register nodes ─────────────────────────────────────────────────────
    builder.add_node("extractor", extractor_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("risk_analyzer", risk_analyzer_node)
    builder.add_node("validator", validator_node)
    builder.add_node("hitl_gate", hitl_gate_node)
    builder.add_node("report_generator", report_generator_node)

    # ── Edges ──────────────────────────────────────────────────────────────
    # Entry point
    builder.add_edge(START, "extractor")

    # Fan-out: extractor → [summarizer, risk_analyzer] in parallel
    builder.add_edge("extractor", "summarizer")
    builder.add_edge("extractor", "risk_analyzer")

    # Fan-in: both parallel branches → validator
    builder.add_edge("summarizer", "validator")
    builder.add_edge("risk_analyzer", "validator")

    # Linear tail
    builder.add_edge("validator", "hitl_gate")
    builder.add_edge("hitl_gate", "report_generator")
    builder.add_edge("report_generator", END)

    # ── Compile ────────────────────────────────────────────────────────────
    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    graph = builder.compile(**compile_kwargs)

    logger.info("graph_compiled", nodes=list(builder.nodes.keys()))
    return graph


def get_compiled_graph() -> Any:
    """Return a compiled graph with the DynamoDB checkpointer.

    Falls back to a memory-only graph if the checkpointer cannot be
    initialised (e.g. LocalStack is not running during unit tests).

    Returns
    -------
    CompiledStateGraph
        Ready-to-run graph instance.
    """
    checkpointer: Any = None
    try:
        from src.services.dynamo_service import get_checkpointer
        checkpointer = get_checkpointer()
        logger.info("checkpointer_loaded", backend="dynamodb")
    except Exception as exc:
        logger.warning(
            "checkpointer_unavailable",
            error=str(exc),
            fallback="in-memory (no persistence)",
        )

    return build_graph(checkpointer=checkpointer)
