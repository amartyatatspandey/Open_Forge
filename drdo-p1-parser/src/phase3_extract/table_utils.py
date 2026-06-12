"""Shared table parsing helpers for Phase 3 extractors."""

from __future__ import annotations

import re
from typing import Literal

from src.phase3_extract.unit_normalizer import CANONICAL_UNITS
from src.schemas.pipeline import GridSource

EMPTY_MARKERS = {"—", "–", "-", "", "n/a", "na"}

_HEADER_KEYWORDS = (
    "parameter",
    "min",
    "typ",
    "max",
    "unit",
    "pin",
    "name",
    "condition",
    "value",
    "description",
)


def is_empty_cell(text: str | None) -> bool:
    """Return True if cell text represents an empty/missing value."""
    if text is None:
        return True
    return text.strip().lower() in EMPTY_MARKERS or text.strip() == ""


def is_header_row(row: list[str]) -> bool:
    """Return True if row looks like a table header."""
    if not row:
        return False
    non_empty = [cell.strip() for cell in row if cell.strip()]
    if not non_empty:
        return False
    matches = sum(
        1
        for cell in non_empty
        if any(keyword in cell.lower() for keyword in _HEADER_KEYWORDS)
    )
    return matches >= 2


def identify_header_row(rows: list[list[str]]) -> int | None:
    """Find the header row index in the first few rows."""
    for index, row in enumerate(rows[:5]):
        if is_header_row(row):
            return index
    return None


def map_columns(header: list[str]) -> dict[str, int]:
    """Map electrical table header names to column indices."""
    col_map: dict[str, int] = {}
    for index, cell in enumerate(header):
        lower = cell.lower().strip()
        if any(x in lower for x in ("parameter", "name", "part", "description")):
            col_map["parameter"] = index
        elif any(x in lower for x in ("min", "minimum")):
            col_map["min"] = index
        elif any(x in lower for x in ("typ", "typical")):
            col_map["typ"] = index
        elif any(x in lower for x in ("max", "maximum")):
            col_map["max"] = index
        elif any(x in lower for x in ("unit", "units")):
            col_map["unit"] = index
        elif any(x in lower for x in ("condition", "test")):
            col_map["conditions"] = index
        elif "note" in lower:
            col_map["notes"] = index
    return col_map


def map_pin_columns(header: list[str]) -> dict[str, int]:
    """Map pinout table header names to column indices."""
    col_map: dict[str, int] = {}
    for index, cell in enumerate(header):
        lower = cell.lower().strip()
        if "pin" in lower and "type" not in lower:
            col_map["pin_number"] = index
        elif lower in ("name",) or "name" in lower:
            col_map["pin_name"] = index
        elif "type" in lower or "function" in lower:
            if "alt" in lower:
                col_map["alt_function"] = index
            elif "pin_type" not in col_map:
                col_map["pin_type"] = index
        elif "description" in lower or lower == "function":
            col_map["description"] = index
    if "pin_number" not in col_map and header:
        col_map.setdefault("pin_number", 0)
    if "pin_name" not in col_map and len(header) > 1:
        col_map.setdefault("pin_name", 1)
    return col_map


def map_abs_max_columns(header: list[str]) -> dict[str, int]:
    """Map absolute maximum ratings header to column indices."""
    col_map: dict[str, int] = {}
    for index, cell in enumerate(header):
        lower = cell.lower().strip()
        if any(x in lower for x in ("parameter", "name")):
            col_map["parameter"] = index
        elif any(x in lower for x in ("max", "maximum", "value")):
            col_map["max"] = index
        elif "unit" in lower:
            col_map["unit"] = index
        elif "condition" in lower:
            col_map["conditions"] = index
    return col_map


def infer_unit_from_param_type(param_type: str) -> str:
    """Return default canonical unit for a parameter type."""
    return CANONICAL_UNITS.get(param_type, CANONICAL_UNITS.get("other", "V"))


def parse_numeric(cell_text: str) -> float | None:
    """Parse numeric value from cell text, stripping sign prefix."""
    if is_empty_cell(cell_text):
        return None
    cleaned = cell_text.strip().replace(",", "")
    cleaned = re.sub(r"^[±+\-−]", "", cleaned).strip()
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def grid_source_to_extracted_source(
    grid_source: GridSource,
) -> Literal["vector_path_A", "vlm_path_B", "manual_review"]:
    """Map GridMatrix source to ExtractedValue source literal."""
    if grid_source == "vector_path_A":
        return "vector_path_A"
    if grid_source == "vlm_path_B":
        return "vlm_path_B"
    return "manual_review"


def cell_at(row: list[str], index: int | None) -> str:
    """Safely get cell text from a row."""
    if index is None or index >= len(row):
        return ""
    return row[index].strip()
