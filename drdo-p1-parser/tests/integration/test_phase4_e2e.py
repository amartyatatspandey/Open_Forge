"""Integration tests for Phase 4 end-to-end pipeline."""

from src.phase4_validate.runner import run_phase4
from tests.fixtures.phase3_mock_outputs import (
    all_golden_phase3_outputs,
    mock_tlv7021_component_datasheet,
)


def test_run_phase4_end_to_end() -> None:
    phase3_out = mock_tlv7021_component_datasheet()
    validation, export = run_phase4(phase3_out)

    assert validation.component_id == "TLV7021"
    assert export.component_id == "TLV7021"
    assert export.validation_status in ("PASS", "WARN", "BLOCKED")


def test_run_phase4_all_golden() -> None:
    all_phase3 = all_golden_phase3_outputs()
    for component_id, datasheet in all_phase3.items():
        validation, export = run_phase4(datasheet)
        assert validation is not None
        assert export is not None
        assert validation.component_id == datasheet.component_id
        assert export.validation_status in ("PASS", "WARN", "BLOCKED")
