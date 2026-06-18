"""Unit tests for KiCad export."""

from src.phase4_validate.kicad_exporter import export_to_kicad, infer_net_name
from src.schemas.datasheet import PinDefinition, ValidationError, ValidationResult
from tests.fixtures.phase3_mock_outputs import mock_tlv7021_component_datasheet


def test_kicad_export_from_valid_datasheet() -> None:
    datasheet = mock_tlv7021_component_datasheet()
    validation = ValidationResult(
        component_id="TLV7021",
        passed=True,
        errors=[],
        warnings=[],
        review_required=False,
        confidence_score=0.95,
        timestamp="2026-06-12T00:00:00Z",
    )
    export = export_to_kicad(datasheet, validation)

    assert export.component_id == "TLV7021"
    assert len(export.pins) == 8
    assert export.validation_status == "PASS"
    assert "V_CC" in [p.pin_name for p in export.pins]


def test_kicad_export_status_warn() -> None:
    datasheet = mock_tlv7021_component_datasheet()
    validation = ValidationResult(
        component_id="TLV7021",
        passed=True,
        errors=[],
        warnings=[
            ValidationError(
                level="WARNING",
                param_name="I_CC",
                message="Low confidence",
            )
        ],
        review_required=True,
        confidence_score=0.80,
        timestamp="2026-06-12T00:00:00Z",
    )
    export = export_to_kicad(datasheet, validation)
    assert export.validation_status == "WARN"


def test_kicad_export_status_blocked() -> None:
    datasheet = mock_tlv7021_component_datasheet()
    validation = ValidationResult(
        component_id="TLV7021",
        passed=False,
        errors=[
            ValidationError(
                level="CRITICAL",
                param_name="V_CC",
                message="min > max",
            )
        ],
        warnings=[],
        review_required=True,
        confidence_score=0.50,
        timestamp="2026-06-12T00:00:00Z",
    )
    export = export_to_kicad(datasheet, validation)
    assert export.validation_status == "BLOCKED"


def test_infer_net_name_power() -> None:
    pin = PinDefinition(pin_number="1", pin_name="VCC", pin_type="power")
    assert infer_net_name(pin) == "V_CC"


def test_infer_net_name_ground() -> None:
    pin = PinDefinition(pin_number="2", pin_name="GND", pin_type="ground")
    assert infer_net_name(pin) == "GND"


def test_infer_net_name_3v3() -> None:
    pin = PinDefinition(pin_number="1", pin_name="V33", pin_type="power")
    assert infer_net_name(pin) == "V_3V3"


def test_electrical_specs_populated() -> None:
    datasheet = mock_tlv7021_component_datasheet()
    validation = ValidationResult(
        component_id="TLV7021",
        passed=True,
        errors=[],
        warnings=[],
        review_required=False,
        confidence_score=0.95,
        timestamp="2026-06-12T00:00:00Z",
    )
    export = export_to_kicad(datasheet, validation)
    assert len(export.electrical_specs) > 0
    assert "parameter_type" in next(iter(export.electrical_specs.values()))
