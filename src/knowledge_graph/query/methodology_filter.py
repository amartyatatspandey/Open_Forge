"""Methodology filter — prune placement rules using KG-5 DesignMethodology.

When a DesignMethodology node is active:
  - Only rules whose constraint_type is in active_constraint_types are kept.
  - Any rule whose constraint_type is in suppressed_constraint_types is removed.
  - If active_constraint_types is empty the filter is a no-op (all rules pass).
"""

from __future__ import annotations

import logging
from typing import Optional

from src.schemas.kg import KGNode

logger = logging.getLogger(__name__)


def apply_methodology_filter(
    placement_rule_nodes: list[KGNode],
    methodology_node: Optional[KGNode],
) -> list[KGNode]:
    """Filter PlacementRule nodes using the active DesignMethodology.

    Args:
        placement_rule_nodes: PLACEMENT_RULE nodes from BFS traversal
        methodology_node: KG-5 DESIGN_METHODOLOGY node, or None

    Returns:
        Filtered list of placement rule nodes.
        - If methodology_node is None: all rules are returned unchanged.
        - If active_constraint_types is empty: all rules are returned unchanged.
        - Otherwise: rules matching active types (minus suppressed) are returned.

    Example:
        >>> # RF_highfreq only activates keepout and proximity
        >>> filtered = apply_methodology_filter(rules, rf_methodology_node)
        >>> # only nodes with constraint_type in ["keepout", "proximity"] survive
    """
    if methodology_node is None:
        return placement_rule_nodes

    active_types: list[str] = methodology_node.properties.get("active_constraint_types", [])
    suppressed_types: list[str] = methodology_node.properties.get("suppressed_constraint_types", [])

    if not active_types:
        # No explicit activation list — methodology imposes no filter
        return placement_rule_nodes

    kept: list[KGNode] = []
    for node in placement_rule_nodes:
        constraint_type = node.properties.get("constraint_type")
        if constraint_type in active_types and constraint_type not in suppressed_types:
            kept.append(node)

    logger.debug(
        f"Methodology filter ({methodology_node.label}): "
        f"{len(placement_rule_nodes)} → {len(kept)} placement rules"
    )
    return kept
