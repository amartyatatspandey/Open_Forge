"""Unit tests for Phase 3 unit normalizer."""

import pytest

from src.phase3_extract.unit_normalizer import normalize_unit


def test_voltage_mv_to_v() -> None:
    val, unit = normalize_unit("3300", "mV", "voltage")
    assert val == 3.3
    assert unit == "V"


def test_current_a_to_ma() -> None:
    val, unit = normalize_unit("0.5", "A", "current")
    assert val == 500.0
    assert unit == "mA"


def test_ocr_error_u_to_micro() -> None:
    val, unit = normalize_unit("100", "uA", "current")
    assert val == 0.1
    assert unit == "mA"


def test_unknown_unit_raises() -> None:
    with pytest.raises(ValueError, match="Unknown unit"):
        normalize_unit("3.3", "XYZ", "voltage")


def test_case_insensitive() -> None:
    val1, _ = normalize_unit("1000", "mV", "voltage")
    val2, _ = normalize_unit("1000", "MV", "voltage")
    assert val1 == val2


def test_whitespace_handling() -> None:
    val1, _ = normalize_unit("1000", "mV", "voltage")
    val2, _ = normalize_unit("1000", " m V ", "voltage")
    assert val1 == val2


def test_empty_value_raises() -> None:
    with pytest.raises(ValueError):
        normalize_unit("", "V", "voltage")
