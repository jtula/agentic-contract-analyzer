"""Pydantic v2 models for the Risk Analyzer node output."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Risk severity levels ordered from least to most critical."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(str, Enum):
    """Category of legal / contractual risk."""

    FINANCIAL = "FINANCIAL"
    """Penalties, fines, hidden payments, liability caps."""

    LEGAL = "LEGAL"
    """Ambiguous clauses, abusive terms, jurisdiction issues."""

    TEMPORAL = "TEMPORAL"
    """Critical deadlines, short notice periods, auto-renewals."""

    COMPLIANCE = "COMPLIANCE"
    """GDPR, data protection, sector-specific regulations."""

    OPERATIONAL = "OPERATIONAL"
    """Service levels, delivery obligations, force-majeure gaps."""


class RiskItem(BaseModel):
    """A single identified risk within the contract.

    Each risk is self-contained — it carries everything a reviewer needs
    to evaluate and act on the finding.
    """

    model_config = {"frozen": True}

    risk_id: str = Field(..., description="Unique identifier for this risk item.")
    description: str = Field(
        ..., min_length=10, description="Clear description of the risk."
    )
    category: RiskCategory = Field(..., description="Risk category.")
    severity: Severity = Field(..., description="Assessed severity level.")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence that this is a genuine risk."
    )
    clause_reference: str = Field(
        ..., description="Quote or reference to the exact clause in the contract."
    )
    recommendation: str = Field(
        ..., description="Actionable recommendation to mitigate this risk."
    )
    unverified: bool = Field(
        default=False,
        description=(
            "True if the validator could not find textual evidence for this risk. "
            "Flags it for human review."
        ),
    )


class RiskAnalysisOutput(BaseModel):
    """Complete output from the risk analyzer node.

    The LLM produces this via `.with_structured_output(RiskAnalysisOutput)`.
    """

    model_config = {"frozen": True}

    document_id: str = Field(..., description="ID of the source document.")
    risks: list[RiskItem] = Field(
        default_factory=list, description="All identified risks."
    )
    total_risks: int = Field(..., ge=0, description="Total number of risks found.")
    risks_by_severity: dict[str, int] = Field(
        default_factory=dict,
        description="Count of risks grouped by severity label.",
    )
    highest_severity: Severity = Field(
        ..., description="Highest severity level found across all risks."
    )
    analysis_timestamp: str = Field(
        ..., description="ISO-8601 timestamp when analysis was performed."
    )
    overall_risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Normalised composite risk score (0 = no risk, 1 = extreme risk). "
            "Computed as weighted average of per-risk severities × confidences."
        ),
    )
