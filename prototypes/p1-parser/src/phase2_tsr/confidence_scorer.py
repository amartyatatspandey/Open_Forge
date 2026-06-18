"""Heuristic confidence scoring for TSR grid candidates."""

from __future__ import annotations

import logging

from src.config import Config, get_config
from src.schemas.pipeline import GridMatrix

logger = logging.getLogger(__name__)


def score_grid(grid: GridMatrix, config: Config | None = None) -> float:
    """Score a GridMatrix on structural confidence heuristics.

    Args:
        grid: GridMatrix to score.
        config: Optional config override.

    Returns:
        Confidence score in [0.0, 1.0].
    """
    cfg = config or get_config()
    if not grid.rows:
        return 0.0

    score = 0.5
    col_lengths = [len(row) for row in grid.rows]
    consistent_cols = len(set(col_lengths)) == 1
    if consistent_cols:
        score += 0.25

    total_cells = sum(col_lengths)
    empty_cells = sum(1 for row in grid.rows for cell in row if not str(cell).strip())
    empty_ratio = empty_cells / total_cells if total_cells else 1.0
    if empty_ratio <= cfg.phase2_tsr.max_empty_cell_ratio:
        score += 0.15 * (1.0 - empty_ratio)
    else:
        score -= 0.2 * (empty_ratio - cfg.phase2_tsr.max_empty_cell_ratio)

    non_empty_rows = sum(1 for row in grid.rows if any(str(c).strip() for c in row))
    if non_empty_rows < len(grid.rows):
        score -= 0.1 * (len(grid.rows) - non_empty_rows) / len(grid.rows)

    if grid.source == "vector_path_A":
        score += cfg.phase2_tsr.vector_source_bonus

    score = max(0.0, min(1.0, score))
    logger.debug(
        "Scored grid (%s, %dx%d): %.3f",
        grid.source,
        grid.num_rows,
        grid.num_cols,
        score,
    )
    return score


def pick_best_grid(
    grid_a: GridMatrix | None,
    grid_b: GridMatrix | None,
    config: Config | None = None,
) -> GridMatrix | None:
    """Pick the best grid from Path A and Path B.

    Args:
        grid_a: Vector path result, or None if failed.
        grid_b: VLM path result, or None if failed.
        config: Optional config override.

    Returns:
        Best GridMatrix, or None if both paths failed.
    """
    if grid_a is None and grid_b is None:
        return None
    if grid_a is None:
        return grid_b
    if grid_b is None:
        return grid_a

    score_a = score_grid(grid_a, config=config)
    score_b = score_grid(grid_b, config=config)
    if score_a >= score_b:
        logger.info("Picked vector path (%.3f vs %.3f)", score_a, score_b)
        return grid_a
    logger.info("Picked VLM path (%.3f vs %.3f)", score_b, score_a)
    return grid_b
