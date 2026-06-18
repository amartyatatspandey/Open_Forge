"""BFS traversal with path-confidence tracking.

Path confidence is the PRODUCT of edge confidences along the path from
a start node to the current node — not an average or minimum.

Relations intentionally excluded:
  - IS_A: would flood traversal with type-hierarchy nodes
  - CONNECTS_TO: pin-level wiring, not design-knowledge relationships
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.schemas.kg import KGEdge, KGNode, KGRelation

if TYPE_CHECKING:
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Relations that are traversed during graph search
TRAVERSAL_RELATIONS: frozenset[KGRelation] = frozenset({
    KGRelation.REQUIRES,
    KGRelation.USES,
    KGRelation.HAS_PROPERTY,
    KGRelation.MUST_BE_NEAR,
    KGRelation.REQUIRES_ROUTING,
    KGRelation.PART_OF,
    KGRelation.GOVERNED_BY,  # reaches PLACEMENT_RULE nodes from COMPONENT_TYPE/INSTANCE
})


def bfs_traverse(
    start_nodes: list[KGNode],
    graph: KnowledgeGraph,
    max_depth: int,
    min_edge_confidence: float,
) -> tuple[dict[str, float], list[KGEdge]]:
    """BFS traversal from start_nodes with product path-confidence tracking.

    Args:
        start_nodes: Nodes to start traversal from (path_confidence = 1.0)
        graph: KnowledgeGraph to traverse
        max_depth: Maximum number of hops to follow
        min_edge_confidence: Skip edges below this confidence

    Returns:
        Tuple of:
          - path_confidences: node_id → product of edge confidences on the path
            (start nodes have 1.0; a node reached via two 0.90 edges has 0.81)
          - traversed_edges: KGEdge objects crossed during traversal

    Algorithm:
        Frontier-based BFS. Each depth layer is processed together.
        First visit to a node wins — higher-confidence paths should appear
        earlier in the frontier because they are closer to the start nodes.
        Once a node is in `visited`, it is never revisited.
    """
    # Start nodes get 1.0; first visit wins
    visited: dict[str, float] = {n.id: 1.0 for n in start_nodes}
    traversed_edges: list[KGEdge] = []
    frontier: set[str] = {n.id for n in start_nodes}

    for _depth in range(max_depth):
        next_frontier: set[str] = set()

        for node_id in frontier:
            edges = graph.get_edges_from(node_id, min_confidence=min_edge_confidence)

            for edge in edges:
                if edge.relation not in TRAVERSAL_RELATIONS:
                    continue
                if edge.target_id in visited:
                    continue  # already reached via an earlier (higher-confidence) path

                path_confidence = visited[node_id] * edge.confidence
                visited[edge.target_id] = path_confidence
                traversed_edges.append(edge)
                next_frontier.add(edge.target_id)

        frontier = next_frontier
        if not frontier:
            break  # graph exhausted before max_depth

    return visited, traversed_edges
