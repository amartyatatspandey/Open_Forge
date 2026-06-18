"""Graph consistency validation for KnowledgeGraph.

Provides validation checks to ensure the knowledge graph maintains
referential integrity and data quality constraints.
"""

from __future__ import annotations

from src.knowledge_graph.graph import KnowledgeGraph
from src.schemas.kg import KGEdge, KGNode


def validate(graph: KnowledgeGraph) -> list[str]:
    """Validate knowledge graph consistency.

    Performs the following checks:
    - No KGEdge references a source_id that doesn't exist as a node (orphaned edge)
    - No KGEdge references a target_id that doesn't exist as a node
    - All node confidence values are in [0.0, 1.0]
    - All edge confidence values are in [0.0, 1.0]
    - No node has an empty label

    Args:
        graph: KnowledgeGraph to validate

    Returns:
        List of human-readable error strings. Empty list = valid graph.

    Example:
        >>> errors = validate(kg)
        >>> if errors:
        ...     for err in errors:
        ...         print(f"Validation error: {err}")
        ... else:
        ...     print("Graph is valid")
    """
    errors = []

    # Check 1 & 2: Orphaned edges (source_id or target_id doesn't exist as node)
    for edge in _get_all_edges(graph):
        if not graph.node_exists(edge.source_id):
            errors.append(
                f"Orphaned edge: source_id '{edge.source_id}' not found as node"
            )
        if not graph.node_exists(edge.target_id):
            errors.append(
                f"Orphaned edge: target_id '{edge.target_id}' not found as node"
            )

    # Check 3: Node confidence values in [0.0, 1.0]
    for node in _get_all_nodes(graph):
        if not (0.0 <= node.confidence <= 1.0):
            errors.append(
                f"Invalid confidence for node '{node.id}': {node.confidence} (must be in [0.0, 1.0])"
            )

    # Check 4: Edge confidence values in [0.0, 1.0]
    for edge in _get_all_edges(graph):
        if not (0.0 <= edge.confidence <= 1.0):
            errors.append(
                f"Invalid confidence for edge '{edge.source_id}' -> '{edge.target_id}': "
                f"{edge.confidence} (must be in [0.0, 1.0])"
            )

    # Check 5: No node has an empty label
    for node in _get_all_nodes(graph):
        if not node.label or not node.label.strip():
            errors.append(f"Node '{node.id}' has empty label")

    return errors


def _get_all_nodes(graph: KnowledgeGraph) -> list[KGNode]:
    """Get all KGNode objects from the graph.

    Args:
        graph: KnowledgeGraph to extract nodes from

    Returns:
        List of KGNode objects
    """
    nodes: list[KGNode] = []
    # Access the internal graph to iterate over all node IDs
    for node_id in graph._graph.nodes:
        node = graph.get_node(node_id)
        if node is not None:
            nodes.append(node)
    return nodes


def _get_all_edges(graph: KnowledgeGraph) -> list[KGEdge]:
    """Get all KGEdge objects from the graph.

    Args:
        graph: KnowledgeGraph to extract edges from

    Returns:
        List of KGEdge objects
    """
    edges: list[KGEdge] = []
    # Access the internal graph to iterate over all edges
    for u, v, data in graph._graph.edges(data=True):
        edge = data.get("data")
        if edge is not None:
            edges.append(edge)
    return edges
