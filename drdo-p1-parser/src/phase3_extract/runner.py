"""Phase 3 orchestrator: semantic extraction from Phase 2 grids."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.config import Config, get_config
from src.phase3_extract.absolute_max_extractor import extract_absolute_max_ratings
from src.phase3_extract.footnote_resolver import resolve_footnotes_in_extraction
from src.phase3_extract.parameter_extractor import extract_electrical_parameters
from src.phase3_extract.pinout_extractor import extract_pins
from src.phase3_extract.validation import validate_extracted_data
from src.schemas.datasheet import ComponentDatasheet, DatasheetSection
from src.schemas.pipeline import Phase2Output

logger = logging.getLogger(__name__)


def _component_id_from_phase2(phase2_output: Phase2Output) -> str:
    """Resolve component ID from Phase 2 metadata or PDF path."""
    component_id = phase2_output.metadata.get("component_id")
    if component_id:
        return str(component_id)
    stem = Path(phase2_output.pdf_path).stem
    for prefix in ("TI_", "_v1"):
        stem = stem.replace(prefix, "")
    return stem


def run_phase3(
    phase2_output: Phase2Output,
    config: Config | None = None,
) -> ComponentDatasheet:
    """Run full Phase 3 extraction pipeline on Phase 2 output.

    Args:
        phase2_output: Structured grids from Phase 2 TSR.
        config: Optional config override.

    Returns:
        ComponentDatasheet with extracted sections and validation.
    """
    cfg = config or get_config()
    component_id = _component_id_from_phase2(phase2_output)
    footnote_map = phase2_output.metadata.get("footnote_map") or {}

    logger.info(
        "Phase 3: Extracting %s from %s",
        component_id,
        phase2_output.pdf_path,
    )

    all_parameters = []
    all_pins = []
    all_abs_max = []
    sections: list[DatasheetSection] = []

    for grid in phase2_output.grids:
        page_range = (grid.page_number, grid.page_number)
        logger.debug(
            "  Processing %s table (%dr × %dc)",
            grid.section_type,
            grid.num_rows,
            grid.num_cols,
        )

        if grid.section_type == "electrical_characteristics":
            params = extract_electrical_parameters(
                grid, component_id, footnote_map, cfg
            )
            all_parameters.extend(params)
            sections.append(
                DatasheetSection(
                    section_type="electrical_characteristics",
                    section_heading=grid.heading_text,
                    page_range=page_range,
                    table_confidence=grid.confidence,
                    parameters=params,
                )
            )
        elif grid.section_type == "pinout":
            pins_list = extract_pins(grid, component_id, cfg)
            all_pins.extend(pins_list)
            sections.append(
                DatasheetSection(
                    section_type="pinout",
                    section_heading=grid.heading_text,
                    page_range=page_range,
                    table_confidence=grid.confidence,
                    pins=pins_list,
                )
            )
        elif grid.section_type == "absolute_maximum_ratings":
            abs_max = extract_absolute_max_ratings(grid, component_id, cfg)
            all_abs_max.extend(abs_max)
            sections.append(
                DatasheetSection(
                    section_type="absolute_maximum_ratings",
                    section_heading=grid.heading_text,
                    page_range=page_range,
                    table_confidence=grid.confidence,
                    abs_max_ratings=abs_max,
                )
            )

    resolve_footnotes_in_extraction(
        all_parameters, all_pins, all_abs_max, footnote_map
    )

    validation = validate_extracted_data(
        component_id, all_parameters, all_pins, all_abs_max, cfg
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    datasheet = ComponentDatasheet(
        component_id=component_id,
        manufacturer="Texas Instruments",
        extraction_timestamp=timestamp,
        sections=sections,
        validation=validation,
    )

    _write_debug_output(datasheet, phase2_output, cfg)
    logger.info(
        "Phase 3 complete: %d params, %d pins, %d abs-max for %s",
        len(all_parameters),
        len(all_pins),
        len(all_abs_max),
        component_id,
    )
    return datasheet


def _write_debug_output(
    datasheet: ComponentDatasheet,
    phase2_output: Phase2Output,
    config: Config,
) -> None:
    """Write optional debug metadata to phase3 output directory."""
    out_dir = config.pipeline.phase3_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(phase2_output.pdf_path).stem
    meta_path = out_dir / f"{stem}_phase3_meta.json"
    meta = {
        "component_id": datasheet.component_id,
        "pdf_path": phase2_output.pdf_path,
        "num_sections": len(datasheet.sections),
        "num_parameters": len(datasheet.all_parameters),
        "num_pins": len(datasheet.all_pins),
        "validation_passed": datasheet.validation.passed if datasheet.validation else None,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
