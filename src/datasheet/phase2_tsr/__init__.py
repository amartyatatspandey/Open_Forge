"""Phase 2 Table Structure Recognition (TSR) package.

This package implements dual-path table structure recognition:
- Path A (Vector): pdfplumber + Camelot for bordered tables
- Path B (VLM): Qwen2-VL-7B for borderless tables

The only public export is `process()` which orchestrates both paths
and returns the best grid for each table crop.

Usage:
    from src.datasheet.phase2_tsr import process
    from src.config import get_config

    config = get_config()
    result = process(phase1_output, config)
    # result is Phase2Output with reconstructed grids
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.datasheet.phase1_dla._schemas import Phase1Output, TableCrop
from src.datasheet.phase2_tsr._schemas import GridMatrix, Phase2Output
from src.datasheet.phase2_tsr.confidence_scorer import pick_best_grid
from src.datasheet.phase2_tsr.merged_cell_handler import detect_merged_cells
from src.datasheet.phase2_tsr.path_a_vector import extract_table_vector_path
from src.datasheet.phase2_tsr.path_b_vlm import extract_table_vlm_path

if TYPE_CHECKING:
    from src.config import Config
    from src.datasheet.phase1_dla._schemas import Phase1Output

logger = logging.getLogger(__name__)

# Public API exports only the process function
__all__ = ["process"]


def _process_single_table(
    pdf_path: Path,
    table_crop: TableCrop,
    table_index: int,
    config: Config,
) -> GridMatrix:
    """Process a single table crop through dual-path extraction.

    Runs both vector and VLM paths in parallel (conceptually) and
    selects the best result using confidence scoring.

    Args:
        pdf_path: Path to source PDF
        table_crop: TableCrop from Phase 1
        table_index: Index of table within page
        config: Application configuration

    Returns:
        GridMatrix with best extraction result

    Raises:
        ValueError: If both TSR paths fail for this table
    """
    page_number = table_crop.page_number
    logger.info(f"Processing table {table_index} on page {page_number}")

    # Path A: Vector extraction (pdfplumber + Camelot)
    try:
        grid_a = extract_table_vector_path(
            pdf_path,
            table_crop,
            table_index,
            config,
        )
    except Exception as e:
        logger.warning(f"Path A failed for table {table_index}: {e}")
        grid_a = None

    # Path B: VLM extraction (Qwen2-VL-7B)
    try:
        grid_b = extract_table_vlm_path(
            pdf_path,
            table_crop,
            table_index,
            config,
        )
    except Exception as e:
        logger.warning(f"Path B failed for table {table_index}: {e}")
        grid_b = None

    # Select best grid using confidence scoring
    try:
        best_grid = pick_best_grid(grid_a, grid_b)
    except ValueError as e:
        logger.error(f"Both paths failed for table {table_index}: {e}")
        raise

    # Detect merged cells
    best_grid = detect_merged_cells(best_grid)

    logger.info(
        f"Table {table_index}: Selected {best_grid.extraction_path} path "
        f"with confidence {best_grid.confidence:.3f}, "
        f"merged_cells={best_grid.has_merged_cells}"
    )

    return best_grid


def process(
    phase1_output: Phase1Output,
    config: Config,
) -> Phase2Output:
    """Phase 2: Table Structure Recognition.

    For each TableCrop in phase1_output, reconstruct the grid matrix using
dual-path extraction. Pass footnote_maps through unchanged to Phase2Output.

    Args:
        phase1_output: Phase1Output from Phase 1 DLA
        config: Application configuration

    Returns:
        Phase2Output containing reconstructed grids and footnote maps

    Raises:
        FileNotFoundError: If source PDF not found
        ValueError: If all TSR paths fail for a table

    Example:
        >>> from src.datasheet.phase2_tsr import process
        >>> from src.config import get_config
        >>> config = get_config()
        >>> phase1 = process_phase1(Path("datasheet.pdf"), config)
        >>> phase2 = process(phase1, config)
        >>> len(phase2.grids)
        3
    """
    start_time = time.time()

    pdf_path = Path(phase1_output.pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info(f"Starting Phase 2 TSR on {pdf_path}")
    logger.info(f"Processing {len(phase1_output.table_crops)} table crops")

    # Process each table crop
    grids: list[GridMatrix] = []
    for table_index, table_crop in enumerate(phase1_output.table_crops):
        try:
            grid = _process_single_table(
                pdf_path,
                table_crop,
                table_index,
                config,
            )
            grids.append(grid)
        except ValueError as e:
            # Both paths failed for this table
            logger.error(f"Failed to extract table {table_index}: {e}")
            # Continue with other tables

    processing_time_ms = (time.time() - start_time) * 1000

    logger.info(
        f"Phase 2 complete: {len(grids)} grids extracted, "
        f"{processing_time_ms:.1f}ms"
    )

    return Phase2Output(
        source_pdf_hash=phase1_output.source_pdf_hash,
        grids=grids,
        footnote_maps=phase1_output.footnote_maps,  # Pass through unchanged
        processing_time_ms=processing_time_ms,
    )
