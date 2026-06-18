"""Internal schemas for Phase 5 Layout Section Extraction.

These types are not exported from src.schemas and are used only within
Phase 5 for internal data representation between extraction steps.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.schemas.datasheet import PlacementConstraint


class LayoutExtractionResult(BaseModel):
    """Instructor-enforced wrapper for LLM output.

    This is the expected response format when querying Qwen2.5-7B-Instruct
    for layout constraint extraction. The constraints list contains fully
    structured PlacementConstraint objects.
    """

    model_config = {"extra": "forbid"}

    constraints: list[PlacementConstraint] = Field(
        default_factory=list,
        description="List of extracted placement constraints from layout text",
    )
    extraction_notes: str = Field(
        default="",
        description="Optional notes from the LLM about extraction quality or ambiguities",
    )


class PageTextBlock(BaseModel):
    """Plain text extracted from one layout page via pdfplumber.

    Represents a single page's text content after cleaning and normalization.
    The char_count field helps filter out pages with insufficient content.
    """

    model_config = {"extra": "forbid"}

    page_number: int = Field(
        ge=1,
        description="1-indexed page number matching Phase 1 indexing",
    )
    text: str = Field(
        ...,
        description="Extracted and cleaned text content from the page",
    )
    char_count: int = Field(
        ge=0,
        description="Character count of extracted text (post-cleaning)",
    )