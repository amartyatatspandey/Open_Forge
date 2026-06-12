"""Unit tests for min/typ/max ordering rules."""

from src.phase4_validate.ordering_rules import validate_min_typ_max_ordering
from src.schemas.datasheet import ElectricalParameter, ExtractedValue


def _value(raw: str, val: float, unit: str = "V") -> ExtractedValue:
    return ExtractedValue(
        raw_text=raw,
        value=val,
        unit=unit,
        confidence=0.95,
        source="manual_review",
    )


def test_valid_ordering() -> None:
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        min_value=_value("1.8", 1.8),
        typ_value=_value("3.3", 3.3),
        max_value=_value("5.5", 5.5),
    )
    assert validate_min_typ_max_ordering([param]) == []


def test_inverted_min_max() -> None:
    param = ElectricalParameter(
        name="V_OUT",
        parameter_type="voltage",
        min_value=_value("5.0", 5.0),
        max_value=_value("0.5", 0.5),
    )
    errors = validate_min_typ_max_ordering([param])
    assert len(errors) == 1
    assert errors[0].level == "CRITICAL"


def test_typ_greater_than_max() -> None:
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        typ_value=_value("6.0", 6.0),
        max_value=_value("5.5", 5.5),
    )
    errors = validate_min_typ_max_ordering([param])
    assert len(errors) == 1
    assert "typ" in errors[0].message


def test_min_greater_than_typ() -> None:
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        min_value=_value("4.0", 4.0),
        typ_value=_value("3.3", 3.3),
    )
    errors = validate_min_typ_max_ordering([param])
    assert len(errors) == 1
    assert errors[0].param_name == "V_CC"
