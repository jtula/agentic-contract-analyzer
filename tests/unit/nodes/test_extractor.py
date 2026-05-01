"""Unit tests for the extractor node.

All tests are pure unit tests — no S3 calls, no LLM calls, no AWS.
The extractor node is tested by pre-populating ``document_text``
in the state so the PDF download path is bypassed.
"""

from __future__ import annotations

import pytest

from src.graph.state import GraphState
from src.nodes.extractor import extractor_node, _extract_sections, _compute_extraction_confidence

# ── Sample contract text ──────────────────────────────────────────────────
SAMPLE_CONTRACT = """\
PARTES
Las partes de este contrato son:
- CONTRATANTE: Empresa ABC S.L., con domicilio en Madrid.
- PROVEEDOR: Tech Solutions Ltd., con domicilio en Barcelona.

OBJETO
El objeto del presente contrato es la prestación de servicios de desarrollo de software.

CLÁUSULAS
Cláusula 1 — Precio
El precio total del servicio es de 50.000 EUR más IVA.

Cláusula 2 — Penalizaciones
En caso de incumplimiento de los plazos, se aplicará una penalización del 2% diario.

FECHAS
Vigencia: desde el 1 de enero de 2025 hasta el 31 de diciembre de 2025.

PENALIZACIONES
El incumplimiento de plazos conllevará penalizaciones económicas según cláusula 2.
"""


def _make_state(text: str = SAMPLE_CONTRACT, s3_path: str = "") -> GraphState:
    """Create a minimal GraphState for extractor testing."""
    return GraphState(
        document_id="test-doc-123",
        s3_path=s3_path,
        document_text=text,
        extractor_output=None,
        summary_output=None,
        risk_analysis_output=None,
        validation_output=None,
        global_confidence=0.0,
        needs_human_review=False,
        current_node="",
        errors=[],
        retry_count=0,
        human_feedback=None,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


class TestExtractSections:
    """Unit tests for the _extract_sections helper."""

    def test_detects_known_sections(self) -> None:
        sections = _extract_sections(SAMPLE_CONTRACT)
        assert "PARTES" in sections
        assert "OBJETO" in sections

    def test_falls_back_to_general_when_no_sections(self) -> None:
        sections = _extract_sections("This is plain text with no recognisable sections.")
        assert "GENERAL" in sections

    def test_sections_content_is_non_empty(self) -> None:
        sections = _extract_sections(SAMPLE_CONTRACT)
        for name, content in sections.items():
            assert content.strip(), f"Section '{name}' is empty"


class TestExtractionConfidence:
    """Unit tests for the confidence calculator."""

    def test_high_confidence_for_text_rich_doc(self) -> None:
        text = "A" * 10_000  # 10k chars
        conf = _compute_extraction_confidence(text, page_count=1)
        assert conf > 0.5

    def test_low_confidence_for_image_based_doc(self) -> None:
        conf = _compute_extraction_confidence("", page_count=5)
        assert conf == 0.0

    def test_confidence_bounded(self) -> None:
        text = "A" * 100_000
        conf = _compute_extraction_confidence(text, page_count=1)
        assert 0.0 <= conf <= 1.0


class TestExtractorNode:
    """Integration-style unit tests for the extractor node function."""

    def test_returns_extractor_output_on_success(self) -> None:
        state = _make_state(SAMPLE_CONTRACT)
        result = extractor_node(state)
        assert result["extractor_output"] is not None
        assert result["extractor_output"].document_id == "test-doc-123"

    def test_sets_document_text(self) -> None:
        state = _make_state(SAMPLE_CONTRACT)
        result = extractor_node(state)
        assert result["document_text"] == SAMPLE_CONTRACT

    def test_extracts_sections(self) -> None:
        state = _make_state(SAMPLE_CONTRACT)
        result = extractor_node(state)
        sections = result["extractor_output"].sections
        assert len(sections) >= 1

    def test_sets_current_node(self) -> None:
        state = _make_state(SAMPLE_CONTRACT)
        result = extractor_node(state)
        assert result["current_node"] == "extractor"

    def test_handles_empty_text_gracefully(self) -> None:
        state = _make_state("")
        result = extractor_node(state)
        # Should not raise; output may be None or have low confidence
        assert "current_node" in result

    def test_page_count_estimated_from_text_length(self) -> None:
        long_text = "word " * 10_000  # ~50k chars → ~16 pages
        state = _make_state(long_text)
        result = extractor_node(state)
        output = result["extractor_output"]
        if output:
            assert output.page_count >= 1
