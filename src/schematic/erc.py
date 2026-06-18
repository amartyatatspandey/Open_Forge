"""Electrical rules checker for schematic netlists."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from src.schemas.datasheet import ComponentDatasheet
from src.schemas.nir import NetlistEntry, PinRef

from src.schematic._schemas import ERCResult, ERCViolation

logger = logging.getLogger(__name__)

ERC_RULES = [
    "no_output_conflict",
    "power_net_has_source",
    "no_required_pin_floating",
    "no_logic_level_mismatch",
    "no_floating_inputs",
]

_OUTPUT_TYPES = frozenset({"output", "io"})
_INPUT_TYPES = frozenset({"input", "io"})
_POWER_FUNCTIONS = frozenset({"POWER_POSITIVE", "POWER_GROUND", "POWER_INPUT"})
_REQUIRED_FUNCTIONS = frozenset({"POWER_POSITIVE", "POWER_GROUND", "ENABLE", "RESET"})


def _pin_lookup(
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
) -> dict[tuple[str, str], tuple[str, str | None]]:
    """Map (ref, pin_number) → (pin_type, normalized_function)."""
    lookup: dict[tuple[str, str], tuple[str, str | None]] = {}
    for _component_id, (ref, datasheet) in ref_map.items():
        if datasheet is None:
            continue
        for pin in datasheet.pins:
            lookup[(ref, pin.pin_number)] = (pin.pin_type or "", pin.normalized_function)
    return lookup


def _connected_pins(netlist: list[NetlistEntry]) -> set[tuple[str, str]]:
    connected: set[tuple[str, str]] = set()
    for net in netlist:
        for conn in net.connections:
            connected.add((conn.ref, conn.pin_number))
    return connected


def check_erc(
    netlist: list[NetlistEntry],
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
) -> ERCResult:
    """Run all ERC rules. Never raises."""
    violations: list[ERCViolation] = []
    pin_lookup = _pin_lookup(ref_map)
    connected = _connected_pins(netlist)

    try:
        for net in netlist:
            outputs_on_net: list[str] = []
            for conn in net.connections:
                pin_type, _func = pin_lookup.get((conn.ref, conn.pin_number), ("", None))
                if pin_type in _OUTPUT_TYPES:
                    outputs_on_net.append(conn.ref)

            if len(outputs_on_net) > 1:
                violations.append(
                    ERCViolation(
                        severity="CRITICAL",
                        rule_name="no_output_conflict",
                        affected_refs=sorted(set(outputs_on_net)),
                        message=f"Multiple output pins on net {net.net_name}",
                    )
                )

        for net in netlist:
            if not net.net_name.startswith("VCC"):
                continue
            has_source = False
            for conn in net.connections:
                _pin_type, func = pin_lookup.get((conn.ref, conn.pin_number), ("", None))
                if func == "POWER_POSITIVE" or "regulator" in conn.ref.lower():
                    has_source = True
                    break
            if not has_source and net.connections:
                violations.append(
                    ERCViolation(
                        severity="CRITICAL",
                        rule_name="power_net_has_source",
                        affected_refs=[c.ref for c in net.connections],
                        message=f"Power net {net.net_name} has no identified source",
                    )
                )

        for _component_id, (ref, datasheet) in ref_map.items():
            if datasheet is None:
                continue
            for pin in datasheet.pins:
                func = pin.normalized_function
                if func not in _REQUIRED_FUNCTIONS:
                    continue
                if (ref, pin.pin_number) not in connected:
                    violations.append(
                        ERCViolation(
                            severity="CRITICAL",
                            rule_name="no_required_pin_floating",
                            affected_refs=[ref],
                            message=f"Required pin {pin.raw_name} on {ref} is floating",
                        )
                    )

        for net in netlist:
            if "3V3" in net.net_name.upper() and "5V" in net.net_name.upper():
                violations.append(
                    ERCViolation(
                        severity="WARNING",
                        rule_name="no_logic_level_mismatch",
                        affected_refs=[c.ref for c in net.connections],
                        message=f"Potential logic level mismatch on {net.net_name}",
                    )
                )

        drivers_by_net: dict[str, set[str]] = defaultdict(set)
        for net in netlist:
            for conn in net.connections:
                pin_type, _func = pin_lookup.get((conn.ref, conn.pin_number), ("", None))
                if pin_type in _OUTPUT_TYPES:
                    drivers_by_net[net.net_name].add(conn.ref)

        for net in netlist:
            if net.net_type == "power":
                continue
            floating_inputs: list[str] = []
            for conn in net.connections:
                pin_type, func = pin_lookup.get((conn.ref, conn.pin_number), ("", None))
                if func in _POWER_FUNCTIONS:
                    continue
                if pin_type in _INPUT_TYPES and conn.ref not in drivers_by_net.get(net.net_name, set()):
                    if len(drivers_by_net.get(net.net_name, set())) == 0:
                        floating_inputs.append(conn.ref)
            if floating_inputs:
                violations.append(
                    ERCViolation(
                        severity="WARNING",
                        rule_name="no_floating_inputs",
                        affected_refs=sorted(set(floating_inputs)),
                        message=f"Input pins may be floating on net {net.net_name}",
                    )
                )

    except Exception as exc:
        logger.error("ERC check failed: %s", exc)
        violations.append(
            ERCViolation(
                severity="CRITICAL",
                rule_name="erc_internal_error",
                affected_refs=[],
                message=str(exc),
            )
        )

    return ERCResult(
        passed=not any(v.severity == "CRITICAL" for v in violations),
        violations=violations,
        rules_checked=len(ERC_RULES),
    )
