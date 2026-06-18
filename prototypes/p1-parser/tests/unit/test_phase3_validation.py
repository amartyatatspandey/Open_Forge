"""Unit tests for Phase 3 validation."""

from src.phase3_extract.validation import validate_extracted_data
from src.schemas.datasheet import ElectricalParameter, ExtractedValue, PinDefinition


def test_validate_passes_clean_data() -> None:
    params = [
        ElectricalParameter(
            name="V_CC",
            parameter_type="voltage",
            max_value=ExtractedValue(
                raw_text="5.5",
                value=5.5,
                unit="V",
                confidence=0.95,
                source="vector_path_A",
            ),
        )
    ]
    pins = [
        PinDefinition(pin_number="1", pin_name="V_CC", pin_type="power"),
    ]
    result = validate_extracted_data("TEST", params, pins, [])
    assert result.passed is True


def test_validate_duplicate_parameters() -> None:
    params = [
        ElectricalParameter(name="V_CC", parameter_type="voltage"),
        ElectricalParameter(name="V_CC", parameter_type="voltage"),
    ]
    result = validate_extracted_data("TEST", params, [], [])
    assert result.passed is False
    assert any("Duplicate" in err.message for err in result.errors)
