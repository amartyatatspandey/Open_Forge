"""KG-2/KG-4 ingestion package for application note PDFs.

Downloads TI/ADI application note PDFs and ingests them into:
- KG-2 (design recipes) for design rules
- KG-4 (placement rules) for spatial constraints

Public API:
    scrape_app_notes(sources_config, output_dir, config) -> list[Path]
    ingest_app_note(pdf_path, graph, config) -> IngestionResult

Example:
    >>> from pathlib import Path
    >>> from src.knowledge_graph import KnowledgeGraph
    >>> from src.config import get_config
    >>> 
    >>> config = get_config()
    >>> graph = KnowledgeGraph()
    >>> 
    >>> # Download PDFs
    >>> pdf_paths = scrape_app_notes(
    ...     Path("configs/sources.yaml"),
    ...     Path("data/appnotes"),
    ...     config
    ... )
    >>> 
    >>> # Ingest into graph
    >>> for pdf_path in pdf_paths:
    ...     result = ingest_app_note(pdf_path, graph, config)
    ...     print(f"{result.source_document}: {result.nodes_created} nodes")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.knowledge_graph.ingestion._schemas import IngestionResult
from src.knowledge_graph.ingestion.kg2_appnotes.kg2_graph_builder import (
    convert_design_triples_to_graph,
)
from src.knowledge_graph.ingestion.kg2_appnotes.kg4_graph_builder import (
    convert_placement_constraints_to_graph,
)
from src.knowledge_graph.ingestion.kg2_appnotes.prose_extractor import (
    extract_from_pdf,
)
from src.knowledge_graph.ingestion.kg2_appnotes.scraper import (
    scrape_app_notes_from_config,
)

if TYPE_CHECKING:
    from src.config import Config
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


def scrape_app_notes(
    sources_config: Path,
    output_dir: Path,
    config: Config,
) -> list[Path]:
    """Download app note PDFs listed in sources.yaml config.
    
    Skips PDFs already downloaded (checks by filename).
    Verifies PDF headers after download.
    
    Args:
        sources_config: Path to sources.yaml config file
        output_dir: Directory to save downloaded PDFs
        config: Application configuration
        
    Returns:
        List of local PDF paths successfully downloaded
        
    Example:
        >>> from pathlib import Path
        >>> from src.config import get_config
        >>> config = get_config()
        >>> 
        >>> paths = scrape_app_notes(
        ...     Path("configs/sources.yaml"),
        ...     Path("data/appnotes"),
        ...     config
        ... )
        >>> print(f"Downloaded {len(paths)} app notes")
        Downloaded 3 app notes
    """
    return scrape_app_notes_from_config(sources_config, output_dir)


def ingest_app_note(
    pdf_path: Path,
    graph: KnowledgeGraph,
    config: Config,
) -> IngestionResult:
    """Ingest one app note PDF into KG-2 and KG-4.
    
    Pass 1: Run prose extraction on text → design recipe nodes (KG-2)
    Pass 2: Run placement extraction on text → placement rule nodes (KG-4)
    
    Args:
        pdf_path: Path to app note PDF
        graph: KnowledgeGraph to add to
        config: Application configuration
        
    Returns:
        IngestionResult with counts for both KG-2 and KG-4
        
    Example:
        >>> from pathlib import Path
        >>> from src.knowledge_graph import KnowledgeGraph
        >>> from src.config import get_config
        >>> 
        >>> graph = KnowledgeGraph()
        >>> config = get_config()
        >>> 
        >>> result = ingest_app_note(
        ...     Path("data/appnotes/TI_SLVA477B_BuckConverterDesign.pdf"),
        ...     graph,
        ...     config
        ... )
        >>> print(f"Nodes: {result.nodes_created}, Edges: {result.edges_created}")
    """
    result = IngestionResult(
        source_document=pdf_path.name,
    )
    
    logger.info(f"Ingesting app note: {pdf_path.name}")
    
    try:
        # Extract both types of rules
        design_triples, placement_constraints = extract_from_pdf(pdf_path, config)
        
        # Pass 1: Convert design rules to KG-2
        kg2_nodes, kg2_edges = convert_design_triples_to_graph(
            design_triples,
            pdf_path,
            graph,
        )
        
        # Pass 2: Convert placement constraints to KG-4
        kg4_nodes, kg4_edges = convert_placement_constraints_to_graph(
            placement_constraints,
            pdf_path,
            graph,
        )
        
        # Aggregate results
        result.nodes_created = kg2_nodes + kg4_nodes
        result.edges_created = kg2_edges + kg4_edges
        result.triples_extracted = len(design_triples) + len(placement_constraints)
        result.success = True
        
        logger.info(
            f"Ingested {pdf_path.name}: "
            f"KG-2: {kg2_nodes} nodes, {kg2_edges} edges; "
            f"KG-4: {kg4_nodes} nodes, {kg4_edges} edges"
        )
        
    except Exception as e:
        error_msg = f"Failed to ingest {pdf_path.name}: {e}"
        logger.error(error_msg)
        result.errors.append(error_msg)
        result.success = False
    
    return result


__all__ = ["scrape_app_notes", "ingest_app_note", "IngestionResult"]
