"""Unit tests for Phase 3 table utilities."""

from src.phase3_extract.table_utils import (
    grid_source_to_extracted_source,
    identify_header_row,
    infer_unit_from_param_type,
    is_empty_cell,
    is_header_row,
    map_abs_max_columns,
    map_columns,
    map_pin_columns,
    parse_numeric,
)


def test_is_empty_cell() -> None:
    assert is_empty_cell("—") is True
    assert is_empty_cell("3.3") is False


def test_is_header_row_electrical() -> None:
    assert is_header_row(["Parameter", "Min", "Typ", "Max", "Unit"]) is True
    assert is_header_row(["V_CC", "1.8", "3.3", "5.5", "V"]) is False


def test_identify_header_row() -> None:
    rows = [["V_CC", "1.8"], ["Parameter", "Min", "Max", "Unit"], ["I_CC", "0.8"]]
    assert identify_header_row(rows) == 1


def test_map_columns() -> None:
    col_map = map_columns(["Parameter", "Min", "Typ", "Max", "Unit", "Conditions"])
    assert col_map["parameter"] == 0
    assert col_map["min"] == 1
    assert col_map["typ"] == 2
    assert col_map["max"] == 3
    assert col_map["unit"] == 4


def test_map_pin_columns() -> None:
    col_map = map_pin_columns(["Pin", "Name", "Type", "Description"])
    assert col_map["pin_number"] == 0
    assert col_map["pin_name"] == 1


def test_map_abs_max_columns() -> None:
    col_map = map_abs_max_columns(["Parameter", "Max", "Unit"])
    assert col_map["parameter"] == 0
    assert col_map["max"] == 1


def test_parse_numeric_with_plus_minus() -> None:
    assert parse_numeric("±20") == 20.0
    assert parse_numeric("1,234.5") == 1234.5
    assert parse_numeric("—") is None


def test_infer_unit_from_param_type() -> None:
    assert infer_unit_from_param_type("voltage") == "V"
    assert infer_unit_from_param_type("current") == "mA"


def test_grid_source_mapping() -> None:
    assert grid_source_to_extracted_source("vector_path_A") == "vector_path_A"
    assert grid_source_to_extracted_source("mock_for_testing") == "manual_review"
