"""Pydantic v2 models for the Report Generator node output."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.risk import RiskItem, Severity


class ReportMetadata(BaseModel):
    """Metadata section included in every generated report."""

    model_config = {"frozen": True}

    document_id: str
    run_id: str
    model_used: str
    total_tokens: int = Field(..., ge=0)
    processing_time_ms: int = Field(..., ge=0)
    langsmith_trace_url: str | None = None
    created_at: str
    report_s3_path_json: str
    report_s3_path_md: str


class ReportOutput(BaseModel):
    """Complete structured report ready for serialisation to JSON / Markdown."""

    model_config = {"frozen": True}

    document_id: str
    executive_summary: str = Field(..., min_length=50)
    key_parties: list[str] = Field(default_factory=list)
    contract_duration: str | None = None
    governing_law: str | None = None
    risks: list[RiskItem] = Field(default_factory=list)
    total_risks: int = Field(..., ge=0)
    highest_severity: Severity
    overall_risk_score: float = Field(..., ge=0.0, le=1.0)
    global_confidence: float = Field(..., ge=0.0, le=1.0)
    recommendations: list[str] = Field(default_factory=list)
    human_feedback: str | None = None
    metadata: ReportMetadata
