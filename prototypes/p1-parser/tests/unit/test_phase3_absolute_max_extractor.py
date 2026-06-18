"""Unit tests for absolute maximum ratings extraction."""

from tests.fixtures.phase2_mock_outputs import mock_sn74_phase2_output
from src.phase3_extract.absolute_max_extractor import extract_absolute_max_ratings


def test_extract_abs_max_from_mock() -> None:
    phase2_out = mock_sn74_phase2_output()
    abs_grid = [
        g for g in phase2_out.grids if g.section_type == "absolute_maximum_ratings"
    ][0]
    ratings = extract_absolute_max_ratings(abs_grid, "SN74")
    assert len(ratings) >= 3
    i_out = next(r for r in ratings if r.name == "I_O")
    assert i_out.max_value.value == 20.0
    assert i_out.unit == "mA"
