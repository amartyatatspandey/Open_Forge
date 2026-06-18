"""Internal schemas for Phase 1 DLA — not exported publicly.

These Pydantic models define the intermediate output of Phase 1 Document Layout
Analysis. They are pipeline-internal types and not part of the public API.
The only public export from this package is process() in __init__.py.

Phase 1 Output Contract (with Phase 2):
- TableCrop: Detected table regions with metadata
- FootnoteMap: Superscript to footnote text mappings
- Phase1Output: Complete DLA results for one PDF
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.schemas.datasheet import TableSectionType


class TableCrop(BaseModel):
    """A detected table region from one PDF page.

    Represents a single table crop extracted from a PDF page by the
    document layout analysis pipeline. Includes position, classification,
    and image data for downstream table structure recognition.

    Attributes:
        page_number: 1-indexed page number where table was found
        section_type: Classification of table content type
        image_bytes: Cropped table image as PNG bytes
        bounding_box: Table location (x1, y1, x2, y2) in pixels
        heading_text: Section heading text above table (if any)
        is_multipage_continuation: True if table continues from previous page
        detection_confidence: YOLO detection confidence [0.0, 1.0]
    """

    page_number: int = Field(ge=1, description="1-indexed page number")
    section_type: TableSectionType = Field(
        description="Classification of table content type"
    )
    image_bytes: bytes = Field(description="Cropped table image as PNG bytes")
    bounding_box: tuple[int, int, int, int] = Field(
        description="Table location (x1, y1, x2, y2) in pixels"
    )
    heading_text: Optional[str] = Field(
        default=None, description="Section heading text above table (if any)"
    )
    is_multipage_continuation: bool = Field(
        default=False,
        description="True if table continues from previous page",
    )
    detection_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="YOLO detection confidence [0.0, 1.0]",
    )


class FootnoteMap(BaseModel):
    """Maps superscript markers to footnote text for one PDF page.

    Captures footnote definitions found on a single page. Superscript
    markers (e.g., "(1)", "*") are mapped to their full text definitions
    for later table cell annotation.

    Attributes:
        page_number: 1-indexed page number where footnotes were found
        entries: Dictionary mapping marker -> footnote text
                 Example: {"1" -> "Valid for T_A = 25°C"}
    """

    page_number: int = Field(ge=1, description="1-indexed page number")
    entries: dict[str, str] = Field(
        description='Dictionary mapping marker -> footnote text. Example: {"1" -> "Valid for T_A = 25°C"}'
    )


class Phase1Output(BaseModel):
    """Complete output of Phase 1 DLA. Input to Phase 2.

    The aggregate result of document layout analysis on a single PDF.
    Contains all detected table crops, footnote mappings, and metadata
    required for Phase 2 Table Structure Recognition.

    Attributes:
        pdf_path: Path to the source PDF file
        source_pdf_hash: SHA-256 hash of source PDF for provenance
        total_pages: Total number of pages in the PDF
        table_crops: List of detected table regions with images
        footnote_maps: List of footnote mappings per page
        processing_time_ms: Total Phase 1 processing time in milliseconds
    """

    pdf_path: str = Field(description="Path to the source PDF file")
    source_pdf_hash: str = Field(
        description="SHA-256 hash of source PDF for provenance"
    )
    total_pages: int = Field(ge=1, description="Total number of pages in the PDF")
    table_crops: list[TableCrop] = Field(
        description="List of detected table regions with images"
    )
    footnote_maps: list[FootnoteMap] = Field(
        description="List of footnote mappings per page"
    )
    processing_time_ms: float = Field(
        ge=0.0, description="Total Phase 1 processing time in milliseconds"
    )
