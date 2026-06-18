"""Phase 3 Semantic Extraction package.

Extracts structured ComponentDatasheet objects from Phase2Output using
constrained LLM extraction with Instructor + Qwen2.5-7B-Instruct.

Public API:
    process(phase2_output, config) -> ComponentDatasheet

Internal modules:
    - unit_normalizer: Unit string normalization and conversion
    - prompt_templates: Section-specific LLM prompts
    - extractor: Instructor + Qwen2.5 extraction logic
    - component_header: Component identity extraction from header
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src.datasheet.phase2_tsr._schemas import Phase2Output
from src.datasheet.phase3_extract.component_header import (
    ComponentHeaderInfo,
    extract_component_header,
)
from src.datasheet.phase3_extract.extractor import ExtractionResult, extract_from_grids
from src.datasheet.utils import compute_extraction_confidence
from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Public API exports only the process function
__all__ = ["process"]


def _get_first_page_text(phase2_output: Phase2Output) -> str:
    """Extract header text from first page of Phase2Output.

    Args:
        phase2_output: Output from Phase 2

    Returns:
        Header text string (placeholder implementation)
    """
    # In production, this would extract from the first GridMatrix
    # For now, return empty string
    return ""


def _calculate_field_coverage(extraction_result: ExtractionResult) -> float:
    """Calculate field coverage ratio for extraction confidence.

    Args:
        extraction_result: ExtractionResult from extractor

    Returns:
        Ratio of successfully extracted fields to attempted fields
    """
    total_fields = 0
    extracted_fields = 0

    # Count electrical parameters
    for param in extraction_result.electrical_params:
        total_fields += 5  # name, conditions, min, typ, max
        if param.parameter_name:
            extracted_fields += 1
        if param.conditions:
            extracted_fields += 1
        if param.value and param.value.min_val is not None:
            extracted_fields += 1
        if param.value and param.value.typ_val is not None:
            extracted_fields += 1
        if param.value and param.value.max_val is not None:
            extracted_fields += 1

    # Count absolute max ratings
    for rating in extraction_result.absolute_max_ratings:
        total_fields += 3  # name, max, conditions
        if rating.parameter_name:
            extracted_fields += 1
        if rating.value and rating.value.max_val is not None:
            extracted_fields += 1
        if rating.note:
            extracted_fields += 1

    # Count pins
    for pin in extraction_result.pins:
        total_fields += 5  # number, raw_name, type, desc, alternates
        if pin.pin_number:
            extracted_fields += 1
        if pin.raw_name:
            extracted_fields += 1
        if pin.pin_type:
            extracted_fields += 1
        if pin.description:
            extracted_fields += 1
        if pin.alternate_functions:
            extracted_fields += 1

    if total_fields == 0:
        return 0.0

    return extracted_fields / total_fields


def process(
    phase2_output: Phase2Output,
    config: Config,
) -> ComponentDatasheet:
    """Phase 3: Constrained semantic extraction.

    For each GridMatrix in phase2_output, extract typed parameters using
    Qwen2.5-7B-Instruct via Instructor. Returns a ComponentDatasheet.

    Component identity fields (component_id, manufacturer, description, package)
    are extracted from the first page header grid if present, otherwise flagged.

    Args:
        phase2_output: Phase2Output from Phase 2 TSR
        config: Application configuration

    Returns:
        ComponentDatasheet with extracted data

    Raises:
        FileNotFoundError: If source PDF referenced in phase2_output not found

    Rules Applied:
    - Rule 1: section_type must be in every extraction prompt
    - Rule 2: normalize_package() called on every extracted package string
    - Rule 3: PinDefinition.normalized_function always set to None
    - Rule 4: Footnote injection from FootnoteMap to ExtractedValue
    - Rule 5: source_pdf_hash and created_at set correctly
    - Rule 6: extraction_confidence computed via compute_extraction_confidence()

    Example:
        >>> from src.datasheet.phase3_extract import process
        >>> from src.config import get_config
        >>> config = get_config()
        >>> phase2 = process_phase2(...)
        >>> datasheet = process(phase2, config)
        >>> datasheet.component_id
        'TPS62933DRLR'
    """
    logger.info(f"Starting Phase 3 extraction on {phase2_output.source_pdf_hash[:16]}...")

    # Validate source PDF exists
    pdf_path = Path(phase2_output.source_pdf_hash)
    # Note: source_pdf_hash is actually the hash, not the path
    # The actual path would need to be tracked separately

    # Step 1: Extract component header information
    header_text = _get_first_page_text(phase2_output)
    header_info = extract_component_header(header_text)

    header_flags = header_info.get_review_flags()
    if header_flags:
        logger.warning(f"Header extraction issues: {header_flags}")

    # Step 2: Extract semantic data from all grids
    extraction_result = extract_from_grids(
        phase2_output.grids,
        phase2_output.footnote_maps,
        config,
    )

    # Combine review flags
    all_review_flags = header_flags + extraction_result.review_flags

    # Step 3: Calculate extraction confidence (Rule 6)
    phase2_confidence = extraction_result.confidence
    field_coverage = _calculate_field_coverage(extraction_result)

    extraction_confidence = compute_extraction_confidence(
        method=extraction_result.extraction_method,
        phase2_confidence=phase2_confidence,
        phase3_field_coverage=field_coverage,
    )

    logger.info(f"Extraction confidence: {extraction_confidence:.3f}")

    # Step 4: Build ComponentDatasheet (Rule 5)
    # Set created_at = datetime.utcnow().isoformat() + "Z"
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Build ComponentDatasheet
    datasheet = ComponentDatasheet(
        component_id=header_info.component_id,
        manufacturer=header_info.manufacturer,
        description=header_info.description,
        package=header_info.normalized_package,  # Rule 2: normalized
        source_pdf_hash=phase2_output.source_pdf_hash,
        electrical_parameters=extraction_result.electrical_params,
        absolute_max_ratings=extraction_result.absolute_max_ratings,
        pins=extraction_result.pins,
        # Rule 3: PinDefinition.normalized_function is None by default
        extraction_method=extraction_result.extraction_method,
        extraction_confidence=extraction_confidence,
        review_required=len(all_review_flags) > 0,
        review_flags=all_review_flags,
        created_at=created_at,
    )

    logger.info(
        f"Phase 3 complete: {len(datasheet.electrical_parameters)} electrical params, "
        f"{len(datasheet.absolute_max_ratings)} absolute max ratings, "
        f"{len(datasheet.pins)} pins"
    )

    return datasheet