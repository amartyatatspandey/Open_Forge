"""Phase 1-5 orchestrator for datasheet parsing pipeline.

This module provides the main entry point for parsing datasheet PDFs through
all five phases: Document Layout Analysis (DLA), Table Structure Recognition (TSR),
Semantic Extraction, Validation, and Layout Constraint Extraction.

Team A Output Contract:
    parse_datasheet(component_id, pdf_path, config) -> ComponentDatasheet

The pipeline orchestrates the complete extraction flow and handles error
management, logging, review queue integration, and result composition.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.datasheet.phase1_dla._schemas import Phase1Output
from src.datasheet.phase1_dla import process as phase1_dla
from src.datasheet.phase2_tsr import process as phase2_tsr
from src.datasheet.phase3_extract import process as phase3_extract
from src.datasheet.phase5_layout import extract_layout_constraints
from src.review.queue import enqueue
from src.schemas.datasheet import ComponentDatasheet, TableSectionType

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)


class DatasheetPipelineError(Exception):
    """Exception raised when a pipeline phase fails.

    Captures the failing phase name, component_id, and original exception
    for debugging and error reporting.

    Attributes:
        phase: Name of the phase that failed (e.g., "Phase 1", "Phase 3")
        component_id: Component ID being processed when failure occurred
        cause: Original exception that caused the pipeline failure
    """

    def __init__(self, phase: str, component_id: str, cause: Exception):
        """Initialize pipeline error with phase context.

        Args:
            phase: Name of the failing phase
            component_id: Component ID being processed
            cause: Original exception that caused failure
        """
        self.phase = phase
        self.component_id = component_id
        self.cause = cause
        super().__init__(f"Phase {phase} failed for {component_id}: {cause}")


def _has_layout_sections(phase1_output: Phase1Output) -> bool:
    """Check if Phase 1 output contains any layout recommendation sections.

    Args:
        phase1_output: Output from Phase 1 DLA

    Returns:
        True if any table crop has section_type == LAYOUT_RECOMMENDATIONS
    """
    for crop in phase1_output.table_crops:
        if crop.section_type == TableSectionType.LAYOUT_RECOMMENDATIONS:
            return True
    return False


def parse_datasheet(
    component_id: str,
    pdf_path: Path,
    config: Config,
) -> ComponentDatasheet:
    """Orchestrate all 5 phases to parse a single datasheet PDF.

    Phase ordering: 1 → 2 → 3 → 4 → 5 (only if layout sections detected)

    Phase 4 verdict is applied before Phase 5.
    Phase 5 constraints are added via model_copy — never mutate in place.
    If any phase raises an unhandled exception, re-raises as DatasheetPipelineError
    with the failing phase name and original exception attached.

    Args:
        component_id: Unique identifier for the component (e.g., "TPS62933DRLR")
        pdf_path: Path to the datasheet PDF file
        config: Application configuration with model paths and thresholds

    Returns:
        ComponentDatasheet with component_id set, all phases applied,
        review_required=True if phase 4 verdict is BLOCK or WARN.

    Raises:
        DatasheetPipelineError: If any pipeline phase fails unexpectedly
        FileNotFoundError: If pdf_path does not exist (before pipeline starts)

    Example:
        >>> from src.config import get_config
        >>> config = get_config()
        >>> datasheet = parse_datasheet("TPS62933", Path("datasheet.pdf"), config)
        >>> datasheet.component_id
        'TPS62933'
        >>> datasheet.extraction_confidence > 0.8
        True
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info(f"Starting datasheet pipeline for {component_id}: {pdf_path}")

    phase1_output = None
    phase2_output = None
    datasheet = None

    try:
        # Phase 1: Document Layout Analysis
        phase_name = "Phase 1"
        logger.info(f"{phase_name}: starting for {component_id}")
        start_time = time.time()

        phase1_output = phase1_dla(pdf_path, config)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"{phase_name}: completed for {component_id} in {duration_ms:.1f}ms, "
            f"found {len(phase1_output.table_crops)} table crops"
        )

        # Phase 2: Table Structure Recognition
        phase_name = "Phase 2"
        logger.info(f"{phase_name}: starting for {component_id}")
        start_time = time.time()

        phase2_output = phase2_tsr(phase1_output, config)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"{phase_name}: completed for {component_id} in {duration_ms:.1f}ms, "
            f"extracted {len(phase2_output.grids)} grids"
        )

        # Phase 3: Semantic Extraction
        phase_name = "Phase 3"
        logger.info(f"{phase_name}: starting for {component_id}")
        start_time = time.time()

        datasheet = phase3_extract(phase2_output, config)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"{phase_name}: completed for {component_id} in {duration_ms:.1f}ms, "
            f"extracted {len(datasheet.electrical_parameters)} parameters, "
            f"{len(datasheet.pins)} pins"
        )

        # Phase 4: Validation (apply verdict)
        phase_name = "Phase 4"
        logger.info(f"{phase_name}: starting for {component_id}")
        start_time = time.time()

        # Import here to avoid circular dependency if needed
        from src.datasheet.phase4_validate import apply_verdict, validate

        validation_result = validate(datasheet, config)

        # IMPORTANT: Capture the return value from apply_verdict
        # It returns a new object, never mutate in place
        datasheet = apply_verdict(datasheet, validation_result)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"{phase_name}: completed for {component_id} in {duration_ms:.1f}ms, "
            f"verdict={validation_result.verdict}, "
            f"review_required={datasheet.review_required}"
        )

        # Phase 5: Layout Constraint Extraction (conditional)
        if _has_layout_sections(phase1_output):
            phase_name = "Phase 5"
            logger.info(f"{phase_name}: starting for {component_id}")
            start_time = time.time()

            constraints = extract_layout_constraints(pdf_path, phase1_output, config)

            # Add constraints via model_copy — never mutate in place
            if constraints:
                datasheet = datasheet.model_copy(
                    update={"layout_constraints": constraints}
                )
                logger.info(
                    f"{phase_name}: completed for {component_id} in "
                    f"{duration_ms:.1f}ms, extracted {len(constraints)} constraints"
                )
            else:
                logger.info(
                    f"{phase_name}: completed for {component_id} in "
                    f"{duration_ms:.1f}ms, no constraints found"
                )

            duration_ms = (time.time() - start_time) * 1000
        else:
            logger.info(f"Phase 5: no layout sections detected, skipping for {component_id}")

        # Set component_id on the final datasheet
        datasheet = datasheet.model_copy(update={"component_id": component_id})

        # Queue routing: if review required, add to review queue
        if datasheet.review_required:
            logger.info(f"Queueing {component_id} for review (review_required=True)")
            # Reconstruct validation_result for queue if Phase 5 ran
            # Note: We need to pass the validation_result from Phase 4
            from src.datasheet.phase4_validate import validate

            validation_result_for_queue = validate(datasheet, config)
            enqueue(datasheet, validation_result_for_queue, config)

        logger.info(
            f"Pipeline completed for {component_id}: "
            f"confidence={datasheet.extraction_confidence:.3f}, "
            f"review_required={datasheet.review_required}"
        )

        return datasheet

    except DatasheetPipelineError:
        # Re-raise pipeline errors as-is
        raise
    except Exception as e:
        # Wrap any unhandled exception as DatasheetPipelineError
        logger.error(f"Pipeline failed at {phase_name} for {component_id}: {e}")
        raise DatasheetPipelineError(phase_name, component_id, e) from e
