"""Additional Phase 3 extraction tests for golden mocks."""

import pytest

from tests.fixtures.phase2_mock_outputs import (
    mock_ina219_phase2_output,
    mock_lm5176_phase2_output,
    mock_sn74_phase2_output,
    mock_tps62933_phase2_output,
)
from src.phase3_extract.absolute_max_extractor import extract_absolute_max_ratings
from src.phase3_extract.parameter_extractor import extract_electrical_parameters
from src.phase3_extract.pinout_extractor import extract_pins
from src.phase3_extract.runner import run_phase3


@pytest.mark.parametrize(
    "factory,component_id,min_params,min_pins",
    [
        (mock_sn74_phase2_output, "SN74LVC1G04", 3, 4),
        (mock_ina219_phase2_output, "INA219", 5, 9),
        (mock_tps62933_phase2_output, "TPS62933", 5, 6),
    ],
)
def test_run_phase3_component_counts(factory, component_id, min_params, min_pins) -> None:
    datasheet = run_phase3(factory())
    assert datasheet.component_id == component_id
    assert len(datasheet.all_parameters) >= min_params
    assert len(datasheet.all_pins) >= min_pins


def test_sn74_v_cc_parameter() -> None:
    out = mock_sn74_phase2_output()
    grid = [g for g in out.grids if g.section_type == "electrical_characteristics"][0]
    params = extract_electrical_parameters(grid, "SN74")
    v_cc = next(p for p in params if p.name == "V_CC")
    assert v_cc.min_value.value == 1.65


def test_ina219_pinout_count() -> None:
    out = mock_ina219_phase2_output()
    grid = [g for g in out.grids if g.section_type == "pinout"][0]
    pins = extract_pins(grid, "INA219")
    assert len(pins) == 9


def test_lm5176_abs_max_count() -> None:
    out = mock_lm5176_phase2_output()
    grid = [g for g in out.grids if g.section_type == "absolute_maximum_ratings"][0]
    ratings = extract_absolute_max_ratings(grid, "LM5176")
    assert len(ratings) == 4


def test_tps62933_validation_passes() -> None:
    datasheet = run_phase3(mock_tps62933_phase2_output())
    assert datasheet.validation.passed is True


def test_sections_have_page_ranges() -> None:
    datasheet = run_phase3(mock_sn74_phase2_output())
    for section in datasheet.sections:
        assert section.page_range[0] > 0
        assert section.table_confidence > 0
