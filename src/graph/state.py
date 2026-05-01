"""GraphState — shared mutable state that flows between all LangGraph nodes.

Every node reads from and writes back to this TypedDict. LangGraph merges
the returned dict with the current state automatically, so each node only
needs to return the keys it actually modified.

Design decisions
----------------
- TypedDict (not Pydantic BaseModel) because LangGraph's StateGraph expects
  a TypedDict for state definitions and uses it to build its internal schema.
- All node outputs are Optional[<PydanticModel>] so partial failures are
  representable without crashing the graph (graceful degradation).
- `errors` is a plain list so any node can append to it safely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from typing_extensions import TypedDict

if TYPE_CHECKING:
    from src.models.extractor import ExtractorOutput
    from src.models.summarizer import SummaryOutput
    from src.models.risk import RiskAnalysisOutput
    from src.models.validator import ValidationOutput


class GraphState(TypedDict):
    """Complete state shared across all nodes in the Contract Risk Analyzer graph.

    Fields are grouped by concern: input, per-node outputs, flow control,
    human-in-the-loop, and metadata.
    """

    # ── Input ─────────────────────────────────────────────────────────────
    document_id: str
    """Unique identifier for the contract document (used as S3 key prefix)."""

    s3_path: str
    """S3 URI of the uploaded PDF, e.g. s3://bucket/contracts/doc-123.pdf."""

    document_text: str
    """Full raw text extracted from the PDF. Set by the extractor node."""

    # ── Per-node outputs ──────────────────────────────────────────────────
    extractor_output: Optional["ExtractorOutput"]
    """Structured output from the extractor node. None if the node failed."""

    summary_output: Optional["SummaryOutput"]
    """Structured output from the summarizer node. None if the node failed."""

    risk_analysis_output: Optional["RiskAnalysisOutput"]
    """Structured output from the risk analyzer node. None if the node failed."""

    validation_output: Optional["ValidationOutput"]
    """Structured output from the validator node. None if the node failed."""

    # ── Flow control ──────────────────────────────────────────────────────
    global_confidence: float
    """Weighted average confidence across summarizer + risk analyzer (0.0–1.0).
    Calculated by the validator node. Drives the HITL gate decision."""

    needs_human_review: bool
    """True when global_confidence < threshold OR a CRITICAL risk was found."""

    current_node: str
    """Name of the node currently executing. Updated by each node on entry."""

    errors: list[str]
    """Accumulated error messages from all nodes. Never cleared mid-run."""

    retry_count: int
    """How many retries the current node has consumed. Reset per node."""

    # ── Human-in-the-loop ─────────────────────────────────────────────────
    human_feedback: Optional[str]
    """Free-text feedback submitted by a human reviewer after an interrupt."""

    # ── Metadata ──────────────────────────────────────────────────────────
    created_at: str
    """ISO-8601 timestamp when the run was created."""

    updated_at: str
    """ISO-8601 timestamp of the last state mutation."""
