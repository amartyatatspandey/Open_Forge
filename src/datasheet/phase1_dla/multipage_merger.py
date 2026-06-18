"""Multipage table merging for Phase 1 DLA.

Detects and merges tables that span multiple pages using:
- Header row matching across page boundaries
- Spatial proximity of table regions
- Continuation markers in table content
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.datasheet.phase1_dla._schemas import TableCrop

logger = logging.getLogger(__name__)

# Threshold for considering tables as potentially continuing
# Tables within this vertical distance (normalized 0-1) are candidates
CONTINUATION_PROXIMITY_THRESHOLD: float = 0.1

# Minimum similarity for header row matching
HEADER_SIMILARITY_THRESHOLD: float = 0.7


def _normalize_bbox(
    bbox: tuple[int, int, int, int],
    page_width: int,
    page_height: int,
) -> tuple[float, float, float, float]:
    """Normalize bounding box coordinates to 0-1 range.

    Args:
        bbox: (x1, y1, x2, y2) in pixels
        page_width: Page width in pixels
        page_height: Page height in pixels

    Returns:
        Normalized (x1, y1, x2, y2)
    """
    x1, y1, x2, y2 = bbox
    return (
        x1 / page_width,
        y1 / page_height,
        x2 / page_width,
        y2 / page_height,
    )


def _calculate_vertical_distance(
    table1: TableCrop,
    table2: TableCrop,
    page_height: int,
) -> float:
    """Calculate vertical distance between two tables on consecutive pages.

    Args:
        table1: Table on previous page
        table2: Table on current page
        page_height: Page height in pixels

    Returns:
        Normalized vertical distance (0-1)
    """
    _, y1_1, _, y2_1 = table1.bounding_box
    _, y1_2, _, y2_2 = table2.bounding_box

    # Normalize to 0-1
    y2_1_norm = y2_1 / page_height
    y1_2_norm = y1_2 / page_height

    # Distance from bottom of page N to top of table on page N+1
    # Page N+1 starts at y=0, so we measure from page break
    page_break_distance = 1.0 - y2_1_norm + y1_2_norm

    return page_break_distance


def _headers_similar(
    table1: TableCrop,
    table2: TableCrop,
) -> bool:
    """Check if two tables have similar header rows.

    Uses heading text and spatial alignment to determine if
    tables are likely continuations of the same table.

    Args:
        table1: Table on previous page
        table2: Table on current page

    Returns:
        True if headers appear similar
    """
    # Check heading text similarity
    heading1 = table1.heading_text or ""
    heading2 = table2.heading_text or ""

    if heading1 and heading2:
        # Simple similarity: same section type and similar heading
        if table1.section_type == table2.section_type:
            # Normalize headings for comparison
            norm1 = heading1.lower().strip()
            norm2 = heading2.lower().strip()

            # Direct match or one contains the other
            if norm1 == norm2 or norm1 in norm2 or norm2 in norm1:
                return True

    # Check spatial alignment (tables in same horizontal position)
    x1_1, _, x2_1, _ = table1.bounding_box
    x1_2, _, x2_2, _ = table2.bounding_box

    # Calculate overlap ratio
    overlap_start = max(x1_1, x1_2)
    overlap_end = min(x2_1, x2_2)

    if overlap_start < overlap_end:
        overlap_width = overlap_end - overlap_start
        width1 = x2_1 - x1_1
        width2 = x2_2 - x1_2
        avg_width = (width1 + width2) / 2
        overlap_ratio = overlap_width / avg_width if avg_width > 0 else 0

        if overlap_ratio > HEADER_SIMILARITY_THRESHOLD:
            return True

    return False


def _is_continuation(
    previous_table: Optional[TableCrop],
    current_table: TableCrop,
    page_height: int,
) -> bool:
    """Determine if current table is a continuation of previous table.

    Uses multiple heuristics:
    1. Spatial proximity at page boundary
    2. Header row similarity
    3. Same section type
    4. Previous table near bottom of page

    Args:
        previous_table: Table from previous page (may be None)
        current_table: Table on current page
        page_height: Page height in pixels

    Returns:
        True if current_table is a continuation of previous_table
    """
    if previous_table is None:
        return False

    # Must be consecutive pages
    if current_table.page_number != previous_table.page_number + 1:
        return False

    # Must be same section type
    if current_table.section_type != previous_table.section_type:
        return False

    # Check spatial proximity
    vertical_distance = _calculate_vertical_distance(
        previous_table, current_table, page_height
    )

    # Previous table must be near bottom of its page
    _, _, _, y2_prev = previous_table.bounding_box
    prev_at_bottom = (y2_prev / page_height) > 0.7

    # Current table should be near top of its page
    _, y1_curr, _, _ = current_table.bounding_box
    curr_at_top = (y1_curr / page_height) < 0.3

    # Proximity check
    proximity_ok = vertical_distance < CONTINUATION_PROXIMITY_THRESHOLD * 2

    # Header similarity check
    headers_ok = _headers_similar(previous_table, current_table)

    # Table is continuation if:
    # - Previous was at bottom, current at top
    # - Similar headers
    # - Reasonable proximity
    is_cont = prev_at_bottom and curr_at_top and headers_ok and proximity_ok

    if is_cont:
        logger.info(
            f"Detected table continuation: page {previous_table.page_number} "
            f"-> page {current_table.page_number}"
        )

    return is_cont


def detect_multipage_tables(
    all_tables: list[TableCrop],
    page_height: int,
) -> list[TableCrop]:
    """Detect and mark multipage table continuations.

    Scans through tables in page order and marks tables that are
    continuations of tables from previous pages.

    Args:
        all_tables: List of all detected tables (sorted by page)
        page_height: Page height in pixels (assumes consistent sizing)

    Returns:
        List of tables with is_multipage_continuation flag set
    """
    if not all_tables:
        return []

    # Sort by page number, then by vertical position
    sorted_tables = sorted(
        all_tables,
        key=lambda t: (t.page_number, t.bounding_box[1]),
    )

    result: list[TableCrop] = []
    previous_table: Optional[TableCrop] = None

    for table in sorted_tables:
        # Check if this table continues from previous page
        is_continuation = _is_continuation(previous_table, table, page_height)

        # Create updated table with continuation flag
        updated_table = table.model_copy(
            update={"is_multipage_continuation": is_continuation}
        )

        result.append(updated_table)

        # Track as potential predecessor for next table
        # Only track if not itself a continuation (original table)
        if not is_continuation:
            previous_table = updated_table

    logger.info(f"Multipage detection: {len(result)} tables, marked continuations")
    return result


def merge_continuation_tables(
    tables: list[TableCrop],
) -> list[TableCrop]:
    """Merge detected continuation tables (placeholder for future).

    Currently just marks continuations. Future implementation could:
    - Concatenate table images vertically
    - Merge row data from all pages
    - Create single unified table representation

    Args:
        tables: List of tables with continuation flags

    Returns:
        List of tables (may be merged in future)
    """
    # For now, just return tables with continuation flags set
    # Future: actually merge the image bytes and metadata
    return tables
