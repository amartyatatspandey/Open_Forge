"""Component selector — choose specific parts from DesignSubgraph.

Maps COMPONENT_TYPE nodes to BOMEntry objects with reference designators
and specific part selections (when available).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.schemas.intent import BOMEntry, IntentDict
    from src.schemas.kg import DesignSubgraph, KGEdge, KGNode

logger = logging.getLogger(__name__)

# Component label → reference designator prefix
REF_DESIGNATOR_MAP: dict[str, str] = {
    "capacitor": "C",
    "cap": "C",
    "resistor": "R",
    "res": "R",
    "inductor": "L",
    "ind": "L",
    "antenna": "ANT",
    "ant": "ANT",
    "connector": "J",
    "conn": "J",
    "crystal": "X",
    "xtal": "X",
    "diode": "D",
    "transistor": "Q",
    "fuse": "F",
    "switch": "SW",
    "led": "D",
    "battery": "BT",
    "speaker": "SP",
    "microphone": "MK",
    "transformer": "T",
    "relay": "K",
    "motor": "M",
    "solenoid": "SOL",
    "potentiometer": "RV",
    "varistor": "RV",
    "thermistor": "RT",
}

# Default prefix for ICs and everything else
_DEFAULT_REF_PREFIX = "U"


def _get_ref_prefix(label: str) -> str:
    """Get reference designator prefix for a component label.
    
    Args:
        label: Component type label (e.g., "capacitor", "ldo_regulator")
        
    Returns:
        Reference designator prefix (e.g., "C", "U", "R")
    """
    label_lower = label.lower()
    
    # Check for exact match first
    if label_lower in REF_DESIGNATOR_MAP:
        return REF_DESIGNATOR_MAP[label_lower]
    
    # Check if any keyword is contained in the label
    for keyword, prefix in REF_DESIGNATOR_MAP.items():
        if keyword in label_lower:
            return prefix
    
    # Check for IC-related keywords
    ic_keywords = [
        "regulator", "ic", "chip", "processor", "microcontroller", "mcu",
        "fpga", "asic", "sensor", "adc", "dac", "opamp", "op-amp",
        "amplifier", "driver", "controller", "converter", "module",
        "interface", "transceiver", "memory", "eeprom", "flash",
    ]
    for keyword in ic_keywords:
        if keyword in label_lower:
            return _DEFAULT_REF_PREFIX
    
    return _DEFAULT_REF_PREFIX


class RefCounter:
    """Manages reference designator counters per BOM generation."""
    
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
    
    def next(self, prefix: str) -> int:
        """Get next number for a given prefix."""
        current = self._counters.get(prefix, 0)
        current += 1
        self._counters[prefix] = current
        return current
    
    def reset(self) -> None:
        """Reset all counters."""
        self._counters.clear()


# Global counter instance (reset per BOM generation)
_ref_counter = RefCounter()


def _find_matching_instance(
    comp_type_node: KGNode,
    subgraph: DesignSubgraph,
) -> Optional[KGNode]:
    """Find a COMPONENT_INSTANCE matching the component type.
    
    Match criteria (in order of preference):
    1. instance.properties.get("component_type") == comp_type_node.label
    2. Any REQUIRES/PART_OF edge from comp_type_node leads to the instance
    
    Args:
        comp_type_node: COMPONENT_TYPE node from subgraph
        subgraph: The DesignSubgraph containing instances
        
    Returns:
        Matching KGNode or None
    """
    # Strategy 1: Check component_type property
    for instance in subgraph.component_instances:
        comp_type_property = instance.properties.get("component_type")
        if comp_type_property and comp_type_property.lower() == comp_type_node.label.lower():
            return instance
    
    # Strategy 2: Check design_rules edges
    from src.schemas.kg import KGRelation
    
    for edge in subgraph.design_rules:
        if edge.source_id == comp_type_node.id:
            # Check if this edge leads to an instance
            for instance in subgraph.component_instances:
                if edge.target_id == instance.id:
                    if edge.relation in (KGRelation.REQUIRES, KGRelation.PART_OF):
                        return instance
    
    return None


def _get_value_constraints(
    comp_type_node: KGNode,
    subgraph: DesignSubgraph,
) -> dict[str, Any]:
    """Collect value constraints from design_rules edges.
    
    Args:
        comp_type_node: COMPONENT_TYPE node
        subgraph: DesignSubgraph with design_rules
        
    Returns:
        Dict of constraint name → constraint value
    """
    constraints: dict[str, Any] = {}
    
    for edge in subgraph.design_rules:
        if edge.source_id == comp_type_node.id and edge.constraints:
            # Merge all constraints from edges
            for key, value in edge.constraints.items():
                constraints[key] = value
    
    return constraints


def select_component(
    comp_type_node: KGNode,
    subgraph: DesignSubgraph,
    intent: IntentDict,
    counter: RefCounter,
) -> BOMEntry:
    """Select the best specific part for a component type.
    
    Step 1: Check subgraph.component_instances for a matching specific part
    Step 2: If no match found → specific_part = None (with confidence penalty)
    Step 3: Generate justification
    Step 4: Collect value constraints from design_rules
    Step 5: Assign reference designator
    
    Args:
        comp_type_node: COMPONENT_TYPE node from the subgraph
        subgraph: DesignSubgraph with traversal results
        intent: Original design intent
        counter: Reference designator counter
        
    Returns:
        BOMEntry with component selection details
    """
    from src.schemas.intent import BOMEntry
    from src.bom.justification import generate as generate_justification
    
    # Get base confidence from subgraph
    base_confidence = subgraph.path_confidences.get(comp_type_node.id, 0.5)
    
    # Step 1: Try to find a matching component instance
    matching_instance = _find_matching_instance(comp_type_node, subgraph)
    
    # Step 2: Determine specific_part and confidence
    if matching_instance is not None:
        specific_part = matching_instance.label
        confidence = base_confidence
        source = matching_instance.source
        alternatives: list[str] = []
        review_flag = False
    else:
        # No specific part found → penalty for unresolved part
        specific_part = None
        confidence = base_confidence * 0.85  # 15% penalty
        source = comp_type_node.source
        alternatives = []
        review_flag = True  # Needs human review
    
    # Step 3: Generate justification
    justification = generate_justification(comp_type_node, specific_part, intent)
    
    # Step 4: Collect value constraints
    value_constraints = _get_value_constraints(comp_type_node, subgraph)
    
    # Step 5: Assign reference designator
    ref_prefix = _get_ref_prefix(comp_type_node.label)
    ref_number = counter.next(ref_prefix)
    ref = f"{ref_prefix}{ref_number}"
    
    return BOMEntry(
        ref=ref,
        component_type=comp_type_node.label,
        specific_part=specific_part,
        value_constraints=value_constraints,
        justification=justification,
        source=source,
        confidence=round(confidence, 4),
        alternatives=alternatives,
        review_flag=review_flag,
    )


def reset_counter() -> None:
    """Reset the global reference designator counter.
    
    Call this at the start of each BOM generation.
    """
    _ref_counter.reset()


def get_counter() -> RefCounter:
    """Get the global reference designator counter."""
    return _ref_counter
