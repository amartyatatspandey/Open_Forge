"""NIR component_type → tscircuit element type and pin label mapping."""

from __future__ import annotations

TSCIRCUIT_ELEMENT_MAP: dict[str, str] = {
    # Passives
    "resistor": "resistor",
    "capacitor": "capacitor",
    "inductor": "inductor",
    "crystal": "crystal",
    "ferrite_bead": "inductor",
    "fuse": "fuse",
    "potentiometer": "resistor",
    # Semiconductors
    "diode": "diode",
    "led": "led",
    "zener_diode": "diode",
    "schottky_diode": "diode",
    "transistor": "transistor",
    "mosfet": "transistor",
    "bjt": "transistor",
    # ICs
    "op_amp": "chip",
    "ldo_regulator": "chip",
    "voltage_regulator": "chip",
    "buck_converter": "chip",
    "boost_converter": "chip",
    "switching_regulator": "chip",
    "microcontroller": "chip",
    "voltage_reference": "chip",
    "gate_driver": "chip",
    "comparator": "chip",
    "voltage_comparator": "chip",
    "adc_converter": "chip",
    "dac_converter": "chip",
    "usb_uart_bridge": "chip",
    "rf_ic": "chip",
    "current_source": "chip",
    # Connectors and RF
    "connector": "connector",
    "sma_connector": "connector",
    "usb_connector": "connector",
    "micro_connector": "connector",
    "antenna": "chip",
    # Power
    "power_source": "power_source",
    "battery": "power_source",
}

# Pin label maps for typed elements where tscircuit
# uses semantic pin names instead of pin numbers
TSCIRCUIT_PIN_LABELS: dict[str, dict[str, str]] = {
    # element_type → {pin_number → tscircuit_pin_label}
    "resistor": {"1": "pin1", "2": "pin2"},
    "capacitor": {"1": "pos", "2": "neg"},
    "inductor": {"1": "pin1", "2": "pin2"},
    "diode": {"1": "A", "2": "K"},
    "led": {"1": "A", "2": "K"},
    "transistor": {"1": "B", "2": "C", "3": "E"},
    "fuse": {"1": "pin1", "2": "pin2"},
    "crystal": {"1": "pin1", "2": "pin2"},
}


def get_element_type(component_type: str) -> tuple[str, bool]:
    """
    Returns (tscircuit_element_type, needs_review).
    needs_review=True when component_type not in map (falls back to chip).
    """
    if component_type in TSCIRCUIT_ELEMENT_MAP:
        return TSCIRCUIT_ELEMENT_MAP[component_type], False
    return "chip", True


def get_pin_label(
    element_type: str,
    pin_number: str,
) -> str:
    """
    Returns the tscircuit pin label for a given element type and pin number.
    Falls back to 'pin{number}' for unmapped types.
    """
    labels = TSCIRCUIT_PIN_LABELS.get(element_type, {})
    return labels.get(pin_number, f"pin{pin_number}")
