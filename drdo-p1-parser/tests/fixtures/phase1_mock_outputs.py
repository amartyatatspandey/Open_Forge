"""Mock Phase 1 outputs for Phase 2 integration tests."""

from __future__ import annotations

from src.schemas.pipeline import BoundingBox, DetectedTable, Phase1Output


def _table(
    section_type: str,
    page_number: int,
    heading_text: str | None = None,
) -> DetectedTable:
    """Build a minimal DetectedTable for runner tests."""
    return DetectedTable(
        crop_bytes=b"\x89PNG\r\n\x1a\n\x00",
        bbox=BoundingBox(x1=50, y1=100, x2=450, y2=300),
        page_number=page_number,
        page_range=(page_number, page_number),
        confidence=0.92,
        section_type=section_type,  # type: ignore[arg-type]
        heading_text=heading_text,
    )


def mock_phase1_output_tlv7021() -> Phase1Output:
    """Minimal Phase1Output mimicking TLV7021 detections."""
    return Phase1Output(
        pdf_path="corpus/golden/TI_TLV7021_v1.pdf",
        detected_tables=[
            _table("absolute_maximum_ratings", 4, "6.1 Absolute Maximum Ratings"),
            _table("electrical_characteristics", 5, "6.5 Electrical Characteristics"),
            _table("pinout", 3, "5 Pin Configuration and Functions"),
        ],
        footnote_map={"(1)": "Test footnote"},
    )
