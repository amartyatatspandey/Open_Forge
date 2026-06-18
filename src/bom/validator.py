"""BOM validator — runs cross-component compatibility checks.

This module validates cross-component compatibility including voltage levels,
logic level mismatches, and supplier availability. All validation failures
are collected before returning — does not short-circuit on first failure.

Example:
    >>> from src.bom.validator import validate_bom
    >>> from src.schemas.intent import ValidatedBOM
    >>> validated = validate_bom(bom, config)
    >>> if validated.review_required:
    ...     print("Review needed:", validated.review_flags)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.config import Config
    from src.schemas.intent import BOMEntry, ValidatedBOM

from src.bom.supplier_cache import AvailabilityStatus, check_availability

logger = logging.getLogger(__name__)

# Power component types that have output voltage
POWER_COMPONENT_TYPES = ["regulator", "ldo", "buck", "boost", "converter"]

# IC component types for logic level checking
IC_COMPONENT_TYPES = ["microcontroller", "ic"]


def _is_power_component(component_type: str) -> bool:
    """Check if component type is a power component with output voltage."""
    component_type_lower = component_type.lower()
    return any(power_type in component_type_lower for power_type in POWER_COMPONENT_TYPES)


def _is_ic_component(component_type: str) -> bool:
    """Check if component type is an IC for logic level checking."""
    component_type_lower = component_type.lower()
    return any(ic_type in component_type_lower for ic_type in IC_COMPONENT_TYPES)


def _extract_output_voltage(value_constraints: dict[str, Any]) -> float | None:
    """Extract output voltage from value_constraints.

    Args:
        value_constraints: Dictionary of electrical/physical constraints.

    Returns:
        Output voltage as float, or None if not specified.
    """
    voltage = value_constraints.get("output_voltage")
    if voltage is None:
        return None
    try:
        return float(voltage)
    except (ValueError, TypeError):
        return None


def _extract_logic_voltage(value_constraints: dict[str, Any]) -> float | None:
    """Extract logic voltage from value_constraints.

    Args:
        value_constraints: Dictionary of electrical/physical constraints.

    Returns:
        Logic voltage as float, or None if not specified.
    """
    voltage = value_constraints.get("logic_voltage")
    if voltage is None:
        return None
    try:
        return float(voltage)
    except (ValueError, TypeError):
        return None


def _pass1_voltage_compatibility(components: list[BOMEntry]) -> list[str]:
    """Pass 1 — Check voltage compatibility between power components.

    Find all power components and check if any have different output voltages
    that might conflict on the same implicit rail. Since we cannot detect
    rail names yet, we use a component position heuristic.

    Args:
        components: List of BOMEntry objects to validate.

    Returns:
        List of review flag strings for any potential conflicts.
    """
    review_flags: list[str] = []

    # Find all power components with output voltages
    power_components: list[tuple[BOMEntry, float]] = []
    for entry in components:
        if _is_power_component(entry.component_type):
            voltage = _extract_output_voltage(entry.value_constraints)
            if voltage is not None:
                power_components.append((entry, voltage))

    # Check for voltage conflicts between power components
    # For now, we flag any pair with different voltages as potential conflict
    # This is a conservative approach until rail detection is implemented
    for i, (entry1, voltage1) in enumerate(power_components):
        for entry2, voltage2 in power_components[i + 1:]:
            if abs(voltage1 - voltage2) > 0.1:  # 0.1V tolerance
                flag = (
                    f"Potential voltage conflict between {entry1.ref} and {entry2.ref} "
                    f"({voltage1}V vs {voltage2}V)"
                )
                review_flags.append(flag)
                logger.debug(f"Voltage compatibility WARNING: {flag}")

    return review_flags


def _pass2_logic_level_compatibility(components: list[BOMEntry]) -> list[str]:
    """Pass 2 — Check logic level compatibility between ICs.

    Find all ICs (microcontrollers, ICs) and check if any have different
    logic voltages (e.g., 3.3V vs 5V) which would indicate a level mismatch.

    Args:
        components: List of BOMEntry objects to validate.

    Returns:
        List of review flag strings for any logic level mismatches.
    """
    review_flags: list[str] = []

    # Find all ICs with logic voltages
    ic_components: list[tuple[BOMEntry, float]] = []
    for entry in components:
        if _is_ic_component(entry.component_type):
            voltage = _extract_logic_voltage(entry.value_constraints)
            if voltage is not None:
                ic_components.append((entry, voltage))

    # Check for logic level mismatches
    # Flag pairs with significantly different voltages
    for i, (entry1, voltage1) in enumerate(ic_components):
        for entry2, voltage2 in ic_components[i + 1:]:
            if abs(voltage1 - voltage2) > 0.5:  # 0.5V threshold for logic mismatch
                flag = (
                    f"Logic level mismatch: {entry1.ref} ({voltage1}V) vs "
                    f"{entry2.ref} ({voltage2}V)"
                )
                review_flags.append(flag)
                logger.debug(f"Logic level WARNING: {flag}")

    return review_flags


def _pass3_supplier_availability(
    components: list[BOMEntry],
    config: Config,
) -> tuple[list[str], list[BOMEntry]]:
    """Pass 3 — Check supplier availability for resolved components.

    For each BOMEntry where specific_part is set, check the supplier cache
    for availability status. Update review flags based on status.

    Args:
        components: List of BOMEntry objects to validate.
        config: Application configuration.

    Returns:
        Tuple of (review_flags, updated_components) where updated_components
        has review_flag set for unavailable items.
    """
    review_flags: list[str] = []
    updated_components: list[BOMEntry] = []

    for entry in components:
        if entry.specific_part is None:
            # No specific part to check
            updated_components.append(entry)
            continue

        status = check_availability(entry.specific_part, config)

        if status == AvailabilityStatus.UNKNOWN:
            flag = (
                f"Availability unverified for {entry.specific_part} — "
                "confirm before procurement"
            )
            review_flags.append(flag)
            logger.debug(f"Supplier availability INFO: {flag}")
            updated_components.append(entry)

        elif status == AvailabilityStatus.UNAVAILABLE:
            flag = f"{entry.specific_part} marked unavailable in supplier cache"
            review_flags.append(flag)
            logger.debug(f"Supplier availability WARNING: {flag}")
            # Update entry with review_flag=True using model_copy
            updated_entry = entry.model_copy(update={"review_flag": True})
            updated_components.append(updated_entry)

        else:
            # Available - no flag needed
            updated_components.append(entry)

    return review_flags, updated_components


def validate_bom(
    bom: ValidatedBOM,
    config: Config,
) -> ValidatedBOM:
    """Run cross-component validation on the BOM.

    Executes three validation passes in sequence:
    1. Voltage compatibility check for power components
    2. Logic level compatibility check for ICs
    3. Supplier availability check for resolved components

    Collects all failures before returning — does not short-circuit on
    first failure. Returns a new ValidatedBOM, never mutates input.

    Args:
        bom: The ValidatedBOM to validate.
        config: Application configuration with thresholds and cache paths.

    Returns:
        A new ValidatedBOM with validation results. Adds validation failures
        to review_flags. Sets review_required=True if any CRITICAL validation
        fails (currently no CRITICAL checks implemented, all are WARNING/INFO).

    Example:
        >>> from src.bom.validator import validate_bom
        >>> validated = validate_bom(bom, config)
        >>> print(f"Flags: {len(validated.review_flags)}")
        >>> print(f"Review required: {validated.review_required}")
    """
    new_review_flags: list[str] = []
    updated_components = list(bom.components)

    # Pass 1: Voltage compatibility
    voltage_flags = _pass1_voltage_compatibility(updated_components)
    new_review_flags.extend(voltage_flags)

    # Pass 2: Logic level compatibility
    logic_flags = _pass2_logic_level_compatibility(updated_components)
    new_review_flags.extend(logic_flags)

    # Pass 3: Supplier availability
    availability_flags, updated_components = _pass3_supplier_availability(
        updated_components, config
    )
    new_review_flags.extend(availability_flags)

    # Determine if any flags are CRITICAL
    # Currently no CRITICAL flags are generated by this validator
    has_critical = any("CRITICAL" in flag for flag in new_review_flags)

    # Build updated BOM with validation results
    updated_bom = bom.model_copy(update={
        "review_flags": bom.review_flags + new_review_flags,
        "review_required": bom.review_required or has_critical,
        "components": updated_components,
    })

    logger.info(
        f"BOM validation complete: {len(new_review_flags)} flags, "
        f"review_required={updated_bom.review_required}"
    )

    return updated_bom


__all__ = ["validate_bom"]