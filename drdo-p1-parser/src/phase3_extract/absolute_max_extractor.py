"""Extract absolute maximum ratings from Phase 2 grids."""

from __future__ import annotations

import logging

from src.config import Config, get_config
from src.phase3_extract.parameter_extractor import infer_param_type
from src.phase3_extract.table_utils import (
    cell_at,
    grid_source_to_extracted_source,
    identify_header_row,
    is_empty_cell,
    map_abs_max_columns,
    parse_numeric,
)
from src.phase3_extract.unit_normalizer import normalize_unit
from src.schemas.datasheet import AbsoluteMaxRating, ExtractedValue
from src.schemas.pipeline import GridMatrix

logger = logging.getLogger(__name__)


def extract_single_abs_max(
    row: list[str],
    col_map: dict[str, int],
    grid_confidence: float,
    source: str,
) -> AbsoluteMaxRating | None:
    """Extract one absolute maximum rating from a row."""
    param_name = cell_at(row, col_map.get("parameter"))
    max_text = cell_at(row, col_map.get("max"))
    unit_text = cell_at(row, col_map.get("unit"))
    conditions = cell_at(row, col_map.get("conditions"))

    if not param_name or is_empty_cell(max_text):
        return None

    param_type = infer_param_type(param_name)
    numeric = parse_numeric(max_text)
    if numeric is None:
        logger.warning("Cannot extract abs max rating: %s = %s", param_name, max_text)
        return None

    if is_empty_cell(unit_text):
        from src.phase3_extract.table_utils import infer_unit_from_param_type

        normalized_unit = infer_unit_from_param_type(param_type)
        normalized_value = numeric
    else:
        try:
            normalized_value, normalized_unit = normalize_unit(
                str(numeric), unit_text, param_type
            )
        except ValueError as exc:
            logger.warning("Abs max unit normalization failed: %s", exc)
            from src.phase3_extract.table_utils import infer_unit_from_param_type

            normalized_unit = infer_unit_from_param_type(param_type)
            normalized_value = numeric

    extracted_source = grid_source_to_extracted_source(source)  # type: ignore[arg-type]

    return AbsoluteMaxRating(
        name=param_name,
        max_value=ExtractedValue(
            raw_text=max_text,
            value=normalized_value,
            unit=normalized_unit,
            confidence=grid_confidence,
            source=extracted_source,
        ),
        unit=normalized_unit,
        conditions=conditions if not is_empty_cell(conditions) else None,
    )


def extract_absolute_max_ratings(
    grid: GridMatrix,
    component_id: str,
    config: Config | None = None,
) -> list[AbsoluteMaxRating]:
    """Extract absolute maximum ratings from a grid."""
    _ = config or get_config()
    header_row_idx = identify_header_row(grid.rows)
    if header_row_idx is None:
        logger.warning("%s: No header in absolute_maximum_ratings table", component_id)
        return []

    col_map = map_abs_max_columns(grid.rows[header_row_idx])
    ratings: list[AbsoluteMaxRating] = []
    for row in grid.rows[header_row_idx + 1 :]:
        rating = extract_single_abs_max(row, col_map, grid.confidence, grid.source)
        if rating is not None:
            ratings.append(rating)

    return ratings
