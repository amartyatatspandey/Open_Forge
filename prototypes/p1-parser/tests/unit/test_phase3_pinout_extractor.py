"""Unit tests for pinout extraction."""

from tests.fixtures.phase2_mock_outputs import mock_tlv7021_phase2_output
from src.phase3_extract.pinout_extractor import (
    extract_alternate_functions,
    extract_pins,
    infer_pin_type,
)


def test_extract_pins_from_mock() -> None:
    phase2_out = mock_tlv7021_phase2_output()
    pinout_grid = [g for g in phase2_out.grids if g.section_type == "pinout"][0]
    pins = extract_pins(pinout_grid, "TLV7021")
    assert len(pins) == 8
    assert pins[0].pin_number == "1"
    assert pins[0].pin_name == "IN+"


def test_infer_pin_type() -> None:
    assert infer_pin_type("V_CC", "Power") == "power"
    assert infer_pin_type("GND", "Ground") == "ground"
    assert infer_pin_type("GPIO0", "I/O") == "digital_io"
    assert infer_pin_type("DATA_OUT", "Output") == "digital_output"


def test_alternate_functions() -> None:
    funcs = extract_alternate_functions("GPIO0/UART_TX/SPI_MOSI")
    assert funcs == ["GPIO0", "UART_TX", "SPI_MOSI"]
