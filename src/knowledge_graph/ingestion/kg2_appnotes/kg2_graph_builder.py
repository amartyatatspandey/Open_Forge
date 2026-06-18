"""KG-2 graph builder for design recipe triples.

Converts design rule Triple objects into KG-2 nodes and edges:
- DESIGN_RECIPE nodes for design patterns/circuits
- COMPONENT_TYPE nodes for component categories
- ELECTRICAL_PROPERTY nodes for measurements/specs
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.knowledge_graph.ingestion._schemas import Triple
from src.schemas.datasheet import ExtractionMethod
from src.schemas.kg import KGEdge, KGNode, KGNodeType

if TYPE_CHECKING:
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Design pattern keywords heuristic
DESIGN_PATTERN_KEYWORDS: set[str] = {
    "design",
    "circuit",
    "topology",
    "converter",
    "amplifier",
    "filter",
    "oscillator",
    "regulator",
    "driver",
    "rectifier",
    "inverter",
    "charge pump",
    "reference",
    "bias",
}

# Unit pattern for measurement detection
UNIT_PATTERN = re.compile(
    r'\b\d+\.?\d*\s*(mV|V|mA|A|µA|uA|kΩ|Ω|ohm|Hz|kHz|MHz|GHz|pF|nF|µF|uF|mF|F|dB|ppm|ppb)\b',
    re.IGNORECASE
)


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_node_id(node_type: str, name: str) -> str:
    """Create a node ID.
    
    Args:
        node_type: Prefix for node type (design_recipe, component_type, etc.)
        name: Concept name
        
    Returns:
        Normalized node ID
    """
    # Normalize: lowercase, replace spaces with underscores, remove special chars
    normalized = name.lower()
    normalized = re.sub(r'\s+', '_', normalized)
    normalized = re.sub(r'[^\w_]', '', normalized)
    normalized = normalized.strip('_')
    
    return f"{node_type}:{normalized}"


def _looks_like_design_pattern(name: str) -> bool:
    """Heuristic: does the subject look like a design pattern?
    
    Args:
        name: Subject text
        
    Returns:
        True if it contains design pattern keywords
    """
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in DESIGN_PATTERN_KEYWORDS)


def _looks_like_measurement(text: str) -> bool:
    """Heuristic: does the object look like a measurement?
    
    Args:
        text: Object text
        
    Returns:
        True if it contains digits or unit strings
    """
    # Check for unit pattern
    if UNIT_PATTERN.search(text):
        return True
    
    # Check for standalone digits
    if re.search(r'\b\d+\.?\d*\b', text):
        return True
    
    return False


def _create_design_recipe_node(
    name: str,
    source_url: str,
    confidence: float,
    extraction_method: ExtractionMethod,
) -> KGNode:
    """Create a DESIGN_RECIPE node for KG-2.
    
    Args:
        name: Design pattern name
        source_url: Source URL
        confidence: Confidence score
        extraction_method: Extraction method
        
    Returns:
        KGNode with layer=2
    """
    return KGNode(
        id=_make_node_id("design_recipe", name),
        node_type=KGNodeType.DESIGN_RECIPE,
        layer=2,
        label=name,
        properties={},
        source=source_url,
        confidence=confidence,
        extraction_method=extraction_method,
        created_at=_now_iso(),
    )


def _create_component_type_node(
    name: str,
    source_url: str,
    confidence: float,
    extraction_method: ExtractionMethod,
) -> KGNode:
    """Create a COMPONENT_TYPE node for KG-2.
    
    Args:
        name: Component type name
        source_url: Source URL
        confidence: Confidence score
        extraction_method: Extraction method
        
    Returns:
        KGNode with layer=2
    """
    return KGNode(
        id=_make_node_id("component_type", name),
        node_type=KGNodeType.COMPONENT_TYPE,
        layer=2,
        label=name,
        properties={},
        source=source_url,
        confidence=confidence,
        extraction_method=extraction_method,
        created_at=_now_iso(),
    )


def _create_electrical_property_node(
    name: str,
    source_url: str,
    confidence: float,
    extraction_method: ExtractionMethod,
) -> KGNode:
    """Create an ELECTRICAL_PROPERTY node for KG-2.
    
    Args:
        name: Property/measurement name
        source_url: Source URL
        confidence: Confidence score
        extraction_method: Extraction method
        
    Returns:
        KGNode with layer=2
    """
    return KGNode(
        id=_make_node_id("property", name),
        node_type=KGNodeType.ELECTRICAL_PROPERTY,
        layer=2,
        label=name,
        properties={},
        source=source_url,
        confidence=confidence,
        extraction_method=extraction_method,
        created_at=_now_iso(),
    )


def convert_design_triples_to_graph(
    triples: list[Triple],
    pdf_path: Path,
    graph: KnowledgeGraph,
) -> tuple[int, int]:
    """Convert design rule Triples into KG-2 nodes and edges.
    
    For each Triple:
    - Source node: DESIGN_RECIPE if subject looks like a design pattern,
                   COMPONENT_TYPE otherwise
    - Target node: ELECTRICAL_PROPERTY if object looks like a measurement,
                   COMPONENT_TYPE otherwise
    - layer = 2 for all nodes and edges
    
    Args:
        triples: List of design rule Triples
        pdf_path: Path to source PDF
        graph: KnowledgeGraph to add to
        
    Returns:
        Tuple of (nodes_created, edges_created)
    """
    nodes_created = 0
    edges_created = 0
    
    source_url = f"file://{pdf_path}"
    
    for triple in triples:
        try:
            # Determine source node type
            if _looks_like_design_pattern(triple.subject):
                source_node = _create_design_recipe_node(
                    triple.subject,
                    source_url,
                    triple.confidence,
                    triple.extraction_method,
                )
            else:
                source_node = _create_component_type_node(
                    triple.subject,
                    source_url,
                    triple.confidence,
                    triple.extraction_method,
                )
            
            # Determine target node type
            if _looks_like_measurement(triple.object_text):
                target_node = _create_electrical_property_node(
                    triple.object_text,
                    source_url,
                    triple.confidence,
                    triple.extraction_method,
                )
            else:
                target_node = _create_component_type_node(
                    triple.object_text,
                    source_url,
                    triple.confidence,
                    triple.extraction_method,
                )
            
            # Add/update nodes
            graph.add_node(source_node)
            nodes_created += 1
            
            graph.add_node(target_node)
            nodes_created += 1
            
            # Create edge
            edge = KGEdge(
                source_id=source_node.id,
                relation=triple.relation,
                target_id=target_node.id,
                constraints={},
                source_document=triple.source_document,
                confidence=triple.confidence,
                layer=2,
            )
            graph.add_edge(edge)
            edges_created += 1
            
        except Exception as e:
            logger.warning(f"Failed to convert design triple ({triple.subject} → {triple.object_text}): {e}")
            continue
    
    logger.info(f"KG-2: Created {nodes_created} nodes, {edges_created} edges")
    return nodes_created, edges_created
