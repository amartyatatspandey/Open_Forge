"""Unit tests for merged cell normalization."""

from src.phase2_tsr.merged_cell_handler import infer_col_count, normalise_merged_cells


def test_normalise_ragged_rows() -> None:
    rows = [["A", "B"], ["C"]]
    result = normalise_merged_cells(rows)
    assert all(len(row) == 2 for row in result)
    assert result[1][1] == ""


def test_normalise_colspan() -> None:
    rows = [["Name →→→", "Value"]]
    result = normalise_merged_cells(rows, target_col_count=4)
    assert len(result[0]) == 4
    assert result[0][0] == "Name"
    assert result[0][3] == "Value"


def test_normalise_rowspan() -> None:
    rows = [["A", "B"], ["↓", "C"]]
    result = normalise_merged_cells(rows, target_col_count=2)
    assert result[1][0] == "A"


def test_infer_col_count() -> None:
    rows = [["A →→", "B"], ["C", "D", "E"]]
    assert infer_col_count(rows) == 3


def test_empty_rows() -> None:
    assert normalise_merged_cells([]) == []
