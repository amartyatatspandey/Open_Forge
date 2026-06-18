"""KG-4 graph builder for placement constraint rules.

Converts PlacementConstraint objects into KG-4 nodes and edges:
- PLACEMENT_RULE nodes in layer 4
- Edges from referenced components to placement rules
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.schemas.datasheet import ExtractionMethod, PlacementConstraint
from src.schemas.kg import KGEdge, KGNode, KGNodeType, KGRelation

if TYPE_CHECKING:
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def convert_placement_constraints_to_graph(
    constraints: list[PlacementConstraint],
    pdf_path: Path,
    graph: KnowledgeGraph,
) -> tuple[int, int]:
    """Convert PlacementConstraints into KG-4 nodes and edges.
    
    Similar logic to p1_importer.py PlacementRule creation:
    - PLACEMENT_RULE nodes in layer 4
    - node_id = "placement_rule:appnote:{pdf_stem}:{i}"
    - Edge from subject component to placement rule via GOVERNED_BY
    
    Args:
        constraints: List of PlacementConstraints
        pdf_path: Path to source PDF
        graph: KnowledgeGraph to add to
        
    Returns:
        Tuple of (nodes_created, edges_created)
    """
    nodes_created = 0
    edges_created = 0
    
    pdf_stem = pdf_path.stem
    source_url = f"file://{pdf_path}"
    
    for i, constraint in enumerate(constraints):
        try:
            # Create placement rule node ID
            node_id = f"placement_rule:appnote:{pdf_stem}:{i}"
            
            # Build properties dict
            properties = {
                "constraint_type": constraint.constraint_type,
                "subject": constraint.subject,
                "relative_to": constraint.relative_to,
                "relative_to_type": constraint.relative_to_type,
                "hard": constraint.hard,
            }
            
            if constraint.max_distance_mm is not None:
                properties["max_distance_mm"] = constraint.max_distance_mm
            if constraint.min_distance_mm is not None:
                properties["min_distance_mm"] = constraint.min_distance_mm
            if constraint.layer is not None:
                properties["layer"] = constraint.layer
            if constraint.source_sentence:
                properties["source_sentence"] = constraint.source_sentence
            
            # Create placement rule node (layer 4)
            rule_node = KGNode(
                id=node_id,
                node_type=KGNodeType.PLACEMENT_RULE,
                layer=4,
                label=f"{constraint.constraint_type}: {constraint.subject} → {constraint.relative_to}",
                properties=properties,
                source=source_url,
                confidence=constraint.confidence,
                extraction_method=ExtractionMethod.P1_PHASE5_NLP,  # From layout section NLP extraction
                created_at=_now_iso(),
            )
            
            graph.add_node(rule_node)
            nodes_created += 1
            
            # Create or reference source node (the component being constrained)
            # Use component_type prefix for generality
            source_node_id = f"component_type:{constraint.subject.lower().replace(' ', '_')}"
            
            # Check if source node exists, create placeholder if not
            if not graph.node_exists(source_node_id):
                source_node = KGNode(
                    id=source_node_id,
                    node_type=KGNodeType.COMPONENT_TYPE,
                    layer=2,  # Component types are in layer 2
                    label=constraint.subject,
                    properties={},
                    source=source_url,
                    confidence=constraint.confidence,
                    extraction_method=ExtractionMethod.MANUAL,  # Referenced from app note prose
                    created_at=_now_iso(),
                )
                graph.add_node(source_node)
                nodes_created += 1
            
            # Create edge: source → placement rule via GOVERNED_BY
            edge = KGEdge(
                source_id=source_node_id,
                relation=KGRelation.GOVERNED_BY,
                target_id=node_id,
                constraints={},
                source_document=pdf_path.name,
                confidence=constraint.confidence,
                layer=4,
            )
            graph.add_edge(edge)
            edges_created += 1
            
        except Exception as e:
            logger.warning(
                f"Failed to convert placement constraint "
                f"({constraint.subject} → {constraint.relative_to}): {e}"
            )
            continue
    
    logger.info(f"KG-4: Created {nodes_created} nodes, {edges_created} edges")
    return nodes_created, edges_created
