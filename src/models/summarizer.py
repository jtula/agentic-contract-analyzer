"""Pydantic v2 models for the Summarizer node output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SectionSummary(BaseModel):
    """Summary of a single contract section produced by the LLM."""

    model_config = {"frozen": True}

    section_name: str = Field(..., description="Normalized section name.")
    summary: str = Field(..., min_length=20, description="Concise summary of the section.")
    key_points: list[str] = Field(
        default_factory=list,
        description="Bullet-point key facts extracted from this section.",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="LLM confidence in this section summary."
    )


class SummaryOutput(BaseModel):
    """Complete structured output from the summarizer node.

    The LLM is forced to produce this exact schema via `.with_structured_output()`.
    """

    model_config = {"frozen": True}

    document_id: str = Field(..., description="ID of the source document.")
    executive_summary: str = Field(
        ...,
        min_length=50,
        description="High-level executive summary of the entire contract.",
    )
    section_summaries: list[SectionSummary] = Field(
        default_factory=list,
        description="Per-section summaries in the order they appear in the contract.",
    )
    key_parties: list[str] = Field(
        default_factory=list,
        description="Names of the contracting parties identified in the document.",
    )
    contract_duration: str | None = Field(
        default=None,
        description="Contract duration or expiry date if explicitly stated.",
    )
    governing_law: str | None = Field(
        default=None,
        description="Jurisdiction or governing law clause if found.",
    )
    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aggregate LLM confidence across all section summaries.",
    )
