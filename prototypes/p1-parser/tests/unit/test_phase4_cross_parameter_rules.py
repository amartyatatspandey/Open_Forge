"""Unit tests for cross-parameter electrical rules."""

from src.phase4_validate.cross_parameter_rules import validate_cross_parameter_rules
from src.schemas.datasheet import ElectricalParameter, ExtractedValue


def _value(raw: str, val: float) -> ExtractedValue:
    return ExtractedValue(
        raw_text=raw,
        value=val,
        unit="V",
        confidence=0.95,
        source="manual_review",
    )


def test_valid_logic_levels() -> None:
    params = [
        ElectricalParameter(
            name="V_CC",
            parameter_type="voltage",
            typ_value=_value("3.3", 3.3),
        ),
        ElectricalParameter(
            name="V_IL",
            parameter_type="voltage",
            max_value=_value("0.8", 0.8),
        ),
    ]
    errors = validate_cross_parameter_rules(params)
    assert not any("V_CC > V_IL_max" in e.message for e in errors)


def test_invalid_logic_window() -> None:
    params = [
        ElectricalParameter(
            name="V_IL",
            parameter_type="voltage",
            max_value=_value("2.0", 2.0),
        ),
        ElectricalParameter(
            name="V_IH",
            parameter_type="voltage",
            min_value=_value("1.5", 1.5),
        ),
    ]
    errors = validate_cross_parameter_rules(params)
    rule_errors = [e for e in errors if "V_IL_max < V_IH_min" in e.message]
    assert len(rule_errors) == 1
    assert rule_errors[0].level == "CRITICAL"


def test_vol_vs_vil_warning() -> None:
    params = [
        ElectricalParameter(
            name="V_OL",
            parameter_type="voltage",
            max_value=_value("0.8", 0.8),
        ),
        ElectricalParameter(
            name="V_IL",
            parameter_type="voltage",
            max_value=_value("0.5", 0.5),
        ),
    ]
    errors = validate_cross_parameter_rules(params)
    assert any(e.level == "WARNING" for e in errors)


def test_missing_params_skipped() -> None:
    params = [
        ElectricalParameter(
            name="V_CC",
            parameter_type="voltage",
            typ_value=_value("3.3", 3.3),
        ),
    ]
    assert validate_cross_parameter_rules(params) == []
