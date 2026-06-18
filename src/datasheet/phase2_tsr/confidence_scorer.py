"""Confidence scoring and grid selection for Phase 2 TSR.

Implements scoring algorithms for GridMatrix quality assessment and
best grid selection from dual-path (vector + VLM) extraction.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from src.datasheet.phase2_tsr._schemas import GridMatrix

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Scoring weights (must sum to 1.0)
WEIGHT_CELL_COUNT: float = 0.25
WEIGHT_EMPTY_RATIO: float = 0.25
WEIGHT_HEADER_DETECTED: float = 0.25
WEIGHT_PARSE_SUCCESS: float = 0.25

# Thresholds
MIN_CELL_COUNT: int = 4
MAX_EMPTY_CELL_RATIO: float = 0.3


def score_grid(grid: Optional[GridMatrix]) -> float:
    """Score a GridMatrix on 4 criteria with equal weight (0.25 each).

    Scoring criteria:
    1. Cell count > 4 (more cells = more likely valid)
    2. Empty cell ratio < 0.3 (too many empty = suspect)
    3. Header row detected (at least one is_header=True cell)
    4. Parse success (grid is not None and num_rows > 1)

    Args:
        grid: GridMatrix to score, or None

    Returns:
        Weighted aggregate score in [0.0, 1.0]

    Example:
        >>> grid = GridMatrix(cells=[...], num_rows=5, num_cols=4, ...)
        >>> score_grid(grid)
        0.85
    """
    if grid is None:
        return 0.0

    scores: list[float] = []

    # Criterion 1: Cell count > 4
    cell_count = len(grid.cells)
    cell_count_score = 1.0 if cell_count > MIN_CELL_COUNT else (cell_count / MIN_CELL_COUNT)
    scores.append(cell_count_score)

    # Criterion 2: Empty cell ratio < 0.3
    if cell_count == 0:
        empty_ratio_score = 0.0
    else:
        empty_count = sum(1 for c in grid.cells if not c.text.strip())
        empty_ratio = empty_count / cell_count
        empty_ratio_score = 1.0 if empty_ratio < MAX_EMPTY_CELL_RATIO else max(0.0, 1.0 - (empty_ratio - MAX_EMPTY_CELL_RATIO) * 2)
    scores.append(empty_ratio_score)

    # Criterion 3: Header row detected
    header_detected = any(c.is_header for c in grid.cells)
    header_score = 1.0 if header_detected else 0.0
    scores.append(header_score)

    # Criterion 4: Parse success (grid valid with >1 row)
    parse_success = grid.num_rows > 1 and grid.num_cols > 0
    parse_score = 1.0 if parse_success else 0.0
    scores.append(parse_score)

    # Weighted aggregate
    aggregate = (
        scores[0] * WEIGHT_CELL_COUNT +
        scores[1] * WEIGHT_EMPTY_RATIO +
        scores[2] * WEIGHT_HEADER_DETECTED +
        scores[3] * WEIGHT_PARSE_SUCCESS
    )

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, aggregate))


def pick_best_grid(
    a: Optional[GridMatrix],
    b: Optional[GridMatrix],
) -> GridMatrix:
    """Select best grid from dual-path extraction results.

    Selection logic:
    - If only one is not None, return it
    - If both None, raise ValueError
    - If both valid, return higher score_grid() result
    - Attach confidence = score_grid(winner) to returned grid

    Args:
        a: GridMatrix from Path A (vector), or None
        b: GridMatrix from Path B (VLM), or None

    Returns:
        Best GridMatrix with confidence updated to score_grid(winner)

    Raises:
        ValueError: If both grids are None ("Both TSR paths failed for this table crop")

    Example:
        >>> grid_a = extract_vector(...)
        >>> grid_b = extract_vlm(...)
        >>> best = pick_best_grid(grid_a, grid_b)
    """
    # Score both grids
    score_a = score_grid(a)
    score_b = score_grid(b)

    logger.debug(f"Path A score: {score_a:.3f}, Path B score: {score_b:.3f}")

    # Case 1: Only A valid
    if a is not None and b is None:
        logger.info(f"Selected Path A (only valid path), score={score_a:.3f}")
        return a.model_copy(update={"confidence": score_a})

    # Case 2: Only B valid
    if b is not None and a is None:
        logger.info(f"Selected Path B (only valid path), score={score_b:.3f}")
        return b.model_copy(update={"confidence": score_b})

    # Case 3: Both None
    if a is None and b is None:
        logger.error("Both TSR paths failed for this table crop")
        raise ValueError("Both TSR paths failed for this table crop")

    # Case 4: Both valid - pick higher score
    assert a is not None and b is not None
    if score_a >= score_b:
        logger.info(f"Selected Path A (score {score_a:.3f} > {score_b:.3f})")
        return a.model_copy(update={"confidence": score_a})
    else:
        logger.info(f"Selected Path B (score {score_b:.3f} > {score_a:.3f})")
        return b.model_copy(update={"confidence": score_b})
