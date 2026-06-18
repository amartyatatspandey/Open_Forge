"""Justification generator — create human-readable rationale for BOM entries.

Uses template strings for fast, deterministic generation without LLM calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.schemas.intent import IntentDict
    from src.schemas.kg import KGNode


def generate(
    comp_type_node: KGNode,
    specific_part: str | None,
    intent: IntentDict,
) -> str:
    """Generate a one-sentence justification for why this component is in the BOM.
    
    Uses template strings — no LLM call. Fast and deterministic.
    
    Template: "{component_label} required for {intent.goal} design.
               {specific_part if present}. Source: {comp_type_node.source}."
    
    Args:
        comp_type_node: The COMPONENT_TYPE node being justified
        specific_part: Selected specific part number, or None if unresolved
        intent: The original design intent
        
    Returns:
        Human-readable justification string
        
    Example:
        >>> justification = generate(capacitor_node, "GRM155R71C104KA88D", intent)
        >>> print(justification)
        "Capacitor required for buck_converter design. Specific part: GRM155R71C104KA88D. Source: TI_SLVA477B.pdf."
    """
    # Clean up the component label for display
    component_label = comp_type_node.label.replace("_", " ").title()
    
    # Clean up the goal
    goal = intent.goal.replace("_", " ")
    
    # Build the base justification
    parts = [f"{component_label} required for {goal} design."]
    
    # Add specific part info if available
    if specific_part:
        parts.append(f"Specific part selected: {specific_part}.")
    else:
        parts.append("Specific part not found — requires manual selection.")
    
    # Add source information
    source = comp_type_node.source
    if source and source not in ("manual", "unknown", ""):
        parts.append(f"Source: {source}.")
    
    return " ".join(parts)
