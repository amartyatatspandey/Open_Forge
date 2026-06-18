"""Passive component net assignment."""

from __future__ import annotations

import re
from typing import Optional

from src.schemas.datasheet import ComponentDatasheet, PinDefinition
from src.schemas.intent import ValidatedBOM
from src.schemas.nir import NetlistEntry, PinRef

from src.schematic.net_assigner import _build_net, _pin_ref


def _find_net(names: list[str], nets: list[NetlistEntry]) -> NetlistEntry | None:
    for name in names:
        for net in nets:
            if net.net_name == name:
                return net
    return None


def _first_pin(datasheet: ComponentDatasheet, index: int = 0) -> PinDefinition | None:
    if not datasheet.pins:
        return None
    if index < len(datasheet.pins):
        return datasheet.pins[index]
    return datasheet.pins[0]


def assign_passives(
    bom: ValidatedBOM,
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
    existing_nets: list[NetlistEntry],
    unresolved_pins: list[PinRef] | None = None,
) -> list[NetlistEntry]:
    """Connect passive components to power and signal nets."""
    nets: list[NetlistEntry] = []
    vcc_net = _find_net(["VCC", "VCC_3V3", "VCC_3p3V", "VCC_5V"], existing_nets)
    gnd_net = _find_net(["GND"], existing_nets)
    sw_net = _find_net(["SW"], existing_nets)

    for entry in bom.components:
        comp_type = entry.component_type.lower()
        datasheet = None
        for _cid, (ref, ds) in ref_map.items():
            if ref == entry.ref:
                datasheet = ds
                break

        if "capacitor" in comp_type and ("decoupling" in comp_type or "bypass" in comp_type):
            if datasheet is None or vcc_net is None or gnd_net is None:
                if unresolved_pins is not None and datasheet is not None:
                    for pin in datasheet.pins:
                        unresolved_pins.append(_pin_ref(entry.ref, pin))
                continue

            pos_pin = _first_pin(datasheet, 0)
            neg_pin = _first_pin(datasheet, 1) or pos_pin
            if pos_pin is None or neg_pin is None:
                continue

            associated = re.search(r"\b([CRU]\d+)\b", entry.justification)
            net_name = (
                f"VCC_{associated.group(1)}_BYPASS"
                if associated
                else (vcc_net.net_name if vcc_net else "VCC")
            )
            nets.append(
                _build_net(
                    net_name,
                    "power",
                    [_pin_ref(entry.ref, pos_pin)],
                    [pos_pin],
                    "passive_assignment",
                )
            )
            nets.append(
                _build_net(
                    f"{net_name}_GND",
                    "power",
                    [_pin_ref(entry.ref, neg_pin)],
                    [neg_pin],
                    "passive_assignment",
                )
            )
            continue

        if "inductor" in comp_type and "power" in comp_type:
            if datasheet is None:
                if unresolved_pins is not None:
                    unresolved_pins.append(
                        PinRef(ref=entry.ref, pin_name="UNKNOWN", pin_number="?")
                    )
                continue

            pin1 = _first_pin(datasheet, 0)
            pin2 = _first_pin(datasheet, 1)
            if pin1 is None or pin2 is None:
                if unresolved_pins is not None:
                    for pin in datasheet.pins:
                        unresolved_pins.append(_pin_ref(entry.ref, pin))
                continue

            input_net = sw_net.net_name if sw_net else (vcc_net.net_name if vcc_net else "VCC")
            output_net = vcc_net.net_name if vcc_net else "VCC"
            nets.append(
                _build_net(
                    f"{entry.ref}_L_IN",
                    "power",
                    [_pin_ref(entry.ref, pin1)],
                    [pin1],
                    "passive_assignment",
                )
            )
            nets.append(
                _build_net(
                    f"{entry.ref}_L_OUT",
                    "power",
                    [_pin_ref(entry.ref, pin2)],
                    [pin2],
                    "passive_assignment",
                )
            )
            _ = input_net
            _ = output_net
            continue

        if "resistor" in comp_type and "pull" in comp_type:
            if datasheet is None or vcc_net is None:
                if unresolved_pins is not None and datasheet is not None:
                    for pin in datasheet.pins:
                        unresolved_pins.append(_pin_ref(entry.ref, pin))
                continue

            pin1 = _first_pin(datasheet, 0)
            pin2 = _first_pin(datasheet, 1)
            if pin1 is None or pin2 is None:
                continue

            signal_match = re.search(
                r"(SPI_[A-Z_]+|I2C_[A-Z_]+|UART_[A-Z_]+|EN|NRST|INT)",
                entry.justification.upper(),
            )
            signal_net = signal_match.group(1) if signal_match else None
            if signal_net is None:
                if unresolved_pins is not None:
                    for pin in datasheet.pins:
                        unresolved_pins.append(_pin_ref(entry.ref, pin))
                continue

            nets.append(
                _build_net(
                    f"{entry.ref}_PULLUP_VCC",
                    "power",
                    [_pin_ref(entry.ref, pin1)],
                    [pin1],
                    "passive_assignment",
                )
            )
            nets.append(
                _build_net(
                    f"{entry.ref}_PULLUP_SIG",
                    "signal",
                    [_pin_ref(entry.ref, pin2)],
                    [pin2],
                    "passive_assignment",
                )
            )
            continue

        if any(kw in comp_type for kw in ("capacitor", "resistor", "inductor")):
            if unresolved_pins is not None and datasheet is not None:
                for pin in datasheet.pins:
                    unresolved_pins.append(_pin_ref(entry.ref, pin))

    return nets
