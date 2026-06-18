"""Constraint inferrer — derive implicit constraints from application context.

Maps application domains to inferred design constraints that should be applied
separate from explicit user-specified constraints.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Application context → inferred constraints mapping
APPLICATION_INFERENCES: dict[str, list[str]] = {
    "drone": ["compact", "lightweight", "low_power", "vibration_resistant"],
    "drones": ["compact", "lightweight", "low_power", "vibration_resistant"],
    "iot sensor": ["low_power", "small_form_factor", "wireless_connectivity"],
    "iot": ["low_power", "small_form_factor", "wireless_connectivity"],
    "industrial": ["wide_temperature_range", "robust", "high_reliability"],
    "industrial control": ["wide_temperature_range", "robust", "high_reliability"],
    "medical": ["high_reliability", "galvanic_isolation", "low_noise"],
    "automotive": ["wide_temperature_range", "emi_compliant", "robust"],
    "wearable": ["ultra_low_power", "compact", "flexible_if_possible"],
    "wearables": ["ultra_low_power", "compact", "flexible_if_possible"],
    "handheld": ["compact", "low_power", "lightweight"],
    "portable": ["compact", "low_power", "battery_operated"],
    "space": ["radiation_tolerant", "high_reliability", "extreme_temperature"],
    "military": ["high_reliability", "wide_temperature_range", "shock_resistant"],
}


def infer_constraints(application: str, explicit_constraints: list[str]) -> list[str]:
    """Infer implicit constraints from application context.

    These are added to IntentDict.inferred_constraints (separate from explicit).

    Match application.lower() against keys (partial match allowed).
    Remove any inferred constraint already in explicit_constraints.

    Args:
        application: The application context string from the prompt
        explicit_constraints: Constraints explicitly stated by the user

    Returns:
        List of inferred constraints not already in explicit_constraints

    Example:
        >>> infer_constraints("drone", ["compact"])
        ['lightweight', 'low_power', 'vibration_resistant']
        >>> infer_constraints("unspecified", [])
        []
    """
    application_lower = application.lower()
    inferred: list[str] = []

    # Find matching application contexts (partial match allowed)
    for app_key, constraints in APPLICATION_INFERENCES.items():
        if app_key in application_lower:
            for constraint in constraints:
                if constraint not in inferred:
                    inferred.append(constraint)
            logger.debug(f"Inferred constraints for '{application}' from '{app_key}': {constraints}")

    # Remove any that are already explicitly stated
    explicit_lower = [c.lower().replace(" ", "_") for c in explicit_constraints]
    explicit_raw_lower = [c.lower() for c in explicit_constraints]

    filtered: list[str] = []
    for constraint in inferred:
        constraint_normalized = constraint.lower().replace("_", " ")
        if constraint not in explicit_constraints and constraint not in explicit_raw_lower:
            # Also check normalized versions
            if constraint.lower() not in explicit_lower and constraint_normalized not in explicit_raw_lower:
                filtered.append(constraint)

    return filtered
