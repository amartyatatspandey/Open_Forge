"""Graph builder for AAC chapter triples.

Converts extracted Triple objects into KGNode and KGEdge objects in KG-1
(physics layer).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.knowledge_graph.ingestion._schemas import IngestionResult, Triple
from src.schemas.datasheet import ExtractionMethod
from src.schemas.kg import KGEdge, KGNode, KGNodeType

if TYPE_CHECKING:
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


def _make_node_id(name: str) -> str:
    """Create a node ID from a concept name.
    
    Args:
        name: Concept name (e.g., "Ohm's Law")
    
    Returns:
        Normalized node ID (e.g., "physics_concept:ohms_law")
    """
    # Normalize: lowercase, replace spaces with underscores, remove special chars
    normalized = name.lower()
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("'", "")
    normalized = normalized.replace("-", "_")
    normalized = normalized.replace("/", "_")
    normalized = normalized.replace("(", "")
    normalized = normalized.replace(")", "")
    # Remove multiple underscores
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    # Strip trailing underscores
    normalized = normalized.strip("_")
    
    return f"physics_concept:{normalized}"


def _create_physics_node(
    name: str,
    source_url: str,
    confidence: float,
    extraction_method: ExtractionMethod,
) -> KGNode:
    """Create a KGNode for a physics concept (KG-1 layer).
    
    Args:
        name: Concept name
        source_url: Source URL
        confidence: Confidence score
        extraction_method: Extraction method
    
    Returns:
        KGNode for the physics concept
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    return KGNode(
        id=_make_node_id(name),
        node_type=KGNodeType.PHYSICS_CONCEPT,
        layer=1,
        label=name,
        properties={},
        source=source_url,
        confidence=confidence,
        extraction_method=extraction_method,
        created_at=now,
    )


def convert_triples_to_graph(
    triples: list[Triple],
    volume: int,
    chapter_title: str,
    graph: KnowledgeGraph,
) -> IngestionResult:
    """Convert Triple list into KGNode + KGEdge in the graph.
    
    Creates physics concept nodes (layer 1) for each subject and object,
    and edges connecting them based on the triples.
    
    Args:
        triples: List of extracted Triples
        volume: Volume number
        chapter_title: Chapter title for logging
        graph: KnowledgeGraph to add nodes/edges to
    
    Returns:
        IngestionResult with counts and status
    """
    result = IngestionResult(
        source_document=f"AAC Vol {volume}: {chapter_title}",
    )
    
    if not triples:
        logger.warning(f"No triples to convert for {chapter_title}")
        result.errors.append("No triples provided")
        return result
    
    logger.info(f"Converting {len(triples)} triples to graph for {chapter_title}")
    
    # Track created node IDs to avoid duplicates
    created_node_ids: set[str] = set()
    
    for triple in triples:
        try:
            # Create subject node
            subject_id = _make_node_id(triple.subject)
            
            # Only create node if it doesn't exist
            if not graph.node_exists(subject_id):
                subject_node = _create_physics_node(
                    triple.subject,
                    triple.source_url,
                    triple.confidence,
                    triple.extraction_method,
                )
                graph.add_node(subject_node)
                result.nodes_created += 1
                created_node_ids.add(subject_id)
            else:
                # Update existing node
                subject_node = _create_physics_node(
                    triple.subject,
                    triple.source_url,
                    triple.confidence,
                    triple.extraction_method,
                )
                graph.add_node(subject_node)
            
            # Create object node
            object_id = _make_node_id(triple.object_text)
            
            if not graph.node_exists(object_id):
                object_node = _create_physics_node(
                    triple.object_text,
                    triple.source_url,
                    triple.confidence,
                    triple.extraction_method,
                )
                graph.add_node(object_node)
                result.nodes_created += 1
                created_node_ids.add(object_id)
            else:
                # Update existing node
                object_node = _create_physics_node(
                    triple.object_text,
                    triple.source_url,
                    triple.confidence,
                    triple.extraction_method,
                )
                graph.add_node(object_node)
            
            # Create edge
            edge = KGEdge(
                source_id=subject_id,
                relation=triple.relation,
                target_id=object_id,
                constraints={},
                source_document=triple.source_document,
                confidence=triple.confidence,
                layer=1,
            )
            graph.add_edge(edge)
            result.edges_created += 1
            result.triples_extracted += 1
            
        except Exception as e:
            error_msg = f"Failed to convert triple ({triple.subject} → {triple.object_text}): {e}"
            logger.warning(error_msg)
            result.errors.append(error_msg)
    
    result.success = len(result.errors) == 0 or result.triples_extracted > 0
    
    logger.info(
        f"Converted {result.triples_extracted} triples to "
        f"{result.nodes_created} nodes, {result.edges_created} edges"
    )
    
    return result
