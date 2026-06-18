"""Section type classification for Phase 1 DLA.

Classifies detected table regions into TableSectionType categories
based on heading text and positional heuristics.

Supports all 7 TableSectionType values from src.schemas.datasheet:
- ELECTRICAL_CHARACTERISTICS
- ABSOLUTE_MAXIMUM_RATINGS
- PINOUT
- TIMING
- ORDERING
- LAYOUT_RECOMMENDATIONS
- OTHER
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.schemas.datasheet import TableSectionType

logger = logging.getLogger(__name__)

# Keyword patterns for section classification
# Maps regex patterns to TableSectionType values
_SECTION_PATTERNS: dict[TableSectionType, list[str]] = {
    TableSectionType.ELECTRICAL_CHARACTERISTICS: [
        r"electrical\s*characteristics",
        r"electrical\s*specifications",
        r"dc\s*characteristics",
        r"ac\s*characteristics",
        r"operating\s*conditions",
        r"recommended\s*operating",
    ],
    TableSectionType.ABSOLUTE_MAXIMUM_RATINGS: [
        r"absolute\s*maximum",
        r"absolute\s*max",
        r"max\s*ratings",
        r"stress\s*ratings",
        r"maximum\s*ratings",
    ],
    TableSectionType.PINOUT: [
        r"pin\s*configuration",
        r"pin\s*assignments",
        r"pin\s*functions",
        r"pin\s*description",
        r"pin\s*out",
        r"terminal\s*functions",
        r"pin\s*function",
        r"pin\s*.*diagram",
    ],
    TableSectionType.TIMING: [
        r"timing\s*requirements",
        r"switching\s*characteristics",
        r"timing\s*diagram",
        r"timing\s*specifications",
        r"dynamic\s*characteristics",
        r"timing\s*tables",
    ],
    TableSectionType.ORDERING: [
        r"ordering\s*information",
        r"order\s*information",
        r"package\s*options",
        r"device\s*options",
        r"ordering\s*code",
        r"part\s*number",
    ],
    TableSectionType.LAYOUT_RECOMMENDATIONS: [
        r"layout\s*recommendations",
        r"pcb\s*layout",
        r"layout\s*guidelines",
        r"layout\s*example",
        r"application\s*layout",
        r"recommended\s*layout",
    ],
}


def _extract_heading_text(
    image_text: str,
    table_bbox: tuple[int, int, int, int],
    page_height: int,
) -> Optional[str]:
    """Extract section heading text above a table region.

    Uses positional heuristics and OCR text to find the section
    heading immediately preceding a detected table.

    Args:
        image_text: Full page text from OCR (if available)
        table_bbox: Table bounding box (x1, y1, x2, y2)
        page_height: Total page height in pixels

    Returns:
        Extracted heading text, or None if no heading found
    """
    # In a real implementation, this would:
    # 1. Look for text regions above the table bbox
    # 2. Apply font size heuristics (headings are larger)
    # 3. Return the most likely heading text

    # For now, we return the provided text or a placeholder
    if image_text:
        # Simple heuristic: return last line before table position
        lines = image_text.split("\n")
        return lines[0] if lines else None

    return None


def _classify_heading(heading_text: Optional[str]) -> TableSectionType:
    """Classify section heading text to TableSectionType.

    Uses regex pattern matching against known section heading patterns.

    Args:
        heading_text: Extracted heading text

    Returns:
        TableSectionType classification (defaults to OTHER if no match)
    """
    if not heading_text:
        return TableSectionType.OTHER

    heading_lower = heading_text.lower()

    for section_type, patterns in _SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, heading_lower, re.IGNORECASE):
                logger.debug(f"Classified heading '{heading_text}' as {section_type.value}")
                return section_type

    logger.debug(f"No pattern match for heading '{heading_text}', defaulting to OTHER")
    return TableSectionType.OTHER


def _classify_by_position(
    page_number: int,
    table_index: int,
) -> TableSectionType:
    """Classify table by positional heuristics when heading is unclear.

    Uses document structure patterns common in datasheets:
    - First tables often contain pinout or absolute maximum ratings
    - Mid-document tables often electrical characteristics
    - End tables often ordering information

    Args:
        page_number: 1-indexed page number
        table_index: Index of table on this page

    Returns:
        TableSectionType based on positional heuristics
    """
    # Simple positional heuristics
    if page_number <= 2 and table_index == 0:
        # Early pages, first table — likely pinout or abs-max
        return TableSectionType.ABSOLUTE_MAXIMUM_RATINGS

    if table_index > 0:
        # Later tables on same page — likely electrical characteristics
        return TableSectionType.ELECTRICAL_CHARACTERISTICS

    # Default fallback
    return TableSectionType.OTHER


def classify_section(
    heading_text: Optional[str],
    page_number: int = 1,
    table_index: int = 0,
    fallback_to_position: bool = False,
) -> TableSectionType:
    """Classify table section type from heading and position.

    Primary method uses heading text pattern matching. If heading
    is unavailable or doesn't match, returns OTHER by default.
    Positional heuristics can be enabled via fallback_to_position
    but are not used by default to avoid misclassification.

    Args:
        heading_text: Extracted section heading text (may be None)
        page_number: 1-indexed page number for position fallback
        table_index: Index of table on page for position fallback
        fallback_to_position: Whether to use positional heuristics
            (default False - returns OTHER if heading doesn't match)

    Returns:
        TableSectionType classification (defaults to OTHER for unknown)
    """
    # Try heading-based classification first
    if heading_text:
        heading_classification = _classify_heading(heading_text)
        if heading_classification != TableSectionType.OTHER:
            return heading_classification

    # If heading classification failed and fallback is enabled, use position
    # Otherwise return OTHER (safe default)
    if fallback_to_position and (heading_text is None or heading_text.strip() == ""):
        return _classify_by_position(page_number, table_index)

    return TableSectionType.OTHER
