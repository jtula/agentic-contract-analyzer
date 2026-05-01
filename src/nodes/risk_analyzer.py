"""Risk Analyzer node — LLM-driven identification of contract risks.

Analyses the extracted contract text clause-by-clause to identify:
  - FINANCIAL: penalties, fines, hidden costs, liability caps
  - LEGAL: ambiguous clauses, one-sided terms, jurisdiction issues
  - TEMPORAL: auto-renewals, short notice periods, critical deadlines
  - COMPLIANCE: GDPR, data protection, sector regulations
  - OPERATIONAL: SLA gaps, force-majeure holes, delivery obligations

Each identified risk gets a severity (LOW/MEDIUM/HIGH/CRITICAL) and a
confidence score (0.0–1.0).

This node is designed to run in PARALLEL with the summarizer node via
LangGraph's Send() mechanism in the graph definition.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from src.graph.state import GraphState
from src.models.risk import RiskAnalysisOutput, RiskCategory, RiskItem, Severity
from src.services.llm_service import get_llm_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are an expert legal risk analyst specialising in contract review.
Identify ALL risks, ambiguities, and problematic clauses in the contract text provided.
For every risk found:
  - Describe it clearly and specifically
  - Assign a category: FINANCIAL, LEGAL, TEMPORAL, COMPLIANCE, or OPERATIONAL
  - Assign severity: LOW, MEDIUM, HIGH, or CRITICAL
  - Quote the exact clause that contains the risk
  - Provide a concrete, actionable recommendation
  - Assign confidence (0.0–1.0) that this is a genuine risk

Be thorough. Missing a CRITICAL risk is worse than flagging a false positive.
Respond ONLY with the RiskAnalysisOutput JSON schema — no prose outside the schema.
"""

_RISK_PROMPT_TEMPLATE = """\
Analyse the following contract text for risks.

Contract text:
---
{text}
---

Document ID: {document_id}
Analysis timestamp: {timestamp}

Produce a complete RiskAnalysisOutput. 
- risk_id: generate as "risk-<index>" (e.g. "risk-1", "risk-2")
- overall_risk_score: 0.0 (no risk) to 1.0 (extreme risk)
- risks_by_severity: count risks per severity label
- highest_severity: the most severe single risk found
"""


def _severity_to_weight(severity: Severity) -> float:
    """Map severity level to a numeric weight for score computation."""
    weights = {
        Severity.LOW: 0.1,
        Severity.MEDIUM: 0.3,
        Severity.HIGH: 0.6,
        Severity.CRITICAL: 1.0,
    }
    return weights[severity]


def _compute_risk_score(risks: list[RiskItem]) -> float:
    """Compute a normalised composite risk score from individual risks."""
    if not risks:
        return 0.0
    weighted_sum = sum(
        _severity_to_weight(r.severity) * r.confidence for r in risks
    )
    # Normalise: divide by max possible (all CRITICAL with confidence=1)
    max_possible = len(risks) * 1.0
    return round(min(1.0, weighted_sum / max_possible), 3)


async def _run_risk_analysis(document_id: str, text: str) -> RiskAnalysisOutput:
    """Async implementation of risk analysis."""
    llm = get_llm_service()
    timestamp = datetime.now(timezone.utc).isoformat()

    prompt = _RISK_PROMPT_TEMPLATE.format(
        text=text[:10000],
        document_id=document_id,
        timestamp=timestamp,
    )

    output = await llm.invoke_structured(
        prompt=prompt,
        output_schema=RiskAnalysisOutput,
        node="risk_analyzer",
        document_id=document_id,
        system_prompt=_SYSTEM_PROMPT,
    )

    # Recalculate derived fields to ensure consistency
    risks_by_severity: dict[str, int] = {}
    for r in output.risks:
        risks_by_severity[r.severity.value] = risks_by_severity.get(r.severity.value, 0) + 1

    highest = (
        max(output.risks, key=lambda r: list(Severity).index(r.severity)).severity
        if output.risks
        else Severity.LOW
    )

    # Rebuild with corrected derived fields
    return RiskAnalysisOutput(
        document_id=document_id,
        risks=output.risks,
        total_risks=len(output.risks),
        risks_by_severity=risks_by_severity,
        highest_severity=highest,
        analysis_timestamp=timestamp,
        overall_risk_score=_compute_risk_score(output.risks),
    )


def _run_async(coro: Any) -> Any:
    """Run *coro* in the current event loop or create a new one.

    Uses ``asyncio.get_running_loop()`` (Python 3.10+) instead of the
    deprecated ``asyncio.get_event_loop()`` to detect whether we are already
    inside a running loop (e.g. FastAPI/uvicorn).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        import nest_asyncio  # type: ignore[import]
        nest_asyncio.apply()
        return loop.run_until_complete(coro)


def risk_analyzer_node(state: GraphState) -> dict[str, Any]:
    """Identify and classify all risks in the contract.

    Parameters
    ----------
    state:
        Current graph state. Reads ``extractor_output`` for the contract text.

    Returns
    -------
    dict
        Keys updated: ``current_node``, ``risk_analysis_output``, ``updated_at``,
        and optionally ``errors``.
    """
    document_id = state["document_id"]
    logger.info("node_started", node="risk_analyzer", document_id=document_id)

    updates: dict[str, Any] = {
        "current_node": "risk_analyzer",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        extractor_output = state.get("extractor_output")
        text = (
            extractor_output.raw_text
            if extractor_output
            else state.get("document_text", "")
        )

        if not text.strip():
            raise ValueError("No contract text available for risk analysis.")

        output = _run_async(_run_risk_analysis(document_id, text))
        updates["risk_analysis_output"] = output

        logger.info(
            "node_completed",
            node="risk_analyzer",
            document_id=document_id,
            total_risks=output.total_risks,
            highest_severity=output.highest_severity.value,
            risk_score=output.overall_risk_score,
        )

    except Exception as exc:
        error_msg = f"risk_analyzer_node failed: {exc!s}"
        logger.error("node_failed", node="risk_analyzer", document_id=document_id, error=str(exc))
        updates["errors"] = [*state.get("errors", []), error_msg]
        updates["risk_analysis_output"] = None

    return updates
