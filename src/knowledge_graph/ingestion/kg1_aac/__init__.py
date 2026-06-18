"""All About Circuits KG-1 ingestion package.

Scrapes AAC textbook chapters and ingests physics concepts into KG-1
(the physics layer) of the KnowledgeGraph.

Public API:
    scrape_aac_chapters(volumes, output_dir, config) -> list[ScrapedChapter]
    ingest_aac_into_graph(chapters, graph, config) -> list[IngestionResult]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src.knowledge_graph.ingestion._schemas import (
    IngestionResult,
    ScrapedChapter,
)
from src.knowledge_graph.ingestion.kg1_aac.graph_builder import (
    convert_triples_to_graph,
)
from src.knowledge_graph.ingestion.kg1_aac.scraper import (
    IN_SCOPE_VOLUMES,
    scrape_chapter,
    scrape_volume,
)

if TYPE_CHECKING:
    from src.config import Config
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


def scrape_aac_chapters(
    volumes: list[int],
    output_dir: Path,
    config: Config,
) -> list[ScrapedChapter]:
    """Scrape All About Circuits textbook chapters for given volumes.

    Volumes 1, 2, 3, 5 are in scope (Vol 4 is not relevant).
    Stores HTML + content hash in output_dir for cache checking.
    Skips chapters where content hash is unchanged from last run.
    Never raises — logs failures, continues to next chapter.

    Args:
        volumes: List of volume numbers to scrape (1, 2, 3, 5)
        output_dir: Directory to store cached HTML and hash files
        config: Application configuration

    Returns:
        List of ScrapedChapter objects with cleaned text content

    Example:
        >>> from pathlib import Path
        >>> from src.config import get_config
        >>> config = get_config()
        >>> chapters = scrape_aac_chapters([1, 2], Path("cache"), config)
        >>> len(chapters)
        15
    """
    all_chapters: list[ScrapedChapter] = []

    # Filter to in-scope volumes
    volumes_to_scrape = [v for v in volumes if v in IN_SCOPE_VOLUMES]
    skipped_volumes = [v for v in volumes if v not in IN_SCOPE_VOLUMES]

    for vol in skipped_volumes:
        logger.warning(f"Volume {vol} not in scope (1, 2, 3, 5), skipping")

    logger.info(f"Scraping AAC volumes: {volumes_to_scrape}")

    for volume in volumes_to_scrape:
        try:
            chapters, errors = scrape_volume(volume, output_dir)
            all_chapters.extend(chapters)

            if errors:
                for error in errors:
                    logger.warning(f"Volume {volume} error: {error}")

        except Exception as e:
            logger.error(f"Failed to scrape volume {volume}: {e}")
            # Continue to next volume

    logger.info(f"Total chapters scraped: {len(all_chapters)}")
    return all_chapters


def ingest_aac_into_graph(
    chapters: list[ScrapedChapter],
    graph: KnowledgeGraph,
    config: Config,
) -> list[IngestionResult]:
    """Convert scraped AAC chapters into KG-1 PhysicsConcept nodes and edges.

    Calls triple_extractor.extract_triples() for each chapter's text.
    Converts each Triple into KGNode + KGEdge in the graph.
    Returns one IngestionResult per chapter.

    Args:
        chapters: List of ScrapedChapter objects to ingest
        graph: KnowledgeGraph to add nodes/edges to
        config: Application configuration

    Returns:
        List of IngestionResult objects, one per chapter

    Example:
        >>> from src.knowledge_graph import KnowledgeGraph
        >>> from src.config import get_config
        >>> graph = KnowledgeGraph()
        >>> config = get_config()
        >>> chapters = scrape_aac_chapters([1], Path("cache"), config)
        >>> results = ingest_aac_into_graph(chapters, graph, config)
        >>> sum(r.triples_extracted for r in results)
        42
    """
    results: list[IngestionResult] = []

    if not chapters:
        logger.warning("No chapters to ingest")
        return results

    logger.info(f"Ingesting {len(chapters)} chapters into graph")

    for chapter in chapters:
        try:
            # Extract triples from chapter text
            from src.knowledge_graph.ingestion import extract_triples

            triples = extract_triples(
                text=chapter.text,
                source_document=f"AAC Vol {chapter.volume} Ch {chapter.chapter_number}",
                source_url=chapter.url,
                config=config,
            )

            if not triples:
                # Create result with warning
                result = IngestionResult(
                    source_document=f"AAC Vol {chapter.volume}: {chapter.chapter_title}",
                    errors=["No triples extracted from chapter"],
                    success=False,
                )
                results.append(result)
                logger.warning(f"No triples from {chapter.chapter_title}")
                continue

            # Convert triples to graph nodes and edges
            result = convert_triples_to_graph(
                triples=triples,
                volume=chapter.volume,
                chapter_title=chapter.chapter_title,
                graph=graph,
            )

            results.append(result)

        except Exception as e:
            logger.error(f"Failed to ingest chapter {chapter.chapter_title}: {e}")
            # Continue to next chapter
            result = IngestionResult(
                source_document=f"AAC Vol {chapter.volume}: {chapter.chapter_title}",
                errors=[str(e)],
                success=False,
            )
            results.append(result)

    logger.info(f"Ingested {len(results)} chapters into graph")
    return results


__all__ = ["scrape_aac_chapters", "ingest_aac_into_graph", "ScrapedChapter"]
