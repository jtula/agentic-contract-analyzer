"""Validator node — cross-reference summarizer and risk analyzer outputs.

Responsibilities:
1. Verify that each identified risk has textual evidence in the contract.
2. Check for contradictions between summaries and risks.
3. Calculate the global confidence score:
       global_confidence = (summary_confidence * 0.3) + (avg_risk_confidence * 0.7)
4. Set ``needs_human_review = True`` if:
   - global_confidence < CONFIDENCE_THRESHOLD (default 0.75), OR
   - any risk has severity == CRITICAL.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from src.graph.state import GraphState
from src.models.risk import Severity
from src.models.validator import CrossReference, ValidationOutput
from src.utils.logger import get_logger

logger = get_logger(__name__)

_CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))


def _verify_clause_in_text(clause_reference: str, document_text: str) -> bool:
    """Check whether *clause_reference* text appears in *document_text*.

    Uses a simple substring match after normalising whitespace. A more
    sophisticated implementation could use fuzzy matching or embeddings.

    Parameters
    ----------
    clause_reference:
        Quoted clause text from the risk item.
    document_text:
        Full contract text from the extractor.

    Returns
    -------
    bool
        True if the reference appears in the document.
    """
    if not clause_reference or not document_text:
        return False
    # Normalise: collapse whitespace and lowercase both sides
    norm_ref = " ".join(clause_reference.lower().split())
    norm_doc = " ".join(document_text.lower().split())
    # Accept partial match (first 60 chars of the reference)
    fragment = norm_ref[:60].strip()
    return fragment in norm_doc if fragment else False


def validator_node(state: GraphState) -> dict[str, Any]:
    """Cross-reference and validate the summarizer + risk analyzer outputs.

    Parameters
    ----------
    state:
        Current graph state.

    Returns
    -------
    dict
        Keys updated: ``current_node``, ``validation_output``, ``global_confidence``,
        ``needs_human_review``, ``updated_at``, and optionally ``errors``.
    """
    document_id = state["document_id"]
    logger.info("node_started", node="validator", document_id=document_id)

    updates: dict[str, Any] = {
        "current_node": "validator",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        summary_output = state.get("summary_output")
        risk_output = state.get("risk_analysis_output")
        document_text = state.get("document_text", "")

        # ── Confidence calculation ─────────────────────────────────────────
        summary_confidence = (
            summary_output.overall_confidence if summary_output else 0.5
        )

        if risk_output and risk_output.risks:
            avg_risk_confidence = sum(r.confidence for r in risk_output.risks) / len(
                risk_output.risks
            )
        else:
            avg_risk_confidence = 0.5  # no risks found — moderate confidence

        # Penalise if either node completely failed
        if summary_output is None:
            summary_confidence = 0.3
        if risk_output is None:
            avg_risk_confidence = 0.3

        global_confidence = round(
            (summary_confidence * 0.3) + (avg_risk_confidence * 0.7), 3
        )

        # ── Cross-reference checks ─────────────────────────────────────────
        cross_refs: list[CrossReference] = []
        unverified_ids: list[str] = []

        if risk_output:
            for risk in risk_output.risks:
                clause_found = _verify_clause_in_text(
                    risk.clause_reference, document_text
                )
                summary_aligned = True  # default — we don't have deep NLI here
                discrepancy: str | None = None

                if not clause_found:
                    summary_aligned = False
                    discrepancy = (
                        f"Clause reference for risk '{risk.risk_id}' not found in document text."
                    )
                    unverified_ids.append(risk.risk_id)

                cross_refs.append(
                    CrossReference(
                        risk_id=risk.risk_id,
                        clause_found_in_text=clause_found,
                        summary_aligned=summary_aligned,
                        discrepancy_note=discrepancy,
                    )
                )

        # ── HITL decision ──────────────────────────────────────────────────
        has_critical = (
            risk_output is not None
            and any(r.severity == Severity.CRITICAL for r in risk_output.risks)
        )
        needs_review = global_confidence < _CONFIDENCE_THRESHOLD or has_critical

        review_reason: str | None = None
        if needs_review:
            reasons: list[str] = []
            if global_confidence < _CONFIDENCE_THRESHOLD:
                reasons.append(
                    f"global_confidence={global_confidence:.2f} < threshold={_CONFIDENCE_THRESHOLD}"
                )
            if has_critical:
                reasons.append("one or more CRITICAL severity risks detected")
            review_reason = "; ".join(reasons)

        output = ValidationOutput(
            document_id=document_id,
            cross_references=cross_refs,
            unverified_risk_ids=unverified_ids,
            global_confidence=global_confidence,
            needs_human_review=needs_review,
            review_reason=review_reason,
            validation_timestamp=datetime.now(timezone.utc).isoformat(),
        )

        updates["validation_output"] = output
        updates["global_confidence"] = global_confidence
        updates["needs_human_review"] = needs_review

        logger.info(
            "node_completed",
            node="validator",
            document_id=document_id,
            global_confidence=global_confidence,
            needs_human_review=needs_review,
            unverified_risks=len(unverified_ids),
        )

    except Exception as exc:
        error_msg = f"validator_node failed: {exc!s}"
        logger.error("node_failed", node="validator", document_id=document_id, error=str(exc))
        updates["errors"] = [*state.get("errors", []), error_msg]
        updates["validation_output"] = None
        # Default to requiring review when validator fails
        updates["global_confidence"] = 0.0
        updates["needs_human_review"] = True

    return updates
