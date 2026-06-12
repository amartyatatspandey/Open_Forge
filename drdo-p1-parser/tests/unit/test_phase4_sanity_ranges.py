"""Unit tests for sanity range validation."""

from src.phase4_validate.sanity_ranges import validate_sanity_ranges
from src.schemas.datasheet import ElectricalParameter, ExtractedValue


def _value(raw: str, val: float, unit: str = "V") -> ExtractedValue:
    return ExtractedValue(
        raw_text=raw,
        value=val,
        unit=unit,
        confidence=0.95,
        source="manual_review",
    )


def test_voltage_in_range() -> None:
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        typ_value=_value("3.3", 3.3),
    )
    assert validate_sanity_ranges([param]) == []


def test_voltage_too_low_warns() -> None:
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        typ_value=ExtractedValue(
            raw_text="0.001",
            value=0.001,
            unit="V",
            confidence=0.70,
            source="manual_review",
        ),
    )
    errors = validate_sanity_ranges([param])
    assert len(errors) == 1
    assert errors[0].level == "WARNING"


def test_temperature_out_of_range() -> None:
    param = ElectricalParameter(
        name="T_J",
        parameter_type="temperature",
        max_value=ExtractedValue(
            raw_text="200",
            value=200.0,
            unit="°C",
            confidence=0.85,
            source="manual_review",
        ),
    )
    errors = validate_sanity_ranges([param])
    assert len(errors) == 1
    assert errors[0].param_name == "T_J"


def test_unknown_param_skipped() -> None:
    param = ElectricalParameter(
        name="CUSTOM_PARAM",
        parameter_type="other",
        typ_value=_value("999", 999.0),
    )
    assert validate_sanity_ranges([param]) == []
