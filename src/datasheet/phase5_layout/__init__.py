"""Phase 5 Layout Section Extraction package.

Extracts PlacementConstraint objects from layout recommendation sections
in datasheets using LLM-based spatial parsing.

Public API:
    extract_layout_constraints(pdf_path, phase1_output, config) -> list[PlacementConstraint]

Internal modules:
    - text_extractor: pdfplumber-based text extraction from specific pages
    - spatial_parser: LLM extraction using Instructor + Qwen2.5-7B
    - type_resolver: relative_to_type classification heuristics
    - constraint_validator: post-LLM validation and filtering
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.datasheet.phase1_dla._schemas import Phase1Output
from src.datasheet.phase5_layout.constraint_validator import validate_and_finalize
from src.datasheet.phase5_layout.spatial_parser import parse_constraints
from src.datasheet.phase5_layout.text_extractor import extract_page_texts
from src.schemas.datasheet import PlacementConstraint, TableSectionType

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Public API exports only the extract_layout_constraints function
__all__ = ["extract_layout_constraints"]


def _get_layout_pages(phase1_output: Phase1Output) -> list[int]:
    """Find all page numbers containing LAYOUT_RECOMMENDATIONS tables.

    Args:
        phase1_output: Phase1Output from Phase 1 DLA

    Returns:
        Sorted list of unique page numbers with layout recommendation tables
    """
    layout_pages: set[int] = set()

    for crop in phase1_output.table_crops:
        if crop.section_type == TableSectionType.LAYOUT_RECOMMENDATIONS:
            layout_pages.add(crop.page_number)
            logger.debug(
                f"Found LAYOUT_RECOMMENDATIONS on page {crop.page_number}"
            )

    return sorted(layout_pages)


def extract_layout_constraints(
    pdf_path: Path,
    phase1_output: Phase1Output,
    config: Config,
) -> list[PlacementConstraint]:
    """Phase 5: Extract PlacementConstraint objects from layout recommendation sections.

    Finds all TableCrops where section_type == LAYOUT_RECOMMENDATIONS.
    If none exist, returns empty list immediately — does not process any
    other section type.

    Extracts plain text from those pages using pdfplumber.
    Sends text to Qwen2.5-7B-Instruct via Instructor to produce
    PlacementConstraint objects.

    Returns empty list on any model failure — never raises.

    Args:
        pdf_path: Path to the source PDF file
        phase1_output: Phase1Output from Phase 1 containing table crops
        config: Application configuration with model paths

    Returns:
        List of validated PlacementConstraint objects extracted from layout
        recommendation sections. Returns empty list if no layout sections
        found or if extraction fails.

    Never raises exceptions — logs warnings and returns empty list on failure.

    Example:
        >>> from src.datasheet.phase5_layout import extract_layout_constraints
        >>> from src.config import get_config
        >>> config = get_config()
        >>> phase1 = process_dla(Path("datasheet.pdf"), config)
        >>> constraints = extract_layout_constraints(Path("datasheet.pdf"), phase1, config)
        >>> len(constraints)
        3
    """
    logger.info("Phase 5: Starting layout constraint extraction")

    # Step 1: Find layout recommendation pages
    layout_pages = _get_layout_pages(phase1_output)

    if not layout_pages:
        logger.info("No LAYOUT_RECOMMENDATIONS sections found, returning empty list")
        return []

    logger.info(f"Found {len(layout_pages)} pages with layout recommendations: {layout_pages}")

    # Step 2: Extract text from layout pages
    page_blocks = extract_page_texts(pdf_path, layout_pages)

    if not page_blocks:
        logger.warning("No text extracted from layout recommendation pages")
        return []

    logger.info(f"Extracted text from {len(page_blocks)} pages")

    # Step 3: Parse constraints using LLM
    extraction_result = parse_constraints(page_blocks, config)

    if not extraction_result.constraints:
        logger.info("No constraints extracted from layout text")
        return []

    logger.info(f"LLM extracted {len(extraction_result.constraints)} raw constraints")

    # Step 4: Validate and finalize constraints
    validated_constraints = validate_and_finalize(extraction_result)

    logger.info(
        f"Phase 5 complete: {len(validated_constraints)} validated constraints "
        f"from {len(layout_pages)} layout pages"
    )

    return validated_constraints
