"""DesignMethodology management for KG-5.

Provides CRUD operations for DesignMethodology nodes in layer 5,
including seeding default methodologies for common design patterns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from src.schemas.datasheet import ExtractionMethod
from src.schemas.kg import KGNode, KGNodeType

if TYPE_CHECKING:
    from src.config import Config
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Default DesignMethodology definitions for seeding
DEFAULT_METHODOLOGIES: dict[str, dict[str, Any]] = {
    "RF_highfreq": {
        "triggers": ["antenna", "RF", "2.4GHz", "5GHz", "Bluetooth", "WiFi", "LoRa", "GHz", "microwave"],
        "active_constraint_types": ["keepout", "proximity", "layer"],
        "suppressed_constraint_types": [],
        "board_spec_defaults": {
            "layers": 2,
            "material": "Rogers_4003C",
            "min_trace_width_mm": 0.1,
            "min_clearance_mm": 0.1,
        },
    },
    "power_management": {
        "triggers": ["buck", "boost", "LDO", "regulator", "battery", "charger", "SMPS", "converter"],
        "active_constraint_types": ["proximity", "orientation", "group"],
        "suppressed_constraint_types": [],
        "board_spec_defaults": {
            "layers": 2,
            "material": "FR4",
            "min_trace_width_mm": 0.2,
            "min_clearance_mm": 0.2,
        },
    },
    "mixed_signal": {
        "triggers": ["ADC", "DAC", "op-amp", "analog", "sensor", "measurement", "precision"],
        "active_constraint_types": ["proximity", "keepout", "layer"],
        "suppressed_constraint_types": [],
        "board_spec_defaults": {
            "layers": 4,
            "material": "FR4",
            "min_trace_width_mm": 0.1,
            "min_clearance_mm": 0.15,
        },
    },
    "standard_SMD": {
        "triggers": ["microcontroller", "digital", "control", "general", "IoT"],
        "active_constraint_types": ["proximity"],
        "suppressed_constraint_types": [],
        "board_spec_defaults": {
            "layers": 2,
            "material": "FR4",
            "min_trace_width_mm": 0.15,
            "min_clearance_mm": 0.15,
        },
    },
    "through_hole": {
        "triggers": ["prototype", "hand-solder", "THT", "DIP", "through-hole"],
        "active_constraint_types": ["proximity"],
        "suppressed_constraint_types": [],
        "board_spec_defaults": {
            "layers": 2,
            "material": "FR4",
            "min_trace_width_mm": 0.25,
            "min_clearance_mm": 0.25,
        },
    },
}


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_methodology_node_id(name: str) -> str:
    """Create node ID for a DesignMethodology."""
    # Normalize: lowercase, replace spaces with underscores
    normalized = name.lower().replace(" ", "_")
    return f"design_methodology:{normalized}"


def add_methodology(
    graph: KnowledgeGraph,
    name: str,
    triggers: list[str],
    active_constraint_types: list[str],
    suppressed_constraint_types: list[str],
    board_spec_defaults: dict[str, Any],
    config: Config,
) -> KGNode:
    """Add or update a DesignMethodology node in KG-5.

    Idempotent - if methodology with same name exists, it is updated.

    Args:
        graph: KnowledgeGraph to add methodology to
        name: Methodology name (e.g., "RF_highfreq")
        triggers: List of keywords that trigger this methodology
        active_constraint_types: Constraint types to enforce
        suppressed_constraint_types: Constraint types to ignore
        board_spec_defaults: Default board specifications
        config: Application configuration

    Returns:
        Created or updated KGNode (DESIGN_METHODOLOGY, layer=5)

    Example:
        >>> node = add_methodology(
        ...     graph, "custom_method",
        ...     triggers=["LED", "driver"],
        ...     active_constraint_types=["proximity"],
        ...     suppressed_constraint_types=[],
        ...     board_spec_defaults={"layers": 2, "material": "FR4"},
        ...     config
        ... )
        >>> node.layer
        5
    """
    node_id = _make_methodology_node_id(name)

    # Build properties dict
    properties = {
        "triggers": triggers,
        "active_constraint_types": active_constraint_types,
        "suppressed_constraint_types": suppressed_constraint_types,
        "board_spec_defaults": board_spec_defaults,
    }

    node = KGNode(
        id=node_id,
        node_type=KGNodeType.DESIGN_METHODOLOGY,
        layer=5,
        label=name,
        properties=properties,
        source="manual_admin",
        confidence=1.0,  # Manually curated
        extraction_method=ExtractionMethod.MANUAL,
        created_at=_now_iso(),
    )

    # Add/update node (idempotent via graph.add_node)
    graph.add_node(node)

    action = "Updated" if graph.node_exists(node_id) else "Created"
    logger.info(f"{action} DesignMethodology: {name} ({node_id})")

    return node


def list_methodologies(graph: KnowledgeGraph) -> list[KGNode]:
    """Return all KGNodeType.DESIGN_METHODOLOGY nodes.

    Args:
        graph: KnowledgeGraph to query

    Returns:
        List of DESIGN_METHODOLOGY nodes sorted by label

    Example:
        >>> methodologies = list_methodologies(graph)
        >>> len(methodologies)
        5
    """
    # Use find_nodes_by_type to get all DESIGN_METHODOLOGY nodes
    methodologies = graph.find_nodes_by_type(KGNodeType.DESIGN_METHODOLOGY)

    # Sort by label
    methodologies.sort(key=lambda n: n.label)

    return methodologies


def get_methodology(graph: KnowledgeGraph, name: str) -> Optional[KGNode]:
    """Return methodology node by name.

    Args:
        graph: KnowledgeGraph to query
        name: Methodology name (e.g., "RF_highfreq")

    Returns:
        KGNode if found, None otherwise

    Example:
        >>> node = get_methodology(graph, "power_management")
        >>> node is not None
        True
        >>> node = get_methodology(graph, "nonexistent")
        >>> node is None
        True
    """
    node_id = _make_methodology_node_id(name)

    try:
        node = graph.get_node(node_id)
        if node is not None and node.node_type == KGNodeType.DESIGN_METHODOLOGY:
            return node
    except Exception:
        pass

    return None


def seed_default_methodologies(graph: KnowledgeGraph, config: Config) -> int:
    """Populate KG-5 with all 5 default DesignMethodology nodes.

    Idempotent - safe to run multiple times. Updates existing nodes.

    Args:
        graph: KnowledgeGraph to seed
        config: Application configuration

    Returns:
        Count of nodes created/updated

    Example:
        >>> count = seed_default_methodologies(graph, config)
        >>> count
        5
        >>> # Run again - idempotent
        >>> count = seed_default_methodologies(graph, config)
        >>> count
        5
    """
    count = 0

    for name, data in DEFAULT_METHODOLOGIES.items():
        try:
            add_methodology(
                graph=graph,
                name=name,
                triggers=data["triggers"],
                active_constraint_types=data["active_constraint_types"],
                suppressed_constraint_types=data["suppressed_constraint_types"],
                board_spec_defaults=data["board_spec_defaults"],
                config=config,
            )
            count += 1
        except Exception as e:
            logger.error(f"Failed to seed methodology {name}: {e}")
            continue

    logger.info(f"Seeded {count} default methodologies")
    return count
