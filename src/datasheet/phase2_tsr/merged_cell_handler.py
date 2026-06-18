"""Merged cell detection and normalization for Phase 2 TSR.

Detects rowspan and colspan attributes by comparing cell content and positions.
Updates GridMatrix cells with span information without reordering.
"""

from __future__ import annotations

import logging
from src.datasheet.phase2_tsr._schemas import CellValue, GridMatrix

logger = logging.getLogger(__name__)

# Similarity threshold for detecting merged cells
CELL_TEXT_SIMILARITY_THRESHOLD: float = 0.9


def _cells_have_same_text(cell1: CellValue, cell2: CellValue) -> bool:
    """Check if two cells have identical or highly similar text.

    Args:
        cell1: First CellValue
        cell2: Second CellValue

    Returns:
        True if text is similar enough to indicate merged cell
    """
    text1 = cell1.text.strip().lower()
    text2 = cell2.text.strip().lower()

    if text1 == text2:
        return True

    # Handle common variations
    if not text1 or not text2:
        return False

    # Length-based heuristic for partial matches
    if abs(len(text1) - len(text2)) / max(len(text1), len(text2)) > 0.5:
        return False

    return False


def _detect_colspan_vector_path(grid: GridMatrix) -> GridMatrix:
    """Detect colspan for vector path by comparing adjacent cells.

    In vector path (pdfplumber + Camelot), merged cells often appear
    as duplicated content in adjacent positions.

    Args:
        grid: Input GridMatrix

    Returns:
        GridMatrix with colspan values updated
    """
    cells = list(grid.cells)
    has_merged = False

    # Group cells by row
    rows: dict[int, list[CellValue]] = {}
    for cell in cells:
        if cell.row not in rows:
            rows[cell.row] = []
        rows[cell.row].append(cell)

    # Detect colspan by identical adjacent cells
    for row_idx, row_cells in rows.items():
        sorted_cells = sorted(row_cells, key=lambda c: c.col)

        i = 0
        while i < len(sorted_cells):
            cell = sorted_cells[i]

            # Look for identical cells to the right
            colspan = 1
            for j in range(i + 1, len(sorted_cells)):
                next_cell = sorted_cells[j]

                # Check if text is identical (merged cell indicator)
                if _cells_have_same_text(cell, next_cell):
                    colspan += 1
                    # Mark the duplicate cell for removal
                    has_merged = True
                else:
                    break

            if colspan > 1:
                # Update original cell with colspan
                cell.colspan = colspan
                has_merged = True

            i += 1

    return grid.model_copy(
        update={"has_merged_cells": has_merged or grid.has_merged_cells}
    )


def _detect_rowspan_vector_path(grid: GridMatrix) -> GridMatrix:
    """Detect rowspan for vector path by comparing vertical adjacent cells.

    Args:
        grid: Input GridMatrix

    Returns:
        GridMatrix with rowspan values updated
    """
    cells = list(grid.cells)
    has_merged = False

    # Group cells by column
    cols: dict[int, list[CellValue]] = {}
    for cell in cells:
        if cell.col not in cols:
            cols[cell.col] = []
        cols[cell.col].append(cell)

    # Detect rowspan by identical vertical cells
    for col_idx, col_cells in cols.items():
        sorted_cells = sorted(col_cells, key=lambda c: c.row)

        i = 0
        while i < len(sorted_cells):
            cell = sorted_cells[i]

            # Look for identical cells below
            rowspan = 1
            for j in range(i + 1, len(sorted_cells)):
                next_cell = sorted_cells[j]

                if _cells_have_same_text(cell, next_cell):
                    rowspan += 1
                    has_merged = True
                else:
                    break

            if rowspan > 1:
                cell.rowspan = rowspan
                has_merged = True

            i += 1

    return grid.model_copy(
        update={"has_merged_cells": has_merged or grid.has_merged_cells}
    )


def _detect_spans_vlm_path(grid: GridMatrix) -> GridMatrix:
    """Detect colspan/rowspan for VLM path from markdown patterns.

    VLM output may include colspan indicators through cell widths
    or special patterns in the markdown.

    Args:
        grid: Input GridMatrix

    Returns:
        GridMatrix with span values updated
    """
    # For VLM path, we use similar heuristics as vector path
    # since markdown doesn't encode span information directly
    # (unlike HTML with colspan attributes)

    # First pass: detect colspan
    grid = _detect_colspan_vector_path(grid)

    # Second pass: detect rowspan
    grid = _detect_rowspan_vector_path(grid)

    return grid


def detect_merged_cells(grid: GridMatrix) -> GridMatrix:
    """Detect and mark merged cells in a GridMatrix.

    Analyzes cell content and positions to identify rowspan and colspan.
    Uses different strategies based on extraction_path (vector vs vlm).

    Args:
        grid: Input GridMatrix

    Returns:
        GridMatrix with updated rowspan/colspan and has_merged_cells flag

    Notes:
        - Never modifies cells list ordering — only updates span fields
        - For vector path: detects by identical adjacent cell text
        - For VLM path: infers from patterns and cell content
    """
    logger.debug(f"Detecting merged cells in {grid.num_rows}x{grid.num_cols} grid")

    if grid.extraction_path == "vector":
        # Vector path: detect by identical cell text
        grid = _detect_colspan_vector_path(grid)
        grid = _detect_rowspan_vector_path(grid)
    elif grid.extraction_path == "vlm":
        # VLM path: infer from markdown patterns
        grid = _detect_spans_vlm_path(grid)
    else:
        logger.warning(f"Unknown extraction path: {grid.extraction_path}")

    # Count actual merged cells
    merged_count = sum(
        1 for c in grid.cells if c.rowspan > 1 or c.colspan > 1
    )

    if merged_count > 0:
        logger.info(f"Detected {merged_count} merged cells in grid")
    else:
        logger.debug("No merged cells detected")

    return grid
