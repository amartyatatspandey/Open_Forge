"""Extended Phase 4 rule tests."""

import pytest

from src.phase4_validate.cross_parameter_rules import ELECTRICAL_RULES
from src.phase4_validate.ordering_rules import validate_min_typ_max_ordering
from src.phase4_validate.sanity_ranges import validate_sanity_ranges
from src.schemas.datasheet import ElectricalParameter, ExtractedValue


def _v(raw: str, val: float, unit: str = "V") -> ExtractedValue:
    return ExtractedValue(
        raw_text=raw,
        value=val,
        unit=unit,
        confidence=0.95,
        source="manual_review",
    )


@pytest.mark.parametrize("rule_name", [r["rule"] for r in ELECTRICAL_RULES])
def test_electrical_rules_defined(rule_name: str) -> None:
    assert rule_name


def test_i_cc_sanity_in_range() -> None:
    param = ElectricalParameter(
        name="I_CC",
        parameter_type="current",
        typ_value=_v("10", 10.0, "mA"),
    )
    assert validate_sanity_ranges([param]) == []


def test_i_cc_sanity_too_high() -> None:
    param = ElectricalParameter(
        name="I_CC",
        parameter_type="current",
        typ_value=_v("6000", 6000.0, "mA"),
    )
    errors = validate_sanity_ranges([param])
    assert len(errors) == 1


def test_t_a_in_range() -> None:
    param = ElectricalParameter(
        name="T_A",
        parameter_type="temperature",
        max_value=_v("85", 85.0, "°C"),
    )
    assert validate_sanity_ranges([param]) == []


def test_v_dd_matches_range() -> None:
    param = ElectricalParameter(
        name="V_DD",
        parameter_type="voltage",
        typ_value=_v("3.3", 3.3),
    )
    assert validate_sanity_ranges([param]) == []


def test_only_typ_no_ordering_error() -> None:
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        typ_value=_v("3.3", 3.3),
    )
    assert validate_min_typ_max_ordering([param]) == []


def test_multiple_params_one_bad() -> None:
    good = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        min_value=_v("1.8", 1.8),
        max_value=_v("5.5", 5.5),
    )
    bad = ElectricalParameter(
        name="V_OUT",
        parameter_type="voltage",
        min_value=_v("5.0", 5.0),
        max_value=_v("0.5", 0.5),
    )
    errors = validate_min_typ_max_ordering([good, bad])
    assert len(errors) == 1
    assert errors[0].param_name == "V_OUT"
