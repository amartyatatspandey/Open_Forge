"""Phase 1: Document Layout Analysis (DLA)."""

from src.phase1_dla.classify_section import classify_section_type, extract_heading_text
from src.phase1_dla.detect import TableDetector, crop_region
from src.phase1_dla.footnote_linker import (
    build_footnote_map,
    extract_footnotes_from_crops,
    link_footnotes_to_cells,
)
from src.phase1_dla.multipage_merge import merge_multipage_tables
from src.phase1_dla.pdf_offset import detect_cover_offset
from src.phase1_dla.rasterize import rasterize_pdf
from src.phase1_dla.runner import run_phase1

__all__ = [
    "TableDetector",
    "build_footnote_map",
    "classify_section_type",
    "crop_region",
    "extract_footnotes_from_crops",
    "extract_heading_text",
    "link_footnotes_to_cells",
    "detect_cover_offset",
    "merge_multipage_tables",
    "rasterize_pdf",
    "run_phase1",
]
