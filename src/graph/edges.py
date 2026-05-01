"""Graph edge routing logic.

All conditional routing lives HERE — never inside node functions.
This keeps nodes pure and testable in isolation.

Routing rules
-------------
- After extractor  → fan-out to summarizer AND risk_analyzer in parallel
                     via LangGraph's Send() API.
- After the fan-in (both parallel nodes finish) → validator
- After validator  → hitl_gate (always; the gate itself decides to interrupt)
- After hitl_gate  → report_generator (always — either auto-pass or post-HITL)
"""

from __future__ import annotations

from typing import Literal

from src.graph.state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


def route_after_extractor(
    state: GraphState,
) -> list[str]:
    """Decide which nodes follow the extractor.

    Both summarizer and risk_analyzer always run (in parallel via Send()).
    If extraction completely failed, we still forward so the downstream
    nodes can gracefully produce empty outputs.

    Parameters
    ----------
    state:
        Current graph state.

    Returns
    -------
    list[str]
        List of node names to fan out to.
    """
    return ["summarizer", "risk_analyzer"]


def route_after_hitl_gate(
    state: GraphState,
) -> Literal["report_generator"]:
    """Route from the HITL gate to the report generator.

    After the gate either passes automatically or resumes from a human
    interrupt, we always proceed to report generation.

    Parameters
    ----------
    state:
        Current graph state (post-HITL).

    Returns
    -------
    str
        Always ``"report_generator"``.
    """
    logger.info(
        "routing_to_report_generator",
        document_id=state["document_id"],
        human_feedback_present=bool(state.get("human_feedback")),
    )
    return "report_generator"
