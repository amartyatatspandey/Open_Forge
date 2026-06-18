"""Power and protocol net assignment."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional, TypedDict

import yaml

from src.config import Config, get_config
from src.schemas.datasheet import ComponentDatasheet, PinDefinition
from src.schemas.nir import NetlistEntry, PinRef

logger = logging.getLogger(__name__)

SKIP_FUNCTIONS = frozenset({
    None,
    "NO_CONNECT",
    "POWER_POSITIVE",
    "POWER_GROUND",
    "POWER_INPUT",
})

class _ProtocolGroup(TypedDict, total=False):
    shared: list[str]
    unique: list[str]
    crossover: list[tuple[str, str]]


def load_protocol_groups(config: Config) -> dict[str, _ProtocolGroup]:
    """Load protocol net-assignment groupings from canonical functions YAML."""
    path = Path(config.canonical_functions_path)
    if not path.exists():
        raise FileNotFoundError(f"Canonical functions file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    protocols = data.get("protocols", {})
    if not isinstance(protocols, dict):
        raise ValueError("canonical_functions.yaml 'protocols' must be a mapping")

    result: dict[str, _ProtocolGroup] = {}
    for name, group in protocols.items():
        if not isinstance(group, dict):
            continue
        parsed: _ProtocolGroup = {}
        if "shared" in group:
            parsed["shared"] = list(group["shared"])
        if "unique" in group:
            parsed["unique"] = list(group["unique"])
        if "crossover" in group:
            parsed["crossover"] = [tuple(pair) for pair in group["crossover"]]
        result[str(name)] = parsed
    return result


PROTOCOL_GROUPS: dict[str, _ProtocolGroup] = load_protocol_groups(get_config())

NET_NAME_MAP: dict[str, str] = {
    "SPI_CLOCK": "SPI_SCK",
    "SPI_DATA_IN": "SPI_MOSI",
    "SPI_DATA_OUT": "SPI_MISO",
    "SPI_CHIP_SELECT": "SPI_CS",
    "I2C_DATA": "I2C_SDA",
    "I2C_CLOCK": "I2C_SCL",
    "UART_TRANSMIT": "UART_TX",
    "UART_RECEIVE": "UART_RX",
    "ENABLE": "EN",
    "RESET": "NRST",
    "INTERRUPT": "INT",
    "PWM_OUTPUT": "PWM",
    "FEEDBACK": "FB",
    "SWITCH_NODE": "SW",
    "ANALOG_OUTPUT": "ANALOG_OUT",
    "RF_OUTPUT": "RF_OUT",
}

_REGULATOR_KEYWORDS = ("regulator", "ldo", "buck", "boost", "converter")


def _pin_ref(ref: str, pin: PinDefinition) -> PinRef:
    pin_name = pin.normalized_function or pin.raw_name
    return PinRef(ref=ref, pin_name=pin_name, pin_number=pin.pin_number)


def _mean_confidence(pins: list[PinDefinition]) -> float:
    confidences = [p.normalization_confidence for p in pins if p.normalization_confidence is not None]
    if not confidences:
        return 0.5
    return sum(confidences) / len(confidences)


def _derive_vcc_net_name(datasheet: ComponentDatasheet) -> str:
    text = f"{datasheet.description} {datasheet.component_id}".lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*v", text)
    if match:
        voltage = match.group(1).replace(".", "p")
        return f"VCC_{voltage}V"
    return "VCC"


def _is_regulator(datasheet: ComponentDatasheet) -> bool:
    text = f"{datasheet.description} {datasheet.component_id}".lower()
    return any(keyword in text for keyword in _REGULATOR_KEYWORDS)


def _iter_pins(
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
    unresolved_pins: list[PinRef] | None,
) -> list[tuple[str, ComponentDatasheet, PinDefinition]]:
    pins: list[tuple[str, ComponentDatasheet, PinDefinition]] = []
    for _component_id, (ref, datasheet) in ref_map.items():
        if datasheet is None:
            logger.warning("Skipping component %s — no datasheet available", ref)
            if unresolved_pins is not None:
                unresolved_pins.append(PinRef(ref=ref, pin_name="UNKNOWN", pin_number="?"))
            continue
        for pin in datasheet.pins:
            pins.append((ref, datasheet, pin))
    return pins


def _build_net(
    net_name: str,
    net_type: str,
    connections: list[PinRef],
    pins: list[PinDefinition],
    source_rule: str,
) -> NetlistEntry:
    return NetlistEntry(
        net_name=net_name,
        net_type=net_type,  # type: ignore[arg-type]
        connections=connections,
        source_rule=source_rule,
        net_confidence=_mean_confidence(pins),
    )


def assign_power_nets(
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
    unresolved_pins: list[PinRef] | None = None,
) -> list[NetlistEntry]:
    """Create power and ground nets from normalized pin functions."""
    pin_data = _iter_pins(ref_map, unresolved_pins)

    regulators = [
        (ref, ds)
        for _cid, (ref, ds) in ref_map.items()
        if ds is not None and _is_regulator(ds)
    ]
    use_per_regulator_vcc = len(regulators) > 1

    vcc_groups: dict[str, list[tuple[str, PinDefinition]]] = defaultdict(list)
    gnd_pins: list[tuple[str, PinDefinition]] = []
    vin_pins: list[tuple[str, PinDefinition]] = []

    for ref, datasheet, pin in pin_data:
        func = pin.normalized_function
        if func == "POWER_POSITIVE":
            if use_per_regulator_vcc and _is_regulator(datasheet):
                net_name = _derive_vcc_net_name(datasheet)
            else:
                net_name = "VCC"
            vcc_groups[net_name].append((ref, pin))
        elif func == "POWER_GROUND":
            gnd_pins.append((ref, pin))
        elif func == "POWER_INPUT":
            vin_pins.append((ref, pin))

    nets: list[NetlistEntry] = []

    for net_name, grouped in vcc_groups.items():
        pins_only = [pin for _, pin in grouped]
        connections = [_pin_ref(ref, pin) for ref, pin in grouped]
        nets.append(
            _build_net(net_name, "power", connections, pins_only, "power_net_assignment")
        )

    if gnd_pins:
        pins_only = [pin for _, pin in gnd_pins]
        connections = [_pin_ref(ref, pin) for ref, pin in gnd_pins]
        nets.append(_build_net("GND", "power", connections, pins_only, "power_net_assignment"))

    if vin_pins:
        pins_only = [pin for _, pin in vin_pins]
        connections = [_pin_ref(ref, pin) for ref, pin in vin_pins]
        nets.append(_build_net("VIN", "power", connections, pins_only, "power_net_assignment"))

    return nets


def _net_type_for_function(func: str, base_name: str) -> str:
    if func in ("SPI_CLOCK", "I2C_CLOCK"):
        return "clock"
    if func.startswith("RF_") or base_name.startswith("RF"):
        return "RF"
    if func.startswith(("SPI_", "I2C_", "UART_")):
        return "signal"
    return "signal"


def assign_protocol_nets(
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
    existing_nets: list[NetlistEntry],
    unresolved_pins: list[PinRef] | None = None,
) -> list[NetlistEntry]:
    """Match pins by normalized_function to form signal nets."""
    _ = existing_nets
    pin_data = _iter_pins(ref_map, unresolved_pins)

    function_pins: dict[str, list[tuple[str, PinDefinition]]] = defaultdict(list)
    for ref, _datasheet, pin in pin_data:
        func = pin.normalized_function
        if func in SKIP_FUNCTIONS or func is None:
            continue
        function_pins[func].append((ref, pin))

    nets: list[NetlistEntry] = []
    assigned: set[tuple[str, str]] = set()

    shared_functions: set[str] = set()
    unique_functions: set[str] = set()
    for group in PROTOCOL_GROUPS.values():
        shared_functions.update(group.get("shared", []))
        unique_functions.update(group.get("unique", []))

    for func in shared_functions:
        matches = function_pins.get(func, [])
        if not matches:
            continue
        base_name = NET_NAME_MAP.get(func, func)
        net_type = _net_type_for_function(func, base_name)
        pins_only = [pin for _, pin in matches]
        connections = [_pin_ref(ref, pin) for ref, pin in matches]
        nets.append(
            _build_net(base_name, net_type, connections, pins_only, "protocol_net_assignment")
        )
        for ref, pin in matches:
            assigned.add((ref, pin.pin_number))

    for func in unique_functions:
        for ref, pin in function_pins.get(func, []):
            base_name = NET_NAME_MAP.get(func, func)
            net_name = f"{base_name}_{ref}"
            net_type = _net_type_for_function(func, base_name)
            nets.append(
                _build_net(
                    net_name,
                    net_type,
                    [_pin_ref(ref, pin)],
                    [pin],
                    "protocol_net_assignment",
                )
            )
            assigned.add((ref, pin.pin_number))

    uart_group = PROTOCOL_GROUPS["UART"]
    tx_pins = function_pins.get("UART_TRANSMIT", [])
    rx_pins = function_pins.get("UART_RECEIVE", [])
    if tx_pins and rx_pins:
        for tx_ref, tx_pin in tx_pins:
            for rx_ref, rx_pin in rx_pins:
                if tx_ref == rx_ref:
                    continue
                net_name = f"UART_{tx_ref}_{rx_ref}"
                pins_only = [tx_pin, rx_pin]
                connections = [_pin_ref(tx_ref, tx_pin), _pin_ref(rx_ref, rx_pin)]
                nets.append(
                    _build_net(
                        net_name,
                        "signal",
                        connections,
                        pins_only,
                        "protocol_net_assignment",
                    )
                )
                assigned.add((tx_ref, tx_pin.pin_number))
                assigned.add((rx_ref, rx_pin.pin_number))

    for func, matches in function_pins.items():
        if func in shared_functions or func in unique_functions:
            continue
        if func in ("UART_TRANSMIT", "UART_RECEIVE"):
            continue
        base_name = NET_NAME_MAP.get(func, func)
        net_type = _net_type_for_function(func, base_name)
        unassigned = [(ref, pin) for ref, pin in matches if (ref, pin.pin_number) not in assigned]
        if not unassigned:
            continue
        pins_only = [pin for _, pin in unassigned]
        connections = [_pin_ref(ref, pin) for ref, pin in unassigned]
        nets.append(
            _build_net(base_name, net_type, connections, pins_only, "protocol_net_assignment")
        )

    return nets
