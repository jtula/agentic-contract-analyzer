"""Unit tests for the validator node."""

from __future__ import annotations

import pytest

from src.graph.state import GraphState
from src.models.extractor import ExtractorOutput
from src.models.risk import RiskAnalysisOutput, RiskCategory, RiskItem, Severity
from src.models.summarizer import SectionSummary, SummaryOutput
from src.nodes.validator import validator_node, _verify_clause_in_text

DOCUMENT_TEXT = """\
PARTES: ABC S.L. y Tech Solutions Ltd.
OBJETO: Desarrollo de software por 50.000 EUR.
Penalización del 2% diario en caso de retraso.
Renovación automática si no se cancela con 30 días de preaviso.
"""

SUMMARY_OUTPUT = SummaryOutput(
    document_id="test-doc-123",
    executive_summary="Contrato de desarrollo de software entre ABC S.L. y Tech Solutions.",
    section_summaries=[],
    key_parties=["ABC S.L.", "Tech Solutions Ltd."],
    contract_duration="12 meses",
    governing_law="España",
    overall_confidence=0.88,
)

RISK_OUTPUT_HIGH_CONFIDENCE = RiskAnalysisOutput(
    document_id="test-doc-123",
    risks=[
        RiskItem(
            risk_id="risk-1",
            description="Penalización diaria sin límite",
            category=RiskCategory.FINANCIAL,
            severity=Severity.HIGH,
            confidence=0.9,
            clause_reference="Penalización del 2% diario",
            recommendation="Limitar al 20%",
        )
    ],
    total_risks=1,
    risks_by_severity={"HIGH": 1},
    highest_severity=Severity.HIGH,
    analysis_timestamp="2025-01-01T00:00:00Z",
    overall_risk_score=0.54,
)

RISK_OUTPUT_CRITICAL = RiskAnalysisOutput(
    document_id="test-doc-123",
    risks=[
        RiskItem(
            risk_id="risk-crit",
            description="Cláusula abusiva",
            category=RiskCategory.LEGAL,
            severity=Severity.CRITICAL,
            confidence=0.95,
            clause_reference="Penalización del 2% diario",
            recommendation="Negociar cláusula",
        )
    ],
    total_risks=1,
    risks_by_severity={"CRITICAL": 1},
    highest_severity=Severity.CRITICAL,
    analysis_timestamp="2025-01-01T00:00:00Z",
    overall_risk_score=0.95,
)


def _make_state(
    summary=SUMMARY_OUTPUT,
    risk=RISK_OUTPUT_HIGH_CONFIDENCE,
    text=DOCUMENT_TEXT,
) -> GraphState:
    return GraphState(
        document_id="test-doc-123",
        s3_path="s3://bucket/test.pdf",
        document_text=text,
        extractor_output=None,
        summary_output=summary,
        risk_analysis_output=risk,
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


class TestVerifyClauseInText:
    def test_found_exact_phrase(self) -> None:
        assert _verify_clause_in_text("Penalización del 2% diario", DOCUMENT_TEXT) is True

    def test_not_found_phrase(self) -> None:
        assert _verify_clause_in_text("fuerza mayor", DOCUMENT_TEXT) is False

    def test_empty_reference_returns_false(self) -> None:
        assert _verify_clause_in_text("", DOCUMENT_TEXT) is False


class TestValidatorNode:
    def test_computes_global_confidence(self) -> None:
        state = _make_state()
        result = validator_node(state)
        output = result["validation_output"]
        assert output is not None
        assert 0.0 <= output.global_confidence <= 1.0

    def test_does_not_require_review_for_high_confidence(self) -> None:
        """When confidence is high and no CRITICAL risks, review is not needed."""
        # Force high confidence by providing high-quality mock outputs
        state = _make_state(
            summary=SummaryOutput(
                document_id="test-doc-123",
                executive_summary="High quality summary with detailed analysis of all clauses.",
                section_summaries=[],
                key_parties=["A", "B"],
                contract_duration=None,
                governing_law=None,
                overall_confidence=0.95,
            ),
            risk=RiskAnalysisOutput(
                document_id="test-doc-123",
                risks=[
                    RiskItem(
                        risk_id="r1",
                        description="Minor formatting issue",
                        category=RiskCategory.OPERATIONAL,
                        severity=Severity.LOW,
                        confidence=0.95,
                        clause_reference="Penalización del 2% diario",
                        recommendation="No action needed",
                    )
                ],
                total_risks=1,
                risks_by_severity={"LOW": 1},
                highest_severity=Severity.LOW,
                analysis_timestamp="2025-01-01T00:00:00Z",
                overall_risk_score=0.05,
            ),
        )
        result = validator_node(state)
        # global_confidence = 0.95*0.3 + 0.95*0.7 = 0.95 > 0.75
        assert result["needs_human_review"] is False

    def test_requires_review_when_critical_risk_present(self) -> None:
        state = _make_state(risk=RISK_OUTPUT_CRITICAL)
        result = validator_node(state)
        assert result["needs_human_review"] is True

    def test_requires_review_when_confidence_below_threshold(self) -> None:
        state = _make_state(
            summary=SummaryOutput(
                document_id="test-doc-123",
                executive_summary="Unclear summary that needs review by a legal professional.",
                section_summaries=[],
                key_parties=[],
                contract_duration=None,
                governing_law=None,
                overall_confidence=0.4,
            ),
            risk=RiskAnalysisOutput(
                document_id="test-doc-123",
                risks=[],
                total_risks=0,
                risks_by_severity={},
                highest_severity=Severity.LOW,
                analysis_timestamp="2025-01-01T00:00:00Z",
                overall_risk_score=0.0,
            ),
        )
        result = validator_node(state)
        # global_confidence = 0.4*0.3 + 0.5*0.7 = 0.47 < 0.75
        assert result["needs_human_review"] is True

    def test_flags_unverified_risks(self) -> None:
        state = _make_state(
            risk=RiskAnalysisOutput(
                document_id="test-doc-123",
                risks=[
                    RiskItem(
                        risk_id="risk-ghost",
                        description="Risk not in document",
                        category=RiskCategory.LEGAL,
                        severity=Severity.MEDIUM,
                        confidence=0.8,
                        clause_reference="this phrase does not exist in the contract",
                        recommendation="Review",
                    )
                ],
                total_risks=1,
                risks_by_severity={"MEDIUM": 1},
                highest_severity=Severity.MEDIUM,
                analysis_timestamp="2025-01-01T00:00:00Z",
                overall_risk_score=0.24,
            )
        )
        result = validator_node(state)
        output = result["validation_output"]
        assert "risk-ghost" in output.unverified_risk_ids

    def test_graceful_degradation_on_none_outputs(self) -> None:
        state = _make_state(summary=None, risk=None)
        result = validator_node(state)
        # Should not raise; confidence should be low
        assert result["global_confidence"] < 0.75
        assert result["needs_human_review"] is True
