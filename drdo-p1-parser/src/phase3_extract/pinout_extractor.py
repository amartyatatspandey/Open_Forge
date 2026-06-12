"""Extract pin definitions from pinout grids."""

from __future__ import annotations

import logging
import re

from src.config import Config, get_config
from src.phase3_extract.table_utils import (
    cell_at,
    identify_header_row,
    is_empty_cell,
    map_pin_columns,
)
from src.schemas.datasheet import PinDefinition
from src.schemas.pipeline import GridMatrix

logger = logging.getLogger(__name__)


def extract_alternate_functions(pin_name: str) -> list[str]:
    """Parse alternate functions from pin name (e.g. GPIO0/UART_TX)."""
    parts = re.split(r"[/,;]", pin_name)
    return [part.strip() for part in parts if part.strip()]


def infer_pin_type(pin_name: str, pin_type_text: str) -> str:
    """Infer pin type literal from name and type column."""
    combined = f"{pin_name} {pin_type_text}".lower()

    if any(x in combined for x in ["v_cc", "v_dd", "v+", "power", "vdd", "vss_out", "v_in"]):
        return "power"
    if any(x in combined for x in ["gnd", "v_ss", "v-", "ground", "vss"]):
        return "ground"
    if any(x in combined for x in ["gpio", "digital", "i/o", "io", "input/output"]):
        return "digital_io"
    if any(x in combined for x in ["out", "tx", "txd", "output", "dq"]) and "input" not in combined:
        return "digital_output"
    if any(x in combined for x in ["analog", "adc", "dac", "ain", "aout", "in+", "in-"]):
        if "out" in combined and "in+" not in combined and "in-" not in combined:
            return "analog_output"
        return "analog_input"
    if any(x in combined for x in ["in", "rx", "rxd", "input", "clk", "scl", "sda"]):
        return "digital_input"
    if any(x in combined for x in ["clock", "clk", "osc"]):
        return "clock"
    if any(x in combined for x in ["reset", "rst", "nreset"]):
        return "reset"
    if any(x in combined for x in ["no connect", "nc", "—"]):
        return "no_connect"
    if pin_type_text.lower() in ("input",):
        return "digital_input"
    if pin_type_text.lower() in ("output", "digital out"):
        return "digital_output"
    if pin_type_text.lower() in ("ground",):
        return "ground"
    if pin_type_text.lower() in ("power",):
        return "power"
    return "other"


def extract_single_pin(
    row: list[str],
    col_map: dict[str, int],
    grid_confidence: float,
) -> PinDefinition | None:
    """Extract one pin from a data row."""
    pin_number = cell_at(row, col_map.get("pin_number"))
    if is_empty_cell(pin_number):
        return None

    pin_name = cell_at(row, col_map.get("pin_name"))
    pin_type_text = cell_at(row, col_map.get("pin_type"))
    description = cell_at(row, col_map.get("description"))

    if pin_name.lower() in ("nc", "—") and "no connect" in pin_type_text.lower():
        pin_type = "no_connect"
    else:
        pin_type = infer_pin_type(pin_name, pin_type_text)

    alternates = extract_alternate_functions(pin_name)
    if len(alternates) == 1:
        alternates = []

    return PinDefinition(
        pin_number=pin_number,
        pin_name=pin_name,
        pin_type=pin_type,  # type: ignore[arg-type]
        alternate_functions=alternates,
        description=description if not is_empty_cell(description) else None,
    )


def extract_pins(
    grid: GridMatrix,
    component_id: str,
    config: Config | None = None,
) -> list[PinDefinition]:
    """Extract pin definitions from a pinout GridMatrix."""
    _ = config or get_config()
    header_row_idx = identify_header_row(grid.rows)
    if header_row_idx is None:
        logger.warning("%s: No header in pinout table", component_id)
        return []

    col_map = map_pin_columns(grid.rows[header_row_idx])
    pins: list[PinDefinition] = []
    for row in grid.rows[header_row_idx + 1 :]:
        pin = extract_single_pin(row, col_map, grid.confidence)
        if pin is not None:
            pins.append(pin)

    return pins
