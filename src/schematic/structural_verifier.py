"""Structural verifier for schematic netlists (Layers 1-3).

Produces a continuous score in [0.0, 1.0] for the unified search controller.
Separate from src/schematic/erc.py — does not replace existing ERC.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.schemas.datasheet import ComponentDatasheet, PinRole
from src.schemas.intent import ValidatedBOM
from src.schemas.nir import NetlistEntry, PinRef
from src.schematic.erc import check_erc

logger = logging.getLogger(__name__)


class VerifierLayer(str, Enum):
    ELECTRICAL_INVARIANTS = "electrical_invariants"   # Layer 1
    PIN_ROLE_COMPATIBILITY = "pin_role_compatibility"  # Layer 2
    SUBCATEGORY_TEMPLATES = "subcategory_templates"   # Layer 3
    TOPOLOGY_SIGNATURES = "topology_signatures"     # Layer 4 — Prompt 3
    POWER_INVARIANTS = "power_invariants"        # Layer 5 — Prompt 3


@dataclass
class LayerViolation:
    layer: VerifierLayer
    severity: str              # "CRITICAL" | "WARNING"
    net_name: Optional[str]    # net where violation occurred, None if N/A
    ref: Optional[str]         # component ref, None if N/A
    pin_number: Optional[str]  # pin number, None if N/A
    message: str


@dataclass
class LayerResult:
    layer: VerifierLayer
    score: float           # 0.0 = all constraints failed, 1.0 = all passed
    constraints_checked: int
    constraints_passed: int
    violations: list[LayerViolation] = field(default_factory=list)
    skipped: bool = False    # True if layer could not run (missing data)
    skip_reason: Optional[str] = None


@dataclass
class VerificationResult:
    """Continuous scoring result from the structural verifier.

    score: float in [0.0, 1.0] — weighted mean of implemented layer scores.
           0.0 means all constraints failed. 1.0 means all constraints passed.
           Layers marked skipped=True contribute their weight at 0.5 (neutral).

    layer_results: per-layer breakdown for targeted error feedback.
                   The search controller uses this to decide which layer
                   to target in the next refinement prompt.

    critical_violations: flat list of CRITICAL severity violations across
                         all layers. Used by the SA polisher to identify
                         which connections to swap.
    """
    score: float
    layer_results: list[LayerResult]
    critical_violations: list[LayerViolation]
    total_constraints_checked: int
    total_constraints_passed: int

    def get_layer(self, layer: VerifierLayer) -> Optional[LayerResult]:
        for lr in self.layer_results:
            if lr.layer == layer:
                return lr
        return None

    def lowest_scoring_layer(self) -> Optional[LayerResult]:
        """Return the non-skipped layer with the lowest score."""
        candidates = [lr for lr in self.layer_results if not lr.skipped]
        if not candidates:
            return None
        return min(candidates, key=lambda lr: lr.score)


# Roles that actively drive a net (sources of signal or power)
_DRIVER_ROLES: frozenset[PinRole] = frozenset({
    PinRole.POWER_OUT,
    PinRole.SIGNAL_OUT,
    PinRole.ANALOG_OUT,
})

# Roles that are passive receivers (sinks)
_RECEIVER_ROLES: frozenset[PinRole] = frozenset({
    PinRole.POWER_IN,
    PinRole.SIGNAL_IN,
    PinRole.ANALOG_IN,
    PinRole.ENABLE,
    PinRole.ENABLE_N,
    PinRole.RESET,
    PinRole.CHIP_SELECT,
    PinRole.INTERRUPT,
    PinRole.FEEDBACK,
    PinRole.ADJUST,
})

# Roles that are bidirectional or shared
_SHARED_ROLES: frozenset[PinRole] = frozenset({
    PinRole.BIDIRECTIONAL,
    PinRole.GROUND,
    PinRole.REFERENCE,
    PinRole.SENSE_POS,
    PinRole.SENSE_NEG,
    PinRole.DIFFERENTIAL_POS,
    PinRole.DIFFERENTIAL_NEG,
    PinRole.CLOCK,
    PinRole.EXPOSED_PAD,
})

# Roles that must never appear on a connected net
_UNCONNECTABLE_ROLES: frozenset[PinRole] = frozenset({PinRole.NC})

# Maps component_type substring → set of PinRole that MUST appear in that
# component's connected pins. All roles in the set must be present.
_SUBCATEGORY_TEMPLATES: dict[str, frozenset[PinRole]] = {
    "op_amp": frozenset({PinRole.POWER_IN, PinRole.SIGNAL_OUT}),
    "opamp": frozenset({PinRole.POWER_IN, PinRole.SIGNAL_OUT}),
    "comparator": frozenset({PinRole.POWER_IN, PinRole.SIGNAL_OUT}),
    "ldo": frozenset({PinRole.POWER_IN, PinRole.GROUND, PinRole.POWER_OUT}),
    "ldo_regulator": frozenset({PinRole.POWER_IN, PinRole.GROUND, PinRole.POWER_OUT}),
    "buck": frozenset({PinRole.POWER_IN, PinRole.GROUND, PinRole.POWER_OUT}),
    "boost": frozenset({PinRole.POWER_IN, PinRole.GROUND, PinRole.POWER_OUT}),
    "adc": frozenset({PinRole.POWER_IN, PinRole.GROUND, PinRole.ANALOG_IN}),
    "dac": frozenset({PinRole.POWER_IN, PinRole.GROUND, PinRole.ANALOG_OUT}),
    "microcontroller": frozenset({PinRole.POWER_IN, PinRole.GROUND}),
    "mcu": frozenset({PinRole.POWER_IN, PinRole.GROUND}),
    "mosfet": frozenset({PinRole.ENABLE}),          # gate must be driven
    "gate_driver": frozenset({PinRole.POWER_IN, PinRole.SIGNAL_IN}),
    "current_source": frozenset({PinRole.POWER_IN, PinRole.GROUND}),
}

# Layer weights for weighted mean score computation.
# Layers 4 and 5 not yet implemented — their weight redistributes to
# implemented layers proportionally at runtime.
_LAYER_WEIGHTS: dict[VerifierLayer, float] = {
    VerifierLayer.ELECTRICAL_INVARIANTS: 0.35,
    VerifierLayer.PIN_ROLE_COMPATIBILITY: 0.30,
    VerifierLayer.SUBCATEGORY_TEMPLATES: 0.20,
    VerifierLayer.TOPOLOGY_SIGNATURES: 0.10,  # Prompt 3
    VerifierLayer.POWER_INVARIANTS: 0.05,  # Prompt 3
}


def _build_pin_role_lookup(
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
) -> dict[tuple[str, str], Optional[PinRole]]:
    """Build lookup: (ref, pin_number) → PinRole | None.

    Returns PinRole if the pin has one set (from Prompt 1 normalizer).
    Returns None if the datasheet is missing or pin has no role.
    """
    lookup: dict[tuple[str, str], Optional[PinRole]] = {}
    for _component_id, (ref, datasheet) in ref_map.items():
        if datasheet is None:
            continue
        for pin in datasheet.pins:
            lookup[(ref, pin.pin_number)] = pin.pin_role
    return lookup


def _run_layer1(
    netlist: list[NetlistEntry],
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
) -> LayerResult:
    """Layer 1: Electrical invariants via existing ERC.

    Score = (rules_checked - critical_violations) / rules_checked
    Each CRITICAL violation reduces the score by 1/rules_checked.
    WARNING violations reduce by 0.5/rules_checked.
    """
    erc_result = check_erc(netlist, ref_map)

    rules_checked = max(erc_result.rules_checked, 1)
    critical_count = sum(
        1 for v in erc_result.violations if v.severity == "CRITICAL"
    )
    warning_count = sum(
        1 for v in erc_result.violations if v.severity == "WARNING"
    )

    penalty = critical_count * 1.0 + warning_count * 0.5
    raw_score = max(0.0, rules_checked - penalty) / rules_checked
    score = round(max(0.0, min(1.0, raw_score)), 4)

    violations = [
        LayerViolation(
            layer=VerifierLayer.ELECTRICAL_INVARIANTS,
            severity=v.severity,
            net_name=None,
            ref=v.affected_refs[0] if v.affected_refs else None,
            pin_number=None,
            message=v.message,
        )
        for v in erc_result.violations
    ]

    return LayerResult(
        layer=VerifierLayer.ELECTRICAL_INVARIANTS,
        score=score,
        constraints_checked=rules_checked,
        constraints_passed=rules_checked - critical_count,
        violations=violations,
    )


def _run_layer2(
    netlist: list[NetlistEntry],
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
) -> LayerResult:
    """Layer 2: Pin-role compatibility checking."""
    pin_role_lookup = _build_pin_role_lookup(ref_map)

    violations: list[LayerViolation] = []
    constraints_checked = 0
    constraints_passed = 0

    for net in netlist:
        if not net.connections:
            continue

        # Collect roles for all connected pins
        roles_on_net: list[tuple[PinRef, Optional[PinRole]]] = []
        for conn in net.connections:
            role = pin_role_lookup.get((conn.ref, conn.pin_number))
            roles_on_net.append((conn, role))

        known_roles = [r for _, r in roles_on_net if r is not None]

        # Rule 2.1 — driver conflict
        constraints_checked += 1
        driver_roles_present = [r for r in known_roles if r in _DRIVER_ROLES]
        driver_type_counts: dict[PinRole, int] = {}
        for r in driver_roles_present:
            driver_type_counts[r] = driver_type_counts.get(r, 0) + 1

        conflict_found = any(c > 1 for c in driver_type_counts.values())
        if conflict_found:
            for role, count in driver_type_counts.items():
                if count > 1:
                    violations.append(LayerViolation(
                        layer=VerifierLayer.PIN_ROLE_COMPATIBILITY,
                        severity="CRITICAL",
                        net_name=net.net_name,
                        ref=None,
                        pin_number=None,
                        message=(
                            f"Net '{net.net_name}' has {count} pins with role "
                            f"'{role.value}' — driver conflict (short circuit risk)"
                        ),
                    ))
        else:
            constraints_passed += 1

        # Rule 2.2 — NC pins must not be connected
        constraints_checked += 1
        nc_pins = [conn for conn, r in roles_on_net if r == PinRole.NC]
        if nc_pins and len(net.connections) > 1:
            for conn in nc_pins:
                violations.append(LayerViolation(
                    layer=VerifierLayer.PIN_ROLE_COMPATIBILITY,
                    severity="CRITICAL",
                    net_name=net.net_name,
                    ref=conn.ref,
                    pin_number=conn.pin_number,
                    message=(
                        f"NC pin {conn.ref}.{conn.pin_number} is connected on "
                        f"net '{net.net_name}' — NC pins must not be connected"
                    ),
                ))
        else:
            constraints_passed += 1

        # Rule 2.3 — power nets need a driver
        if net.net_type == "power":
            constraints_checked += 1
            power_drivers = {PinRole.POWER_OUT, PinRole.GROUND}
            has_driver = any(r in power_drivers for r in known_roles)
            if not has_driver and known_roles:
                violations.append(LayerViolation(
                    layer=VerifierLayer.PIN_ROLE_COMPATIBILITY,
                    severity="WARNING",
                    net_name=net.net_name,
                    ref=None,
                    pin_number=None,
                    message=(
                        f"Power net '{net.net_name}' has no POWER_OUT or GROUND "
                        f"driver pin — net may be undriven"
                    ),
                ))
            else:
                constraints_passed += 1

    if constraints_checked == 0:
        return LayerResult(
            layer=VerifierLayer.PIN_ROLE_COMPATIBILITY,
            score=1.0,
            constraints_checked=0,
            constraints_passed=0,
            skipped=True,
            skip_reason="No nets with connections found",
        )

    critical_count = sum(1 for v in violations if v.severity == "CRITICAL")
    warning_count = sum(1 for v in violations if v.severity == "WARNING")
    penalty = critical_count * 1.0 + warning_count * 0.5
    score = round(
        max(0.0, min(1.0, (constraints_checked - penalty) / constraints_checked)),
        4,
    )

    return LayerResult(
        layer=VerifierLayer.PIN_ROLE_COMPATIBILITY,
        score=score,
        constraints_checked=constraints_checked,
        constraints_passed=constraints_passed,
        violations=violations,
    )


def _run_layer3(
    netlist: list[NetlistEntry],
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
    bom: Optional[ValidatedBOM],
) -> LayerResult:
    """Layer 3: Subcategory template checks.

    Verifies that each component has its mandatory pin roles connected.
    Skipped if ValidatedBOM is not provided.
    """
    if bom is None:
        return LayerResult(
            layer=VerifierLayer.SUBCATEGORY_TEMPLATES,
            score=1.0,
            constraints_checked=0,
            constraints_passed=0,
            skipped=True,
            skip_reason="ValidatedBOM not provided — Layer 3 skipped",
        )

    # Build set of (ref, pin_number) pairs that are actually connected
    connected_pins: set[tuple[str, str]] = set()
    for net in netlist:
        for conn in net.connections:
            connected_pins.add((conn.ref, conn.pin_number))

    # Build ref → component_type mapping from BOM
    ref_to_type: dict[str, str] = {}
    for component in bom.components:
        ref_to_type[component.ref] = component.component_type.lower()

    violations: list[LayerViolation] = []
    constraints_checked = 0
    constraints_passed = 0

    for _component_id, (ref, datasheet) in ref_map.items():
        if datasheet is None:
            continue

        component_type = ref_to_type.get(ref, "").lower()
        if not component_type:
            continue

        # Find matching template(s) by substring
        required_roles: set[PinRole] = set()
        for keyword, roles in _SUBCATEGORY_TEMPLATES.items():
            if keyword in component_type:
                required_roles |= roles

        if not required_roles:
            continue  # no template applies to this component type

        # For each required role, check if a connected pin of this ref has it
        for required_role in required_roles:
            constraints_checked += 1

            # Find all pins of this component that have this role
            pins_with_role = [
                pin for pin in datasheet.pins
                if pin.pin_role == required_role
            ]

            # Check if at least one of them is connected
            is_connected = any(
                (ref, pin.pin_number) in connected_pins
                for pin in pins_with_role
            )

            if not pins_with_role:
                # No pin with this role exists — could be normalization miss
                violations.append(LayerViolation(
                    layer=VerifierLayer.SUBCATEGORY_TEMPLATES,
                    severity="WARNING",
                    net_name=None,
                    ref=ref,
                    pin_number=None,
                    message=(
                        f"{ref} ({component_type}): no pin with required role "
                        f"'{required_role.value}' found — normalization may have failed"
                    ),
                ))
            elif not is_connected:
                violations.append(LayerViolation(
                    layer=VerifierLayer.SUBCATEGORY_TEMPLATES,
                    severity="CRITICAL",
                    net_name=None,
                    ref=ref,
                    pin_number=None,
                    message=(
                        f"{ref} ({component_type}): required role "
                        f"'{required_role.value}' pin is not connected in the netlist"
                    ),
                ))
            else:
                constraints_passed += 1

    if constraints_checked == 0:
        return LayerResult(
            layer=VerifierLayer.SUBCATEGORY_TEMPLATES,
            score=1.0,
            constraints_checked=0,
            constraints_passed=0,
            skipped=True,
            skip_reason="No component types matched any template",
        )

    critical_count = sum(1 for v in violations if v.severity == "CRITICAL")
    warning_count = sum(1 for v in violations if v.severity == "WARNING")
    penalty = critical_count * 1.0 + warning_count * 0.5
    score = round(
        max(0.0, min(1.0, (constraints_checked - penalty) / constraints_checked)),
        4,
    )

    return LayerResult(
        layer=VerifierLayer.SUBCATEGORY_TEMPLATES,
        score=score,
        constraints_checked=constraints_checked,
        constraints_passed=constraints_passed,
        violations=violations,
    )


def verify_schematic(
    netlist: list[NetlistEntry],
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]],
    bom: Optional[ValidatedBOM] = None,
) -> VerificationResult:
    """Run the structural verifier on a schematic netlist.

    Args:
        netlist:  List of NetlistEntry objects from the schematic synthesizer.
        ref_map:  Maps component_id → (ref, ComponentDatasheet | None).
                  Datasheets must have pin_role populated (requires Prompt 1
                  pin normalizer to have run).
        bom:      Optional ValidatedBOM. Required for Layer 3 subcategory checks.
                  If None, Layer 3 is skipped.

    Returns:
        VerificationResult with continuous score in [0.0, 1.0] and per-layer
        breakdown. Never raises — skips layers gracefully on missing data.
    """
    layer_results: list[LayerResult] = []

    # Layer 1 — Electrical Invariants
    try:
        layer_results.append(_run_layer1(netlist, ref_map))
    except Exception as exc:
        logger.error("Layer 1 (electrical invariants) failed: %s", exc)
        layer_results.append(LayerResult(
            layer=VerifierLayer.ELECTRICAL_INVARIANTS,
            score=0.5, constraints_checked=0, constraints_passed=0,
            skipped=True, skip_reason=str(exc),
        ))

    # Layer 2 — Pin-Role Compatibility
    try:
        layer_results.append(_run_layer2(netlist, ref_map))
    except Exception as exc:
        logger.error("Layer 2 (pin-role compatibility) failed: %s", exc)
        layer_results.append(LayerResult(
            layer=VerifierLayer.PIN_ROLE_COMPATIBILITY,
            score=0.5, constraints_checked=0, constraints_passed=0,
            skipped=True, skip_reason=str(exc),
        ))

    # Layer 3 — Subcategory Templates
    try:
        layer_results.append(_run_layer3(netlist, ref_map, bom))
    except Exception as exc:
        logger.error("Layer 3 (subcategory templates) failed: %s", exc)
        layer_results.append(LayerResult(
            layer=VerifierLayer.SUBCATEGORY_TEMPLATES,
            score=0.5, constraints_checked=0, constraints_passed=0,
            skipped=True, skip_reason=str(exc),
        ))

    # Compute weighted mean score across non-placeholder layers
    implemented_layers = {
        VerifierLayer.ELECTRICAL_INVARIANTS,
        VerifierLayer.PIN_ROLE_COMPATIBILITY,
        VerifierLayer.SUBCATEGORY_TEMPLATES,
    }
    total_weight = sum(
        _LAYER_WEIGHTS[lr.layer]
        for lr in layer_results
        if lr.layer in implemented_layers
    )
    if total_weight == 0:
        weighted_score = 0.5
    else:
        weighted_score = sum(
            lr.score * _LAYER_WEIGHTS[lr.layer]
            for lr in layer_results
            if lr.layer in implemented_layers
        ) / total_weight

    # Collect all critical violations
    critical_violations = [
        v
        for lr in layer_results
        for v in lr.violations
        if v.severity == "CRITICAL"
    ]

    total_checked = sum(lr.constraints_checked for lr in layer_results)
    total_passed = sum(lr.constraints_passed for lr in layer_results)

    return VerificationResult(
        score=round(max(0.0, min(1.0, weighted_score)), 4),
        layer_results=layer_results,
        critical_violations=critical_violations,
        total_constraints_checked=total_checked,
        total_constraints_passed=total_passed,
    )
