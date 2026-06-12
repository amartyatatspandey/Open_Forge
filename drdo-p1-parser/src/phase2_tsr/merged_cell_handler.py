"""Normalize merged cells and ragged table rows."""

from __future__ import annotations

import re

_COLSPAN_PATTERN = re.compile(r"→+")
_ROWSPAN_MARKER = "↓"


def infer_col_count(rows: list[list[str]]) -> int:
    """Infer column count after expanding colspan markers."""
    max_cols = 0
    for row in rows:
        expanded = _expand_colspan_row(row)
        max_cols = max(max_cols, len(expanded))
    return max_cols


def _expand_colspan_row(row: list[str]) -> list[str]:
    """Expand cells containing colspan arrows into repeated values."""
    expanded: list[str] = []
    for cell in row:
        match = _COLSPAN_PATTERN.search(cell)
        if match:
            base = _COLSPAN_PATTERN.sub("", cell).strip()
            span = len(match.group(0))
            expanded.extend([base] * max(span, 1))
        else:
            expanded.append(cell.strip())
    return expanded


def normalise_merged_cells(
    rows: list[list[str]],
    target_col_count: int | None = None,
) -> list[list[str]]:
    """Normalize rows to consistent column count with merged cells expanded.

    Args:
        rows: 2D list of cell strings, possibly ragged or with merge markers.
        target_col_count: If None, infer from longest expanded row.

    Returns:
        Normalized rows, all same length, empty cells as "".
    """
    if not rows:
        return []

    expanded_rows = [_expand_colspan_row(row) for row in rows]
    col_count = target_col_count or infer_col_count(rows)

    normalized: list[list[str]] = []
    for row_index, row in enumerate(expanded_rows):
        padded = row + [""] * (col_count - len(row))
        padded = padded[:col_count]
        for col_index, cell in enumerate(padded):
            if cell.strip() == _ROWSPAN_MARKER and row_index > 0:
                padded[col_index] = normalized[row_index - 1][col_index]
        normalized.append(padded)

    return normalized
