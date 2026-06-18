"""Type resolution for relative_to field in PlacementConstraint.

Determines the relative_to_type enum value from a relative_to string,
applying heuristics for pin references, component references, and
board edge references.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Keywords indicating board edge references
BOARD_EDGE_KEYWORDS = ["board", "edge", "boundary", "perimeter", "outline"]

# Pattern for standard component reference designators (e.g., U1, C23, R456)
COMPONENT_PATTERN = re.compile(r'^[A-Z]{1,3}\d+$')


def resolve_relative_to_type(relative_to: str) -> tuple[str, bool]:
    """Determine relative_to_type from relative_to string.

    Applies classification rules in order of specificity:
    1. Pin references: Contains dot with 2 parts (e.g., "U1.VIN")
    2. Component references: Standard designator pattern (e.g., "C1", "U23")
    3. Board edge: Keywords like "board", "edge", "boundary"
    4. Default: Component with needs_review=True

    Args:
        relative_to: The relative_to string from LLM extraction

    Returns:
        Tuple of (resolved_type, needs_review):
        - resolved_type: One of "pin", "component", "board_edge"
        - needs_review: True if classification uncertain and needs human review

    Examples:
        >>> resolve_relative_to_type("U1.VIN")
        ("pin", False)
        >>> resolve_relative_to_type("C1")
        ("component", False)
        >>> resolve_relative_to_type("board edge north")
        ("board_edge", False)
        >>> resolve_relative_to_type("unknown thing")
        ("component", True)
    """
    if not relative_to or not isinstance(relative_to, str):
        logger.debug("Empty or invalid relative_to, defaulting to component with review")
        return ("component", True)

    relative_to_clean = relative_to.strip()

    # Rule 1: Pin reference detection
    # Format: "Component.PinName" with exactly 2 parts
    if "." in relative_to_clean:
        parts = relative_to_clean.split(".")
        if len(parts) == 2:
            # Looks like a pin reference
            component_part, pin_part = parts[0].strip(), parts[1].strip()
            # Validate component part looks like a designator
            if COMPONENT_PATTERN.match(component_part):
                logger.debug(f"Classified '{relative_to}' as pin reference")
                return ("pin", False)
            else:
                # Dot present but doesn't look like valid pin ref
                logger.debug(f"Dot in '{relative_to}' but invalid component part")
                return ("pin", True)

    # Rule 2: Component reference detection
    # Pattern: 1-3 letters followed by digits (e.g., U1, C23, IC101)
    if COMPONENT_PATTERN.match(relative_to_clean):
        logger.debug(f"Classified '{relative_to}' as component reference")
        return ("component", False)

    # Rule 3: Board edge detection
    relative_lower = relative_to_clean.lower()
    if any(keyword in relative_lower for keyword in BOARD_EDGE_KEYWORDS):
        logger.debug(f"Classified '{relative_to}' as board_edge reference")
        return ("board_edge", False)

    # Rule 4: Default to component with review flag
    logger.warning(
        f"Could not classify relative_to '{relative_to}', "
        f"defaulting to component with review flag"
    )
    return ("component", True)
