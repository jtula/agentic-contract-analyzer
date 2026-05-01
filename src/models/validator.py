"""Pydantic v2 models for the Validator node output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CrossReference(BaseModel):
    """A cross-reference check between summarizer and risk-analyzer outputs."""

    model_config = {"frozen": True}

    risk_id: str = Field(..., description="ID of the risk item being verified.")
    clause_found_in_text: bool = Field(
        ...,
        description="True if the referenced clause was located in the extracted text.",
    )
    summary_aligned: bool = Field(
        ...,
        description="True if the risk is consistent with the section summary.",
    )
    discrepancy_note: str | None = Field(
        default=None,
        description="Human-readable note describing the discrepancy if any.",
    )


class ValidationOutput(BaseModel):
    """Output from the validator node.

    Captures consistency checks, global confidence, and the HITL decision.
    """

    model_config = {"frozen": True}

    document_id: str = Field(..., description="ID of the source document.")
    cross_references: list[CrossReference] = Field(
        default_factory=list,
        description="Per-risk cross-reference results.",
    )
    unverified_risk_ids: list[str] = Field(
        default_factory=list,
        description="Risk IDs that could not be verified against the contract text.",
    )
    global_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Weighted average: (summary_confidence * 0.3) + (avg_risk_confidence * 0.7)."
        ),
    )
    needs_human_review: bool = Field(
        ...,
        description=(
            "True when global_confidence < CONFIDENCE_THRESHOLD "
            "or any CRITICAL risk was found."
        ),
    )
    review_reason: str | None = Field(
        default=None,
        description="Plain-English reason the run was flagged for human review.",
    )
    validation_timestamp: str = Field(
        ..., description="ISO-8601 timestamp when validation completed."
    )
