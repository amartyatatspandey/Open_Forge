"""Unit tests for TSR confidence scoring."""

from src.phase2_tsr.confidence_scorer import pick_best_grid, score_grid
from src.schemas.pipeline import GridMatrix


def test_score_consistent_grid() -> None:
    grid = GridMatrix(
        rows=[["A", "B", "C", "D"]] * 5,
        section_type="electrical_characteristics",
        page_number=5,
        confidence=0.95,
        source="vector_path_A",
    )
    assert score_grid(grid) > 0.9


def test_score_sparse_grid() -> None:
    grid = GridMatrix(
        rows=[["A", "", "", "D"], ["", "B", "", ""], ["C", "", "", "D"]],
        section_type="pinout",
        page_number=3,
        confidence=0.70,
        source="vlm_path_B",
    )
    dense = GridMatrix(
        rows=[["A", "B", "C", "D"]] * 3,
        section_type="pinout",
        page_number=3,
        confidence=0.70,
        source="vlm_path_B",
    )
    assert score_grid(grid) < score_grid(dense)


def test_pick_best_grid_vector_wins() -> None:
    grid_a = GridMatrix(
        rows=[["A", "B"]] * 5,
        section_type="electrical_characteristics",
        page_number=5,
        confidence=0.9,
        source="vector_path_A",
    )
    grid_b = GridMatrix(
        rows=[["A", "B"], ["C", "D", "E"]],
        section_type="electrical_characteristics",
        page_number=5,
        confidence=0.7,
        source="vlm_path_B",
    )
    best = pick_best_grid(grid_a, grid_b)
    assert best is not None
    assert best.source == "vector_path_A"


def test_pick_best_grid_single_path() -> None:
    grid_a = GridMatrix(
        rows=[["A"]],
        section_type="other",
        confidence=0.5,
        source="vector_path_A",
    )
    assert pick_best_grid(grid_a, None) == grid_a
    assert pick_best_grid(None, None) is None
