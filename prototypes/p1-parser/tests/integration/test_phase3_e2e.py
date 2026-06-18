"""Integration tests for Phase 3 extraction pipeline."""

from tests.fixtures.phase2_mock_outputs import (
    all_golden_phase2_outputs,
    mock_tlv7021_phase2_output,
)
from src.phase3_extract.runner import run_phase3


def test_run_phase3_with_mock() -> None:
    phase2_out = mock_tlv7021_phase2_output()
    datasheet = run_phase3(phase2_out)

    assert datasheet.component_id == "TLV7021"
    assert len(datasheet.all_pins) > 0
    assert datasheet.validation is not None
    assert datasheet.validation.passed is True


def test_run_phase3_all_golden() -> None:
    all_phase2 = all_golden_phase2_outputs()

    for _key, phase2_out in all_phase2.items():
        datasheet = run_phase3(phase2_out)
        expected_id = phase2_out.metadata["component_id"]
        assert datasheet.component_id == expected_id
        assert datasheet.validation is not None
        assert len(datasheet.sections) == 3
