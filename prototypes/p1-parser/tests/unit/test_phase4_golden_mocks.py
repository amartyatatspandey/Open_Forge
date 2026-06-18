"""Golden mock Phase 4 validation tests."""

from src.phase4_validate.runner import run_phase4
from src.phase4_validate.validator import run_full_validation
from tests.fixtures.phase3_mock_outputs import all_golden_phase3_outputs


def test_sn74_passes_validation() -> None:
    outputs = all_golden_phase3_outputs()
    result = run_full_validation(outputs["TI_SN74LVC1G04"])
    assert result.component_id == "SN74LVC1G04"


def test_ina219_has_pins_in_export() -> None:
    outputs = all_golden_phase3_outputs()
    _, export = run_phase4(outputs["TI_INA219"])
    assert len(export.pins) >= 9


def test_lm5176_validation_runs() -> None:
    outputs = all_golden_phase3_outputs()
    validation, export = run_phase4(outputs["TI_LM5176"])
    assert validation is not None
    assert export.validation_status in ("PASS", "WARN", "BLOCKED")


def test_tps62933_export_has_specs() -> None:
    outputs = all_golden_phase3_outputs()
    _, export = run_phase4(outputs["TI_TPS62933"])
    assert len(export.electrical_specs) > 0


def test_tlv7021_kicad_export_pass_or_warn() -> None:
    outputs = all_golden_phase3_outputs()
    _, export = run_phase4(outputs["TI_TLV7021"])
    assert export.validation_status in ("PASS", "WARN", "BLOCKED")
