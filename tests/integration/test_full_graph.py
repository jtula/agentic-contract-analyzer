"""Integration test — full graph run with mocked LLM.

Verifies that:
1. The graph runs end-to-end without raising.
2. Each node contributes its output to the final state.
3. The validator computes a confidence score.
4. Graceful degradation works when summarizer fails.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.graph.graph import build_graph
from src.models.risk import RiskAnalysisOutput, RiskCategory, RiskItem, Severity
from src.models.summarizer import SectionSummary, SummaryOutput

SAMPLE_CONTRACT = """\
PARTES
Contratante: Empresa ABC S.L.
Proveedor: Tech Solutions Ltd.

OBJETO
Desarrollo de software a medida durante 12 meses.

CLÁUSULAS
El precio total es 60.000 EUR.
Penalización del 2% diario por retraso sin límite máximo.

FECHAS
Inicio: 01/03/2025. Fin: 28/02/2026.
"""

MOCK_SUMMARY = SummaryOutput(
    document_id="integration-test",
    executive_summary=(
        "Contrato de desarrollo de software entre ABC S.L. y Tech Solutions Ltd. "
        "por 60.000 EUR durante 12 meses con penalizaciones por retraso."
    ),
    section_summaries=[
        SectionSummary(
            section_name="PARTES",
            summary="Empresa ABC S.L. y Tech Solutions Ltd.",
            key_points=["ABC S.L.", "Tech Solutions"],
            confidence=0.92,
        )
    ],
    key_parties=["Empresa ABC S.L.", "Tech Solutions Ltd."],
    contract_duration="12 meses",
    governing_law="España",
    overall_confidence=0.90,
)

MOCK_RISK = RiskAnalysisOutput(
    document_id="integration-test",
    risks=[
        RiskItem(
            risk_id="risk-1",
            description="Penalización diaria sin límite máximo",
            category=RiskCategory.FINANCIAL,
            severity=Severity.HIGH,
            confidence=0.92,
            clause_reference="Penalización del 2% diario por retraso sin límite máximo",
            recommendation="Establecer un límite máximo del 20% del valor del contrato.",
        )
    ],
    total_risks=1,
    risks_by_severity={"HIGH": 1},
    highest_severity=Severity.HIGH,
    analysis_timestamp="2025-01-01T00:00:00Z",
    overall_risk_score=0.55,
)


def _build_mock_llm() -> MagicMock:
    mock_llm = MagicMock()

    async def _smart_invoke(prompt, output_schema, node, document_id, system_prompt=None):
        """Return the right mock based on which node is calling."""
        if output_schema.__name__ == "SummaryOutput" or output_schema.__name__ == "SectionSummary":
            return MOCK_SUMMARY
        if output_schema.__name__ == "RiskAnalysisOutput":
            return MOCK_RISK
        return MagicMock()

    mock_llm.invoke_structured = AsyncMock(side_effect=_smart_invoke)
    return mock_llm


class TestFullGraphRun:
    @patch("src.nodes.summarizer.LLMService")
    @patch("src.nodes.risk_analyzer.LLMService")
    @patch("src.nodes.report_generator.S3Service")
    def test_graph_runs_end_to_end(
        self,
        mock_s3_cls: MagicMock,
        mock_risk_llm_cls: MagicMock,
        mock_sum_llm_cls: MagicMock,
    ) -> None:
        """Full graph run succeeds with mocked LLM and S3."""
        # Set up mocks
        mock_sum_llm_cls.return_value = _build_mock_llm()
        mock_risk_llm_cls.return_value = _build_mock_llm()
        mock_s3 = MagicMock()
        mock_s3.upload_report.return_value = (
            "s3://bucket/reports/test/report.json",
            "s3://bucket/reports/test/report.md",
        )
        mock_s3_cls.return_value = mock_s3

        graph = build_graph(checkpointer=None)
        initial_state = {
            "document_id": "integration-test",
            "s3_path": "",
            "document_text": SAMPLE_CONTRACT,
            "extractor_output": None,
            "summary_output": None,
            "risk_analysis_output": None,
            "validation_output": None,
            "global_confidence": 0.0,
            "needs_human_review": False,
            "current_node": "",
            "errors": [],
            "retry_count": 0,
            "human_feedback": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }

        final_state = graph.invoke(initial_state)

        assert final_state["extractor_output"] is not None, "Extractor should have run"
        assert final_state["summary_output"] is not None, "Summarizer should have run"
        assert final_state["risk_analysis_output"] is not None, "Risk analyzer should have run"
        assert final_state["validation_output"] is not None, "Validator should have run"
        assert 0.0 <= final_state["global_confidence"] <= 1.0

    @patch("src.nodes.summarizer.LLMService")
    @patch("src.nodes.risk_analyzer.LLMService")
    @patch("src.nodes.report_generator.S3Service")
    def test_graph_completes_when_summarizer_fails(
        self,
        mock_s3_cls: MagicMock,
        mock_risk_llm_cls: MagicMock,
        mock_sum_llm_cls: MagicMock,
    ) -> None:
        """Graph completes gracefully even if summarizer fails."""
        failing_llm = MagicMock()
        failing_llm.invoke_structured = AsyncMock(side_effect=RuntimeError("LLM down"))
        mock_sum_llm_cls.return_value = failing_llm

        mock_risk_llm_cls.return_value = _build_mock_llm()
        mock_s3 = MagicMock()
        mock_s3.upload_report.return_value = ("s3://x/r.json", "s3://x/r.md")
        mock_s3_cls.return_value = mock_s3

        graph = build_graph(checkpointer=None)
        initial_state = {
            "document_id": "integration-degraded",
            "s3_path": "",
            "document_text": SAMPLE_CONTRACT,
            "extractor_output": None,
            "summary_output": None,
            "risk_analysis_output": None,
            "validation_output": None,
            "global_confidence": 0.0,
            "needs_human_review": False,
            "current_node": "",
            "errors": [],
            "retry_count": 0,
            "human_feedback": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }

        # Should not raise despite summarizer failure
        final_state = graph.invoke(initial_state)
        assert final_state["summary_output"] is None
        assert any("summarizer" in e for e in final_state["errors"])
