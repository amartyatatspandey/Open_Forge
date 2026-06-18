"""Unit tests for absolute maximum rating rules."""

from src.phase4_validate.absolute_max_rules import (
    validate_abs_max_sanity,
    validate_abs_max_vs_operating,
)
from src.schemas.datasheet import AbsoluteMaxRating, ElectricalParameter, ExtractedValue


def _value(raw: str, val: float, unit: str = "V") -> ExtractedValue:
    return ExtractedValue(
        raw_text=raw,
        value=val,
        unit=unit,
        confidence=0.95,
        source="manual_review",
    )


def test_abs_max_exceeds_operating() -> None:
    operating = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        max_value=_value("5.5", 5.5),
    )
    abs_max = AbsoluteMaxRating(
        name="V_CC_ABS",
        max_value=_value("6.0", 6.0),
        unit="V",
    )
    assert validate_abs_max_vs_operating([abs_max], [operating]) == []


def test_abs_max_below_operating_fails() -> None:
    operating = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        max_value=_value("5.5", 5.5),
    )
    abs_max = AbsoluteMaxRating(
        name="V_CC_ABS",
        max_value=_value("5.0", 5.0),
        unit="V",
    )
    errors = validate_abs_max_vs_operating([abs_max], [operating])
    assert len(errors) == 1
    assert errors[0].level == "CRITICAL"


def test_abs_max_sanity_in_range() -> None:
    rating = AbsoluteMaxRating(
        name="V_CC",
        max_value=_value("6.0", 6.0),
        unit="V",
    )
    assert validate_abs_max_sanity([rating]) == []


def test_abs_max_sanity_out_of_range() -> None:
    rating = AbsoluteMaxRating(
        name="V_CC",
        max_value=_value("500", 500.0),
        unit="V",
    )
    errors = validate_abs_max_sanity([rating])
    assert len(errors) == 1
    assert errors[0].level == "WARNING"
