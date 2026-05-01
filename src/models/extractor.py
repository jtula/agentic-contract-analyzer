"""Pydantic v2 models for the Extractor node output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentSection(BaseModel):
    """A single identified section within a legal contract."""

    model_config = {"frozen": True}

    name: str = Field(..., description="Section name, e.g. 'PARTES', 'OBJETO'.")
    content: str = Field(..., description="Full text content of the section.")
    start_page: int = Field(..., ge=1, description="1-indexed page where section begins.")
    end_page: int = Field(..., ge=1, description="1-indexed page where section ends.")


class ExtractorOutput(BaseModel):
    """Structured output produced by the extractor node.

    Contains the raw text, identified sections, and confidence about
    how completely the document was parsed.
    """

    model_config = {"frozen": True}

    document_id: str = Field(..., description="ID of the source document.")
    raw_text: str = Field(..., description="Full concatenated text from all PDF pages.")
    page_count: int = Field(..., ge=1, description="Total number of pages in the PDF.")
    sections: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of section name → section text. "
            "Keys are normalized uppercase, e.g. 'PARTES', 'OBJETO'."
        ),
    )
    identified_sections: list[DocumentSection] = Field(
        default_factory=list,
        description="Detailed section objects with page-range metadata.",
    )
    extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence (0–1) that the text was extracted cleanly. "
            "Drops if the PDF is image-based or heavily formatted."
        ),
    )
    extraction_warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings raised during extraction.",
    )
