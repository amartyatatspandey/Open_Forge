"""Phase 1: Classify detected tables by section type."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pdfplumber

from src.config import Config, get_config
from src.schemas.pipeline import BoundingBox, SectionType

logger = logging.getLogger(__name__)

PositionOnPage = str  # "top" | "middle" | "bottom"

# Classification order matters — first match wins
_SECTION_ORDER: list[SectionType] = [
    "electrical_characteristics",
    "pinout",
    "absolute_maximum_ratings",
    "timing",
    "ordering",
]


def position_on_page(bbox: BoundingBox, page_height: int) -> PositionOnPage:
    """Determine vertical position of a bbox on the page.

    Args:
        bbox: Table bounding box.
        page_height: Page height in pixels.

    Returns:
        "top", "middle", or "bottom".
    """
    if page_height <= 0:
        return "middle"
    center_y = (bbox.y1 + bbox.y2) / 2
    third = page_height / 3
    if center_y < third:
        return "top"
    if center_y < 2 * third:
        return "middle"
    return "bottom"


def extract_heading_text(
    pdf_path: str | Path,
    page_number: int,
    table_bbox: BoundingBox,
    dpi: int = 300,
) -> str | None:
    """Extract section heading text above a table bbox using pdfplumber.

    Args:
        pdf_path: Path to source PDF.
        page_number: 1-indexed page number.
        table_bbox: Table region in rasterized pixel coordinates.
        dpi: Rasterization DPI used to scale coordinates.

    Returns:
        Heading text above the table, or None if not found.
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        return None

    scale = 72.0 / dpi
    with pdfplumber.open(pdf_file) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            return None
        page = pdf.pages[page_number - 1]
        page_height_pt = page.height
        table_top_pt = table_bbox.y1 * scale
        heading_region_top = max(0, table_top_pt - 80)
        cropped = page.crop((0, heading_region_top, page.width, table_top_pt))
        text = cropped.extract_text() or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None
        return lines[-1]


def classify_section_type(
    heading_text: str | None,
    page_number: int,
    position: PositionOnPage,
    config: Config | None = None,
) -> SectionType:
    """Classify a table's section type from heading text and position.

    Args:
        heading_text: Extracted heading above the table.
        page_number: 1-indexed page number.
        position: Vertical position on page.
        config: Optional config override.

    Returns:
        Section type label.
    """
    cfg = config or get_config()
    keywords = cfg.phase1_dla.section_keywords

    if heading_text:
        heading_lower = heading_text.lower()
        for section_type in _SECTION_ORDER:
            patterns = keywords.get(section_type, [])
            for pattern in patterns:
                if pattern.lower() in heading_lower:
                    logger.debug(
                        "Classified page %d as %s via heading: %s",
                        page_number,
                        section_type,
                        heading_text[:60],
                    )
                    return section_type

    # Position fallback heuristics
    if page_number <= 3 and position == "top":
        return "absolute_maximum_ratings"
    if position == "bottom" and page_number <= 5:
        return "pinout"
    if page_number >= 4:
        return "electrical_characteristics"

    return "other"


def heading_matches_section(heading_text: str, section_type: SectionType, config: Config | None = None) -> bool:
    """Check if heading text matches a given section type keyword list."""
    cfg = config or get_config()
    patterns = cfg.phase1_dla.section_keywords.get(section_type, [])
    heading_lower = heading_text.lower()
    return any(re.search(re.escape(p.lower()), heading_lower) for p in patterns)


def _page_text_matches_section(page_text: str, section_type: SectionType, config: Config) -> bool:
    """Return True if page text contains keywords for a section type."""
    patterns = config.phase1_dla.section_keywords.get(section_type, [])
    page_lower = page_text.lower()
    return any(pattern.lower() in page_lower for pattern in patterns)


def scan_page_section_hints(
    pdf_path: str | Path,
    max_pages: int | None = None,
    config: Config | None = None,
) -> dict[int, SectionType]:
    """Scan PDF pages and infer dominant section type from page text.

    Args:
        pdf_path: Path to source PDF.
        max_pages: Optional limit on pages scanned.
        config: Optional config override.

    Returns:
        Map of 1-indexed page number to section type hint.
    """
    cfg = config or get_config()
    pdf_file = Path(pdf_path)
    hints: dict[int, SectionType] = {}

    if not pdf_file.exists():
        return hints

    header_pattern = re.compile(
        r"^\s*\d+(?:\.\d+)+\s+(.+)$",
        re.MULTILINE,
    )
    with pdfplumber.open(pdf_file) as pdf:
        pages = pdf.pages[:max_pages] if max_pages else pdf.pages
        for index, page in enumerate(pages):
            page_number = index + 1
            text = page.extract_text() or ""
            matched: SectionType | None = None
            for line in header_pattern.findall(text):
                for section_type in _SECTION_ORDER:
                    if _page_text_matches_section(line, section_type, cfg):
                        matched = section_type
                        break
                if matched:
                    break
            if matched is None:
                for section_type in _SECTION_ORDER:
                    if _page_text_matches_section(text, section_type, cfg):
                        matched = section_type
                        break
            if matched:
                hints[page_number] = matched

    logger.debug("Page section hints: %s", hints)
    return hints
