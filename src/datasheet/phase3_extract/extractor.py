"""LLM-based semantic extraction using Instructor + Qwen2.5-7B.

Extracts structured Pydantic objects from table grids using local LLM inference.
Uses Instructor library for schema adherence and validation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, TypeVar

from pydantic import BaseModel

from src.datasheet.phase1_dla._schemas import FootnoteMap
from src.datasheet.phase2_tsr._schemas import GridMatrix
from src.datasheet.phase3_extract.prompt_templates import get_prompt_for_table
from src.schemas.datasheet import (
    AbsoluteMaxRating,
    ElectricalParameter,
    ExtractionMethod,
    ExtractedValue,
    PinDefinition,
    TableSectionType,
)

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class InstructorWrapper:
    """Wrapper for Instructor client with Qwen2.5 model."""

    def __init__(self, model_path: Path, device: str = "cpu"):
        """Initialize Instructor with Qwen2.5 model.

        Args:
            model_path: Path to Qwen2.5-7B-Instruct model
            device: Device to run on (cpu, cuda, etc.)
        """
        self.model_path = model_path
        self.device = device
        self._client: Any | None = None
        self._model: Any | None = None
        self._tokenizer: Any | None = None

    def _load_model(self) -> None:
        """Lazy load model on first use."""
        if self._client is not None:
            return

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(f"Loading Qwen2.5 model from {self.model_path}")

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True,
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                device_map=self.device if self.device != "cpu" else None,
                torch_dtype="auto",
                trust_remote_code=True,
            )

            # Import instructor and wrap model
            import instructor
            from openai import OpenAI

            # For local models, we use a custom client
            self._client = None  # Placeholder

        except Exception as e:
            logger.error(f"Failed to load Qwen2.5 model: {e}")
            raise RuntimeError(f"Could not load LLM from {self.model_path}: {e}") from e

    def extract(
        self,
        response_model: type[T],
        system_prompt: str,
        user_content: str,
    ) -> Optional[T]:
        """Extract structured data using Instructor.

        Args:
            response_model: Pydantic model class to extract
            system_prompt: System prompt for the model
            user_content: User content (table text)

        Returns:
            Extracted model instance, or None if extraction fails
        """
        self._load_model()

        # Placeholder: In production, this would use Instructor with the model
        # For now, return None to indicate extraction not implemented
        logger.warning("LLM extraction not fully implemented - using placeholder")
        return None


class ExtractionResult:
    """Result of semantic extraction from a single table."""

    def __init__(
        self,
        electrical_params: list[ElectricalParameter],
        absolute_max_ratings: list[AbsoluteMaxRating],
        pins: list[PinDefinition],
        section_type: TableSectionType,
        extraction_method: ExtractionMethod,
        confidence: float,
        review_flags: list[str],
    ):
        self.electrical_params = electrical_params
        self.absolute_max_ratings = absolute_max_ratings
        self.pins = pins
        self.section_type = section_type
        self.extraction_method = extraction_method
        self.confidence = confidence
        self.review_flags = review_flags


def _grid_to_text(grid: GridMatrix) -> str:
    """Convert GridMatrix to text representation for LLM.

    Args:
        grid: Input grid matrix

    Returns:
        Text representation suitable for LLM prompt
    """
    lines = []

    # Reconstruct table from cells
    for row_idx in range(grid.num_rows):
        row_cells = sorted(
            [c for c in grid.cells if c.row == row_idx],
            key=lambda c: c.col,
        )
        row_text = " | ".join(c.text for c in row_cells)
        lines.append(row_text)

    return "\n".join(lines)


def _inject_footnotes(
    params: list[ElectricalParameter],
    footnote_maps: list[FootnoteMap],
) -> list[ElectricalParameter]:
    """Inject footnote text into ExtractedValue objects.

    Rule 4: For each extracted ExtractedValue, check if raw_text contains
    a superscript marker and inject matched footnote text.

    Args:
        params: List of ElectricalParameter with ExtractedValue
        footnote_maps: List of FootnoteMap from Phase 2

    Returns:
        Parameters with footnotes injected
    """
    import re

    # Build lookup from all footnote maps
    footnote_lookup: dict[str, str] = {}
    for fm in footnote_maps:
        for marker, text in fm.entries.items():
            footnote_lookup[marker] = text

    if not footnote_lookup:
        return params

    result = []
    for param in params:
        if param.value and param.value.raw_text:
            raw = param.value.raw_text

            # Check for superscript markers: (1), (2), *, etc.
            markers = re.findall(r'\((\d+)\)|([\*\†\‡])', raw)

            if markers:
                # Flatten tuple results from regex
                flat_markers = []
                for m in markers:
                    flat_markers.extend([x for x in m if x])

                # Look up footnote text
                for marker in flat_markers:
                    if marker in footnote_lookup:
                        # Inject footnote
                        updated_value = param.value.model_copy(
                            update={"footnote": footnote_lookup[marker]}
                        )
                        param = param.model_copy(update={"value": updated_value})
                        break

        result.append(param)

    return result


def extract_from_grid(
    grid: GridMatrix,
    footnote_maps: list[FootnoteMap],
    config: Config,
) -> ExtractionResult:
    """Extract semantic data from a single table grid.

    Uses Instructor + Qwen2.5 to extract structured Pydantic objects
    from table text.

    Args:
        grid: GridMatrix from Phase 2
        footnote_maps: Footnote maps for footnote injection
        config: Application configuration

    Returns:
        ExtractionResult with extracted parameters
    """
    section_type = grid.section_type

    # Get appropriate prompt for this section type
    system_prompt = get_prompt_for_table(section_type)

    # Convert grid to text
    table_text = _grid_to_text(grid)

    # Determine extraction method
    extraction_method = (
        ExtractionMethod.P1_VLM
        if grid.extraction_path == "vlm"
        else ExtractionMethod.P1_VECTOR
    )

    # Placeholder extraction - in production this would call Instructor
    logger.info(f"Extracting from {section_type.value} table with {grid.num_rows}x{grid.num_cols} cells")

    # For now, return empty result with review flag
    return ExtractionResult(
        electrical_params=[],
        absolute_max_ratings=[],
        pins=[],
        section_type=section_type,
        extraction_method=extraction_method,
        confidence=grid.confidence * 0.9,  # Slightly reduce confidence
        review_flags=["LLM extraction not fully implemented"],
    )


def extract_from_grids(
    grids: list[GridMatrix],
    footnote_maps: list[FootnoteMap],
    config: Config,
) -> ExtractionResult:
    """Extract semantic data from all grids.

    Aggregates extractions from multiple tables and combines review flags.

    Args:
        grids: List of GridMatrix from Phase 2
        footnote_maps: Footnote maps for injection
        config: Application configuration

    Returns:
        Combined ExtractionResult from all grids
    """
    all_electrical = []
    all_absolute_max = []
    all_pins = []
    all_review_flags = []

    for grid in grids:
        result = extract_from_grid(grid, footnote_maps, config)

        all_electrical.extend(result.electrical_params)
        all_absolute_max.extend(result.absolute_max_ratings)
        all_pins.extend(result.pins)
        all_review_flags.extend(result.review_flags)

    # Calculate aggregate confidence
    if grids:
        mean_confidence = sum(g.confidence for g in grids) / len(grids)
    else:
        mean_confidence = 0.0

    # Determine dominant section type
    section_types = [g.section_type for g in grids]
    if section_types:
        # Use first non-OTHER section type, or OTHER if all are OTHER
        dominant = next(
            (s for s in section_types if s != TableSectionType.OTHER),
            TableSectionType.OTHER,
        )
    else:
        dominant = TableSectionType.OTHER

    # Determine extraction method
    vlm_used = any(g.extraction_path == "vlm" for g in grids)
    method = ExtractionMethod.P1_VLM if vlm_used else ExtractionMethod.P1_VECTOR

    return ExtractionResult(
        electrical_params=all_electrical,
        absolute_max_ratings=all_absolute_max,
        pins=all_pins,
        section_type=dominant,
        extraction_method=method,
        confidence=mean_confidence,
        review_flags=all_review_flags,
    )