"""Extract electrical parameters from Phase 2 grids."""

from __future__ import annotations

import logging
import re

from src.config import Config, get_config
from src.phase3_extract.footnote_resolver import extract_footnote_marker
from src.phase3_extract.table_utils import (
    cell_at,
    grid_source_to_extracted_source,
    identify_header_row,
    is_empty_cell,
    map_columns,
    parse_numeric,
)
from src.phase3_extract.unit_normalizer import normalize_unit
from src.schemas.datasheet import ElectricalParameter, ExtractedValue
from src.schemas.pipeline import GridMatrix, GridSource

logger = logging.getLogger(__name__)


def infer_param_type(param_name: str) -> str:
    """Infer parameter type from name."""
    name_lower = param_name.lower()
    if any(x in name_lower for x in ["v_cc", "v_dd", "v_ss", "v_in", "v_out", "v_", "voltage", "v_bus"]):
        return "voltage"
    if any(x in name_lower for x in ["i_cc", "i_dd", "i_q", "i_out", "i_", "current", "i_sleep"]):
        return "current"
    if any(x in name_lower for x in ["r_", "ohm", "resistance", "r_sense"]):
        return "resistance"
    if any(x in name_lower for x in ["c_", "cap", "capacitance"]):
        return "capacitance"
    if any(x in name_lower for x in ["l_", "henry", "inductance"]):
        return "inductance"
    if any(x in name_lower for x in ["f_", "freq", "frequency", "f_sw", "f_i2c"]):
        return "frequency"
    if any(x in name_lower for x in ["t_", "temp", "temperature", "t_j"]):
        return "temperature"
    if any(x in name_lower for x in ["time", "delay", "t_setup", "t_hold"]):
        return "time"
    if any(x in name_lower for x in ["p_", "power", "dissipation"]):
        return "power"
    return "other"


def extract_value_cell(
    cell_text: str,
    unit_text: str,
    param_type: str,
    grid_confidence: float,
    source: str,
    footnote_map: dict[str, str] | None = None,
) -> ExtractedValue | None:
    """Extract and normalize a single min/typ/max cell."""
    if is_empty_cell(cell_text):
        return None

    footnote_text = None
    cell_clean = cell_text
    marker = extract_footnote_marker(cell_text)
    if marker:
        cell_clean = cell_text[: cell_text.index(marker)].strip() or cell_text.replace(marker, "").strip()
        if footnote_map and marker in footnote_map:
            footnote_text = footnote_map[marker]

    numeric = parse_numeric(cell_clean)
    if numeric is None:
        logger.warning("Cannot parse value: %s", cell_text)
        return None

    extracted_source = grid_source_to_extracted_source(source)  # type: ignore[arg-type]

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
            logger.warning("Unit normalization failed: %s", exc)
            from src.phase3_extract.table_utils import infer_unit_from_param_type

            normalized_unit = infer_unit_from_param_type(param_type)
            normalized_value = numeric

    return ExtractedValue(
        raw_text=cell_text,
        value=normalized_value,
        unit=normalized_unit,
        confidence=grid_confidence,
        source=extracted_source,
        footnote=footnote_text,
    )


def extract_single_parameter(
    row: list[str],
    col_map: dict[str, int],
    grid_confidence: float,
    source: GridSource,
    footnote_map: dict[str, str] | None = None,
    component_id: str = "",
    row_idx: int = 0,
) -> ElectricalParameter | None:
    """Extract one electrical parameter from a data row."""
    param_name = cell_at(row, col_map.get("parameter"))
    min_text = cell_at(row, col_map.get("min"))
    typ_text = cell_at(row, col_map.get("typ"))
    max_text = cell_at(row, col_map.get("max"))
    unit_text = cell_at(row, col_map.get("unit"))
    conditions = cell_at(row, col_map.get("conditions"))
    notes_text = cell_at(row, col_map.get("notes"))

    if not param_name or (is_empty_cell(min_text) and is_empty_cell(typ_text) and is_empty_cell(max_text)):
        return None

    param_type = infer_param_type(param_name)
    extracted_source = source

    min_value = extract_value_cell(
        min_text, unit_text, param_type, grid_confidence, extracted_source, footnote_map
    )
    typ_value = extract_value_cell(
        typ_text, unit_text, param_type, grid_confidence, extracted_source, footnote_map
    )
    max_value = extract_value_cell(
        max_text, unit_text, param_type, grid_confidence, extracted_source, footnote_map
    )

    note_marker = extract_footnote_marker(notes_text)
    if note_marker and footnote_map and note_marker in footnote_map:
        footnote_text = footnote_map[note_marker]
        for value in (min_value, typ_value, max_value):
            if value is not None and value.footnote is None:
                value.footnote = footnote_text
                break

    if min_value is None and typ_value is None and max_value is None:
        logger.debug("%s row %d: skipping unparseable parameter %s", component_id, row_idx, param_name)
        return None

    return ElectricalParameter(
        name=param_name,
        parameter_type=param_type,
        min_value=min_value,
        typ_value=typ_value,
        max_value=max_value,
        conditions=conditions if not is_empty_cell(conditions) else None,
    )


def extract_electrical_parameters(
    grid: GridMatrix,
    component_id: str,
    footnote_map: dict[str, str] | None = None,
    config: Config | None = None,
) -> list[ElectricalParameter]:
    """Extract electrical parameters from an electrical_characteristics grid."""
    _ = config or get_config()
    header_row_idx = identify_header_row(grid.rows)
    if header_row_idx is None:
        logger.warning("%s: No header row found in electrical_characteristics", component_id)
        return []

    col_map = map_columns(grid.rows[header_row_idx])
    if "parameter" not in col_map:
        logger.warning("%s: No parameter column in electrical table", component_id)
        return []

    parameters: list[ElectricalParameter] = []
    for row_idx, row in enumerate(grid.rows[header_row_idx + 1 :], start=header_row_idx + 1):
        param = extract_single_parameter(
            row,
            col_map,
            grid.confidence,
            grid.source,
            footnote_map=footnote_map,
            component_id=component_id,
            row_idx=row_idx,
        )
        if param is not None:
            parameters.append(param)

    return parameters
