"""Unit tests for the summarizer node.

The LLM is mocked so tests run without API keys or internet access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.graph.state import GraphState
from src.models.extractor import ExtractorOutput
from src.models.summarizer import SectionSummary, SummaryOutput
from src.nodes.summarizer import summarizer_node

SAMPLE_SECTIONS = {
    "PARTES": "Las partes son ABC S.L. y Tech Solutions Ltd.",
    "OBJETO": "Prestación de servicios de desarrollo de software.",
    "CLÁUSULAS": "El precio es 50.000 EUR. Penalización del 2% por día de retraso.",
}

MOCK_SECTION_SUMMARY = SectionSummary(
    section_name="PARTES",
    summary="Las partes son ABC S.L. y Tech Solutions Ltd.",
    key_points=["ABC S.L.", "Tech Solutions Ltd."],
    confidence=0.9,
)

MOCK_SUMMARY_OUTPUT = SummaryOutput(
    document_id="test-doc-123",
    executive_summary="Este es un contrato de servicios de software entre dos partes.",
    section_summaries=[MOCK_SECTION_SUMMARY],
    key_parties=["ABC S.L.", "Tech Solutions Ltd."],
    contract_duration="12 meses",
    governing_law="España",
    overall_confidence=0.88,
)


def _make_state_with_extractor(sections: dict[str, str]) -> GraphState:
    extractor_output = ExtractorOutput(
        document_id="test-doc-123",
        raw_text="\n".join(sections.values()),
        page_count=3,
        sections=sections,
        identified_sections=[],
        extraction_confidence=0.9,
        extraction_warnings=[],
    )
    return GraphState(
        document_id="test-doc-123",
        s3_path="s3://bucket/test.pdf",
        document_text="\n".join(sections.values()),
        extractor_output=extractor_output,
        summary_output=None,
        risk_analysis_output=None,
        validation_output=None,
        global_confidence=0.0,
        needs_human_review=False,
        current_node="summarizer",
        errors=[],
        retry_count=0,
        human_feedback=None,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


class TestSummarizerNode:
    @patch("src.nodes.summarizer.LLMService")
    def test_returns_summary_output(self, mock_llm_cls: MagicMock) -> None:
        """Node returns a populated SummaryOutput when LLM succeeds."""
        mock_llm = MagicMock()
        mock_llm.invoke_structured = AsyncMock(return_value=MOCK_SUMMARY_OUTPUT)
        mock_llm_cls.return_value = mock_llm

        state = _make_state_with_extractor(SAMPLE_SECTIONS)
        result = summarizer_node(state)

        assert result["summary_output"] is not None
        assert result["summary_output"].document_id == "test-doc-123"

    @patch("src.nodes.summarizer.LLMService")
    def test_sets_current_node(self, mock_llm_cls: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke_structured = AsyncMock(return_value=MOCK_SUMMARY_OUTPUT)
        mock_llm_cls.return_value = mock_llm

        state = _make_state_with_extractor(SAMPLE_SECTIONS)
        result = summarizer_node(state)
        assert result["current_node"] == "summarizer"

    @patch("src.nodes.summarizer.LLMService")
    def test_graceful_degradation_on_llm_error(self, mock_llm_cls: MagicMock) -> None:
        """Node sets summary_output=None and appends error on LLM failure."""
        mock_llm = MagicMock()
        mock_llm.invoke_structured = AsyncMock(side_effect=RuntimeError("LLM down"))
        mock_llm_cls.return_value = mock_llm

        state = _make_state_with_extractor(SAMPLE_SECTIONS)
        result = summarizer_node(state)

        assert result["summary_output"] is None
        assert any("summarizer" in e for e in result["errors"])

    @patch("src.nodes.summarizer.LLMService")
    def test_falls_back_to_raw_text_when_extractor_output_is_none(
        self, mock_llm_cls: MagicMock
    ) -> None:
        """Summarizer uses document_text when extractor_output is None."""
        mock_llm = MagicMock()
        mock_llm.invoke_structured = AsyncMock(return_value=MOCK_SUMMARY_OUTPUT)
        mock_llm_cls.return_value = mock_llm

        state = GraphState(
            document_id="test-doc-123",
            s3_path="",
            document_text="Raw contract text without sections.",
            extractor_output=None,  # simulate extractor failure
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
        result = summarizer_node(state)
        # Should not raise
        assert "current_node" in result
