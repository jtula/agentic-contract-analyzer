"""HITL Gate node — Human-in-the-Loop interrupt point.

This node uses LangGraph's ``interrupt()`` primitive to PAUSE the graph
when the validator decides that human review is required.

Flow
----
- If ``needs_human_review == False``  →  node is a no-op, graph continues.
- If ``needs_human_review == True``   →  ``interrupt()`` pauses the run and
  surfaces the current state to the API layer, which exposes it via
  ``GET /runs/{run_id}``.
  A human then calls ``POST /analyze/{run_id}/resume`` with feedback JSON.
  LangGraph resumes from the checkpoint with ``Command(resume=feedback)``.

The human can:
  - Approve as-is (empty feedback or ``{"action": "approve"}``)
  - Reject / flag for manual processing (``{"action": "reject"}``)
  - Add context (``{"action": "approve", "notes": "Reviewed with legal team…"}``)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.graph.state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


def hitl_gate_node(state: GraphState) -> dict[str, Any]:
    """Conditionally pause the graph for human review.

    Uses ``langgraph.types.interrupt`` to suspend execution and surface the
    current analysis state to the API consumer.

    Parameters
    ----------
    state:
        Current graph state.

    Returns
    -------
    dict
        Keys updated: ``current_node``, ``human_feedback``, ``updated_at``.
        If interrupted, the function does NOT return until the graph is
        resumed — LangGraph handles the suspend/resume transparently.
    """
    document_id = state["document_id"]
    logger.info("node_started", node="hitl_gate", document_id=document_id)

    updates: dict[str, Any] = {
        "current_node": "hitl_gate",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not state.get("needs_human_review", False):
        logger.info(
            "hitl_gate_passed",
            document_id=document_id,
            global_confidence=state.get("global_confidence"),
        )
        return updates

    # ── Interrupt: pause and wait for human input ──────────────────────────
    from langgraph.types import interrupt  # type: ignore[import]

    risk_output = state.get("risk_analysis_output")
    validation_output = state.get("validation_output")

    interrupt_payload = {
        "reason": (
            validation_output.review_reason
            if validation_output
            else None
        ) or "Low confidence or critical risk detected",
        "global_confidence": state.get("global_confidence", 0.0),
        "total_risks": risk_output.total_risks if risk_output else 0,
        "highest_severity": (
            risk_output.highest_severity.value if risk_output else "UNKNOWN"
        ),
        "critical_risks": [
            {
                "risk_id": r.risk_id,
                "description": r.description,
                "clause_reference": r.clause_reference,
                "recommendation": r.recommendation,
            }
            for r in (risk_output.risks if risk_output else [])
            if r.severity.value == "CRITICAL"
        ],
        "unverified_risk_ids": (
            validation_output.unverified_risk_ids if validation_output else []
        ),
    }

    logger.warning(
        "hitl_interrupt_triggered",
        document_id=document_id,
        reason=interrupt_payload["reason"],
        global_confidence=interrupt_payload["global_confidence"],
    )

    # This call PAUSES the graph — execution resumes here after human feedback
    human_feedback: Any = interrupt(interrupt_payload)

    logger.info(
        "hitl_resumed",
        document_id=document_id,
        feedback_received=bool(human_feedback),
    )

    updates["human_feedback"] = (
        human_feedback if isinstance(human_feedback, str)
        else json.dumps(human_feedback) if isinstance(human_feedback, dict)
        else str(human_feedback)
    )
    return updates
