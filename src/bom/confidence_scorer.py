"""Confidence scorer — weighted aggregate BOM confidence calculation.

Critical components have higher weight in the aggregate score.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.schemas.intent import BOMEntry
    from src.schemas.kg import DesignSubgraph


# Component criticality weights
# Critical components (regulators, antennas, MCUs) have higher impact on design success
COMPONENT_CRITICALITY: dict[str, float] = {
    # Power components (high criticality)
    "voltage_regulator": 2.0,
    "ldo_regulator": 2.0,
    "buck_converter": 2.0,
    "boost_converter": 2.0,
    "buck_boost": 2.0,
    "dc_dc_converter": 2.0,
    "power_management": 2.0,
    
    # RF components (high criticality)
    "antenna": 2.0,
    "patch_antenna": 2.0,
    "dipole_antenna": 2.0,
    "rf_ic": 2.0,
    "rf_transceiver": 2.0,
    "rf_frontend": 2.0,
    "low_noise_amplifier": 2.0,
    "power_amplifier": 2.0,
    
    # Control/processing (high criticality)
    "microcontroller": 2.0,
    "mcu": 2.0,
    "processor": 2.0,
    "fpga": 2.0,
    "asic": 2.0,
    "soc": 2.0,
    
    # Passive components (lower criticality - easier to substitute)
    "capacitor": 0.5,
    "cap": 0.5,
    "resistor": 0.5,
    "res": 0.5,
    "inductor": 0.5,
    "ind": 0.5,
    "ferrite_bead": 0.5,
    
    # Common passives
    "ceramic_capacitor": 0.5,
    "electrolytic_capacitor": 0.5,
    "tantalum_capacitor": 0.5,
    "film_capacitor": 0.5,
    "chip_resistor": 0.5,
    "power_inductor": 0.8,  # slightly higher for power inductors
    "shielded_inductor": 0.8,
}

_DEFAULT_WEIGHT = 1.0


def _get_component_weight(component_type: str) -> float:
    """Get the criticality weight for a component type.
    
    Args:
        component_type: The component type label
        
    Returns:
        Weight factor (default 1.0 if not in criticality map)
    """
    component_lower = component_type.lower()
    
    # Check for exact match
    if component_lower in COMPONENT_CRITICALITY:
        return COMPONENT_CRITICALITY[component_lower]
    
    # Check if any keyword is contained in the component type
    for keyword, weight in COMPONENT_CRITICALITY.items():
        if keyword in component_lower:
            return weight
    
    return _DEFAULT_WEIGHT


def score_bom(
    entries: list[BOMEntry],
    subgraph: DesignSubgraph,
) -> float:
    """Calculate weighted aggregate confidence across all BOM entries.
    
    Uses component criticality weights:
    - Voltage regulators, antennas, microcontrollers: weight=2.0
    - Capacitors, resistors, inductors: weight=0.5
    - Default: weight=1.0
    
    Formula: score = sum(entry.confidence * weight) / sum(weights)
    Result is clamped to [0.0, 1.0].
    
    Args:
        entries: List of BOMEntry objects
        subgraph: DesignSubgraph for additional context
        
    Returns:
        Aggregate confidence score in [0.0, 1.0]
        
    Example:
        >>> score = score_bom(bom_entries, subgraph)
        >>> print(f"BOM confidence: {score:.2f}")
        BOM confidence: 0.87
    """
    if not entries:
        return 0.0
    
    total_weighted_confidence = 0.0
    total_weight = 0.0
    
    for entry in entries:
        weight = _get_component_weight(entry.component_type)
        total_weighted_confidence += entry.confidence * weight
        total_weight += weight
    
    if total_weight == 0:
        return 0.0
    
    score = total_weighted_confidence / total_weight
    
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, round(score, 4)))
