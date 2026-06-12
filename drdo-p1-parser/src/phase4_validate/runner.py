"""Phase 4 orchestrator: validation and KiCad export."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config import Config, get_config
from src.phase4_validate.kicad_exporter import KiCadExport, export_to_kicad
from src.phase4_validate.validator import run_full_validation
from src.schemas.datasheet import ComponentDatasheet, ValidationResult

logger = logging.getLogger(__name__)


def run_phase4(
    datasheet: ComponentDatasheet,
    config: Config | None = None,
) -> tuple[ValidationResult, KiCadExport]:
    """Full Phase 4 pipeline: validate and export to KiCad JSON."""
    cfg = config or get_config()

    logger.info("Phase 4: Validating & exporting %s", datasheet.component_id)

    validation = run_full_validation(datasheet, cfg)
    logger.info(
        "  Validation: passed=%s, confidence=%.2f",
        validation.passed,
        validation.confidence_score,
    )

    export = export_to_kicad(datasheet, validation)
    logger.info("  KiCad export: %s", export.validation_status)

    _write_outputs(datasheet.component_id, validation, export, cfg)
    return validation, export


def save_validation_result(
    validation: ValidationResult,
    output_path: Path,
) -> None:
    """Save validation result to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(validation.model_dump(), indent=2),
        encoding="utf-8",
    )
    logger.info("Validation result saved: %s", output_path)


def save_kicad_export(
    export: KiCadExport,
    output_path: Path,
) -> None:
    """Save KiCad export to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(export.model_dump(), indent=2),
        encoding="utf-8",
    )
    logger.info("KiCad export saved: %s", output_path)


def _write_outputs(
    component_id: str,
    validation: ValidationResult,
    export: KiCadExport,
    config: Config,
) -> None:
    """Write Phase 4 outputs to configured directory."""
    out_dir = config.pipeline.phase4_output_dir
    save_validation_result(validation, out_dir / f"{component_id}_validation.json")
    save_kicad_export(export, out_dir / f"{component_id}_kicad.json")
