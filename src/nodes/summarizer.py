"""Summarizer node — LLM-powered section-by-section contract summary.

Receives the extractor output and produces a structured summary using the
LLM with ``.with_structured_output(SummaryOutput)`` to enforce the schema.

Sections are processed concurrently with ``asyncio.gather()`` when there
are more than three, keeping latency low for large contracts.

Because LangGraph nodes must be synchronous by default (unless configured
otherwise), the async work is run inside ``asyncio.run()`` or the event loop
if one already exists.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from src.graph.state import GraphState
from src.models.summarizer import SectionSummary, SummaryOutput
from src.services.llm_service import get_llm_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a senior legal analyst specialising in contract review.
Your task is to produce a precise, structured summary of a contract section.
Be concise, factual, and highlight anything that requires attention.
Always respond in the same language as the contract text.
"""

_SECTION_PROMPT_TEMPLATE = """\
Contract section: {section_name}

Section text:
---
{section_text}
---

Produce a structured summary for this section following the SectionSummary schema exactly.
Set confidence between 0.0 and 1.0 based on how clear and unambiguous the section is.
"""

_MAX_SECTION_CHARS = 6_000
_MAX_EXEC_SUMMARY_CHARS = 8_000

_EXECUTIVE_SUMMARY_PROMPT = """\
You are a senior legal analyst. Given the following contract text, produce:
1. A concise executive summary (3-5 sentences).
2. A list of the contracting parties.
3. The contract duration / expiry date if stated.
4. The governing law / jurisdiction if stated.

Contract text:
---
{text}
---

Respond using the SummaryOutput schema. Set overall_confidence between 0.0 and 1.0.
section_summaries can be an empty list — we fill it separately.
"""


async def _summarise_section(
    llm: Any,
    section_name: str,
    section_text: str,
    document_id: str,
) -> SectionSummary:
    """Summarise a single section and return a SectionSummary model."""
    if len(section_text) > _MAX_SECTION_CHARS:
        logger.warning(
            "section_text_truncated",
            document_id=document_id,
            section_name=section_name,
            original_chars=len(section_text),
            truncated_to=_MAX_SECTION_CHARS,
        )
    prompt = _SECTION_PROMPT_TEMPLATE.format(
        section_name=section_name,
        section_text=section_text[:_MAX_SECTION_CHARS],
    )
    result = await llm.invoke_structured(
        prompt=prompt,
        output_schema=SectionSummary,
        node="summarizer",
        document_id=document_id,
        system_prompt=_SYSTEM_PROMPT,
    )
    return result


async def _run_summarizer(
    document_id: str,
    sections: dict[str, str],
    raw_text: str,
) -> SummaryOutput:
    """Async implementation of the summarizer node logic."""
    llm = get_llm_service()

    # Executive summary first (includes party, duration, governing law)
    exec_prompt = _EXECUTIVE_SUMMARY_PROMPT.format(text=raw_text[:_MAX_EXEC_SUMMARY_CHARS])
    base_output = await llm.invoke_structured(
        prompt=exec_prompt,
        output_schema=SummaryOutput,
        node="summarizer",
        document_id=document_id,
        system_prompt=_SYSTEM_PROMPT,
    )

    # Parallel section summaries
    tasks = [
        _summarise_section(llm, name, text, document_id)
        for name, text in sections.items()
        if text.strip()
    ]
    section_summaries: list[SectionSummary] = await asyncio.gather(*tasks)

    # Compute aggregate confidence
    confidences = [s.confidence for s in section_summaries]
    avg_confidence = sum(confidences) / len(confidences) if confidences else base_output.overall_confidence

    # Rebuild the output with section summaries populated
    return SummaryOutput(
        document_id=document_id,
        executive_summary=base_output.executive_summary,
        section_summaries=list(section_summaries),
        key_parties=base_output.key_parties,
        contract_duration=base_output.contract_duration,
        governing_law=base_output.governing_law,
        overall_confidence=round(avg_confidence, 3),
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
        # No running loop — safe to create one with asyncio.run()
        return asyncio.run(coro)
    else:
        # Already inside a running loop (FastAPI/uvicorn).
        # nest_asyncio patches the loop to allow re-entrant run_until_complete().
        import nest_asyncio  # type: ignore[import]
        nest_asyncio.apply()
        return loop.run_until_complete(coro)


def summarizer_node(state: GraphState) -> dict[str, Any]:
    """Summarise the contract using the LLM with structured output.

    Parameters
    ----------
    state:
        Current graph state. Reads ``extractor_output`` for sections.

    Returns
    -------
    dict
        Keys updated: ``current_node``, ``summary_output``, ``updated_at``,
        and optionally ``errors``.
    """
    document_id = state["document_id"]
    logger.info("node_started", node="summarizer", document_id=document_id)

    updates: dict[str, Any] = {
        "current_node": "summarizer",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        extractor_output = state.get("extractor_output")
        if extractor_output is None:
            logger.warning(
                "summarizer_using_raw_text",
                document_id=document_id,
                reason="extractor_output is None",
            )
            sections = {"GENERAL": state.get("document_text", "")}
            raw_text = state.get("document_text", "")
        else:
            sections = extractor_output.sections or {"GENERAL": extractor_output.raw_text}
            raw_text = extractor_output.raw_text

        output = _run_async(_run_summarizer(document_id, sections, raw_text))
        updates["summary_output"] = output

        logger.info(
            "node_completed",
            node="summarizer",
            document_id=document_id,
            sections=len(output.section_summaries),
            confidence=output.overall_confidence,
        )

    except Exception as exc:
        error_msg = f"summarizer_node failed: {exc!s}"
        logger.error("node_failed", node="summarizer", document_id=document_id, error=str(exc))
        updates["errors"] = [*state.get("errors", []), error_msg]
        updates["summary_output"] = None

    return updates
