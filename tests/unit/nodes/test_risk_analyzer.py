"""Unit tests for the risk analyzer node."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.graph.state import GraphState
from src.models.extractor import ExtractorOutput
from src.models.risk import RiskAnalysisOutput, RiskCategory, RiskItem, Severity
from src.nodes.risk_analyzer import risk_analyzer_node, _compute_risk_score

MOCK_RISK_OUTPUT = RiskAnalysisOutput(
    document_id="test-doc-123",
    risks=[
        RiskItem(
            risk_id="risk-1",
            description="Penalización del 2% diario sin límite máximo.",
            category=RiskCategory.FINANCIAL,
            severity=Severity.HIGH,
            confidence=0.92,
            clause_reference="Penalización del 2% diario",
            recommendation="Añadir un límite máximo del 20% del valor del contrato.",
        ),
        RiskItem(
            risk_id="risk-2",
            description="Cláusula de renovación automática sin notificación previa.",
            category=RiskCategory.TEMPORAL,
            severity=Severity.MEDIUM,
            confidence=0.78,
            clause_reference="renovación automática",
            recommendation="Establecer un período de preaviso de 30 días.",
        ),
    ],
    total_risks=2,
    risks_by_severity={"HIGH": 1, "MEDIUM": 1},
    highest_severity=Severity.HIGH,
    analysis_timestamp="2025-01-01T00:00:00Z",
    overall_risk_score=0.42,
)


def _make_state_with_text(text: str) -> GraphState:
    extractor_output = ExtractorOutput(
        document_id="test-doc-123",
        raw_text=text,
        page_count=2,
        sections={"GENERAL": text},
        identified_sections=[],
        extraction_confidence=0.85,
        extraction_warnings=[],
    )
    return GraphState(
        document_id="test-doc-123",
        s3_path="s3://bucket/test.pdf",
        document_text=text,
        extractor_output=extractor_output,
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


class TestComputeRiskScore:
    def test_no_risks_returns_zero(self) -> None:
        assert _compute_risk_score([]) == 0.0

    def test_single_critical_high_confidence(self) -> None:
        risk = RiskItem(
            risk_id="r1",
            description="Critical issue",
            category=RiskCategory.LEGAL,
            severity=Severity.CRITICAL,
            confidence=1.0,
            clause_reference="...",
            recommendation="Fix it",
        )
        score = _compute_risk_score([risk])
        assert score == 1.0

    def test_single_low_risk_low_score(self) -> None:
        risk = RiskItem(
            risk_id="r1",
            description="Minor issue",
            category=RiskCategory.OPERATIONAL,
            severity=Severity.LOW,
            confidence=0.5,
            clause_reference="...",
            recommendation="Note it",
        )
        score = _compute_risk_score([risk])
        assert score < 0.2


class TestRiskAnalyzerNode:
    @patch("src.nodes.risk_analyzer.LLMService")
    def test_returns_risk_output_on_success(self, mock_llm_cls: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke_structured = AsyncMock(return_value=MOCK_RISK_OUTPUT)
        mock_llm_cls.return_value = mock_llm

        state = _make_state_with_text("Penalización del 2% diario sin límite.")
        result = risk_analyzer_node(state)

        assert result["risk_analysis_output"] is not None
        assert result["risk_analysis_output"].total_risks == 2

    @patch("src.nodes.risk_analyzer.LLMService")
    def test_sets_current_node(self, mock_llm_cls: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke_structured = AsyncMock(return_value=MOCK_RISK_OUTPUT)
        mock_llm_cls.return_value = mock_llm

        state = _make_state_with_text("some contract text")
        result = risk_analyzer_node(state)
        assert result["current_node"] == "risk_analyzer"

    @patch("src.nodes.risk_analyzer.LLMService")
    def test_graceful_on_llm_failure(self, mock_llm_cls: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke_structured = AsyncMock(side_effect=ConnectionError("LLM unavailable"))
        mock_llm_cls.return_value = mock_llm

        state = _make_state_with_text("contract text")
        result = risk_analyzer_node(state)

        assert result["risk_analysis_output"] is None
        assert any("risk_analyzer" in e for e in result["errors"])

    def test_fails_when_no_text_available(self) -> None:
        state = GraphState(
            document_id="test-doc-123",
            s3_path="",
            document_text="",
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
        result = risk_analyzer_node(state)
        assert result["risk_analysis_output"] is None
        assert len(result["errors"]) > 0
