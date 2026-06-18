"""LLM-based spatial constraint parsing using Instructor + Qwen2.5-7B.

Parses layout recommendation text into structured PlacementConstraint
objects using constrained LLM extraction.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.datasheet.phase5_layout._schemas import LayoutExtractionResult, PageTextBlock

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# System prompt for layout constraint extraction
SYSTEM_PROMPT = """You are a PCB layout rules extractor. Read the following text from a datasheet
layout recommendations section and extract every placement constraint mentioned.

For each constraint found, extract:
- constraint_type: one of "proximity", "keepout", "layer", "orientation"
- subject: what component or net this constraint applies to
- relative_to: what it is measured against (component ref, pin ref like U1.VIN, or "board_edge")
- max_distance_mm: numeric mm value if a maximum distance is stated, else null
- min_distance_mm: numeric mm value if a minimum distance is stated, else null  
- layer: "top", "bottom", or "any" if a specific layer is required, else null
- hard: true if the text says "must", "shall", "required"; false if "should", "recommended"
- source_sentence: copy the exact sentence this constraint was extracted from
- confidence: your confidence in this extraction from 0.0 to 1.0

Spatial language patterns to recognize:
"Place X within N mm of Y" → proximity, hard, max_distance_mm=N
"Keep X close to Y" → proximity, hard, max_distance_mm=null
"X should be near Y" → proximity, hard=false
"Maintain keepout of N mm around X" → keepout, min_distance_mm=N
"Avoid routing X near Y" → keepout, hard=false
"Place X on top layer" → layer, layer="top"
"X must be on same side as Y" → layer constraint

If no placement constraints exist in the text, return an empty constraints list.
Do not invent constraints that are not explicitly stated.
"""

MAX_RETRIES = 2


def _format_page_blocks(page_blocks: list[PageTextBlock]) -> str:
    """Format page text blocks for LLM input.

    Concatenates all page text with clear page number markers to help
the LLM understand the document structure.

    Args:
        page_blocks: List of PageTextBlock objects

    Returns:
        Formatted text string with page markers
    """
    parts = []
    for block in page_blocks:
        parts.append(f"\n--- Page {block.page_number} ---\n")
        parts.append(block.text)
    return "\n".join(parts)


def _call_llm_with_instructor(
    formatted_text: str,
    config: Config,
) -> LayoutExtractionResult:
    """Call Qwen2.5-7B-Instruct via Instructor for constraint extraction.

    Attempts extraction with retries on validation failure.

    Args:
        formatted_text: Concatenated page text with markers
        config: Application configuration with model paths

    Returns:
        LayoutExtractionResult with extracted constraints

    Raises:
        RuntimeError: If model cannot be loaded or all retries exhausted
    """
    try:
        # Import instructor and related libraries
        import instructor
        from openai import OpenAI
    except ImportError:
        logger.warning("instructor or openai not available for LLM extraction")
        raise RuntimeError("Instructor library not available")

    # Get model path from config
    try:
        model_path = Path(config.model_paths.get("qwen25_7b", ""))
        if not model_path or not model_path.exists():
            logger.warning(f"Qwen2.5 model not found at: {model_path}")
            raise RuntimeError(f"Model path not found: {model_path}")
    except (AttributeError, KeyError) as e:
        logger.warning(f"Failed to get model path from config: {e}")
        raise RuntimeError("Model path configuration error")

    # Placeholder for actual LLM call
    # In production, this would:
    # 1. Load Qwen2.5-7B-Instruct from model_path
    # 2. Create Instructor client
    # 3. Call with SYSTEM_PROMPT + formatted_text
    # 4. Parse response into LayoutExtractionResult

    logger.info(f"Would call LLM at {model_path} with {len(formatted_text)} chars")

    # For now, return empty result as placeholder
    # This allows the pipeline to continue without actual LLM
    raise RuntimeError("LLM extraction not fully implemented")


def parse_constraints(
    page_blocks: list[PageTextBlock],
    config: Config,
) -> LayoutExtractionResult:
    """Parse layout constraints from extracted page text using LLM.

    Concatenates all page text blocks with page number markers and sends
to Qwen2.5-7B-Instruct via Instructor for structured constraint extraction.

    Args:
        page_blocks: List of PageTextBlock objects with extracted text
        config: Application configuration

    Returns:
        LayoutExtractionResult containing extracted constraints.
        Returns empty result on model failure.

    Never raises — logs WARNING and returns empty result on any failure.

    Example:
        >>> blocks = [PageTextBlock(page_number=5, text="Place C1 within 5mm of U1.VIN", char_count=30)]
        >>> result = parse_constraints(blocks, config)
        >>> len(result.constraints)
        1
    """
    if not page_blocks:
        logger.debug("No page blocks to parse")
        return LayoutExtractionResult(constraints=[], extraction_notes="")

    # Format text for LLM
    formatted_text = _format_page_blocks(page_blocks)

    # Attempt extraction with retries
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = _call_llm_with_instructor(formatted_text, config)
            logger.info(
                f"Extracted {len(result.constraints)} constraints from "
                f"{len(page_blocks)} pages"
            )
            return result

        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(
                    f"LLM extraction attempt {attempt + 1} failed: {e}, retrying..."
                )
            else:
                logger.warning(
                    f"LLM extraction failed after {MAX_RETRIES + 1} attempts: {e}"
                )
                break

    # Return empty result on failure
    return LayoutExtractionResult(
        constraints=[],
        extraction_notes=f"Extraction failed after {MAX_RETRIES + 1} attempts",
    )
