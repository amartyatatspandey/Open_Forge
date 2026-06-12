"""Extended unit normalizer tests."""

import pytest

from src.phase3_extract.unit_normalizer import CANONICAL_UNITS, normalize_unit


@pytest.mark.parametrize(
    "raw_value,raw_unit,param_type,expected_val,expected_unit",
    [
        ("1.5", "kΩ", "resistance", 1500.0, "Ω"),
        ("100", "pF", "capacitance", 100.0, "pF"),
        ("500", "kHz", "frequency", 0.5, "MHz"),
        ("10", "ns", "time", 10.0, "ns"),
        ("25", "°C", "temperature", 25.0, "°C"),
        ("100", "mW", "power", 100.0, "mW"),
        ("1", "nF", "capacitance", 1000.0, "pF"),
        ("2", "µs", "time", 2000.0, "ns"),
        ("3", "GHz", "frequency", 3000.0, "MHz"),
        ("0.001", "A", "current", 1.0, "mA"),
    ],
)
def test_normalize_various_units(
    raw_value, raw_unit, param_type, expected_val, expected_unit
) -> None:
    val, unit = normalize_unit(raw_value, raw_unit, param_type)
    assert val == expected_val
    assert unit == expected_unit


def test_canonical_units_keys() -> None:
    assert "voltage" in CANONICAL_UNITS
    assert CANONICAL_UNITS["current"] == "mA"
