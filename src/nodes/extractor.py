"""Extractor node — PDF text extraction and section segmentation.

This node is the entry point of the graph. It:

1. Downloads the PDF from S3 (via S3Service).
2. Extracts clean text using PyMuPDF (fitz).
3. Heuristically segments the text into named sections.
4. Returns an ExtractorOutput Pydantic model.

If extraction fails after retries, the node logs the error, appends it to
``state["errors"]``, and returns ``extractor_output=None`` so downstream
nodes can degrade gracefully instead of crashing the whole graph.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from src.graph.state import GraphState
from src.models.extractor import DocumentSection, ExtractorOutput
from src.services.s3_service import S3Service
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Section headers we try to detect (order matters — more specific first)
_SECTION_PATTERNS: list[tuple[str, list[str]]] = [
    ("PARTES", ["partes", "las partes", "contratantes", "parties"]),
    ("OBJETO", ["objeto", "objeto del contrato", "scope", "purpose"]),
    ("CLÁUSULAS", ["cláusulas", "clausulas", "condiciones", "terms and conditions"]),
    ("PENALIZACIONES", ["penalizaciones", "penalidades", "penalties", "sanciones"]),
    ("FECHAS", ["vigencia", "duración", "plazo", "term", "duration"]),
    ("CONFIDENCIALIDAD", ["confidencialidad", "confidentiality", "nda"]),
    ("RESPONSABILIDAD", ["responsabilidad", "liability", "indemnización"]),
    ("RESOLUCIÓN", ["resolución", "rescisión", "termination", "terminación"]),
]

# Hard cap on extracted text stored in graph state.
# DynamoDB items are limited to 400 KB; staying well under that limit also
# prevents downstream nodes from receiving unexpectedly large payloads.
_MAX_TEXT_CHARS = 300_000


def _extract_sections(text: str) -> dict[str, str]:
    """Heuristically split *text* into named contract sections.

    Looks for uppercase headings or known keywords at the start of lines.
    If no sections are detected, returns the full text under the key "GENERAL"
    so downstream nodes always have something to work with.

    Parameters
    ----------
    text:
        Full raw text from the PDF.

    Returns
    -------
    dict[str, str]
        Mapping of section name → section text.
    """
    sections: dict[str, str] = {}
    lines = text.split("\n")

    # Build a simple line-number → section-name map.
    # Use seen_indices (set) for O(1) duplicate checking instead of
    # rebuilding a dict from the list on every iteration.
    section_starts: list[tuple[int, str]] = []
    seen_indices: set[int] = set()
    for idx, line in enumerate(lines):
        normalized = line.strip().lower()
        for section_name, keywords in _SECTION_PATTERNS:
            if any(normalized.startswith(kw) for kw in keywords):
                section_starts.append((idx, section_name))
                seen_indices.add(idx)
                break
        # Also detect ALL-CAPS headings with at least 4 chars
        if line.strip().isupper() and len(line.strip()) >= 4 and idx not in seen_indices:
            section_starts.append((idx, line.strip()[:30]))
            seen_indices.add(idx)

    if not section_starts:
        return {"GENERAL": text}

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_starts: list[tuple[int, str]] = []
    for start_idx, name in section_starts:
        if name not in seen:
            seen.add(name)
            unique_starts.append((start_idx, name))

    for i, (start_idx, name) in enumerate(unique_starts):
        end_idx = unique_starts[i + 1][0] if i + 1 < len(unique_starts) else len(lines)
        sections[name] = "\n".join(lines[start_idx:end_idx]).strip()

    return sections


def _build_document_sections(
    sections: dict[str, str],
    lines_per_page: int = 50,
) -> list[DocumentSection]:
    """Convert a sections dict into DocumentSection objects with page estimates.

    Page numbers are estimated based on average lines-per-page.
    """
    result: list[DocumentSection] = []
    current_line = 0
    for name, content in sections.items():
        line_count = content.count("\n") + 1
        start_page = max(1, current_line // lines_per_page + 1)
        end_page = max(start_page, (current_line + line_count) // lines_per_page + 1)
        result.append(
            DocumentSection(
                name=name,
                content=content,
                start_page=start_page,
                end_page=end_page,
            )
        )
        current_line += line_count
    return result


def _compute_extraction_confidence(text: str, page_count: int) -> float:
    """Estimate extraction quality based on content heuristics.

    Penalises very short text relative to page count (image-based PDFs)
    and high ratios of non-printable characters.
    """
    if not text:
        return 0.0

    avg_chars_per_page = len(text) / max(page_count, 1)
    # Typical text PDF has ~2000+ chars/page; image-based ~50
    content_score = min(1.0, avg_chars_per_page / 2000)

    printable = sum(1 for c in text if c.isprintable() or c in "\n\t")
    printable_ratio = printable / len(text)

    return round((content_score * 0.6) + (printable_ratio * 0.4), 3)


def extractor_node(state: GraphState) -> dict[str, Any]:
    """Extract and segment text from the contract PDF.

    Reads ``state["s3_path"]`` (or falls back to ``state["document_text"]``
    if already populated), processes the PDF with PyMuPDF, and returns
    the ``extractor_output`` key.

    Parameters
    ----------
    state:
        Current graph state.

    Returns
    -------
    dict
        Keys updated: ``current_node``, ``document_text``, ``extractor_output``,
        ``updated_at``, and optionally ``errors``.
    """
    document_id = state["document_id"]
    logger.info("node_started", node="extractor", document_id=document_id)

    updates: dict[str, Any] = {
        "current_node": "extractor",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        import fitz  # PyMuPDF

        # Download PDF from S3 (or use pre-populated text for testing)
        raw_text = state.get("document_text", "")
        page_count = 1
        warnings: list[str] = []

        if state.get("s3_path") and not raw_text:
            s3 = S3Service()
            pdf_bytes = s3.download_document(state["s3_path"])

            doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
            page_count = len(doc)
            pages_text: list[str] = []

            for page_num, page in enumerate(doc, start=1):
                page_text = page.get_text("text")  # type: ignore[attr-defined]
                if not page_text.strip():
                    warnings.append(f"Page {page_num} appears to be image-based (no text layer).")
                pages_text.append(page_text)

            doc.close()
            raw_text = "\n".join(pages_text)

        elif raw_text:
            # Text was pre-populated (e.g. in tests or direct text upload)
            page_count = max(1, len(raw_text) // 3000)

        # Guard against very large documents that could exceed the DynamoDB
        # 400 KB item limit when stored as graph state via the checkpointer.
        if len(raw_text) > _MAX_TEXT_CHARS:
            logger.warning(
                "document_text_truncated",
                document_id=document_id,
                original_chars=len(raw_text),
                truncated_to=_MAX_TEXT_CHARS,
            )
            raw_text = raw_text[:_MAX_TEXT_CHARS]

        sections = _extract_sections(raw_text)
        detailed_sections = _build_document_sections(sections)
        confidence = _compute_extraction_confidence(raw_text, page_count)

        output = ExtractorOutput(
            document_id=document_id,
            raw_text=raw_text,
            page_count=page_count,
            sections=sections,
            identified_sections=detailed_sections,
            extraction_confidence=confidence,
            extraction_warnings=warnings,
        )

        updates["document_text"] = raw_text
        updates["extractor_output"] = output

        logger.info(
            "node_completed",
            node="extractor",
            document_id=document_id,
            page_count=page_count,
            sections_found=len(sections),
            confidence=confidence,
        )

    except Exception as exc:
        error_msg = f"extractor_node failed: {exc!s}"
        logger.error("node_failed", node="extractor", document_id=document_id, error=str(exc))
        updates["errors"] = [*state.get("errors", []), error_msg]
        updates["extractor_output"] = None

    return updates
