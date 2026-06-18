"""Triple extraction orchestration module.

Extracts (subject, relation, object) triples from engineering text and maps
them to the KGRelation vocabulary. Uses spaCy first (fast, deterministic),
then falls back to Qwen2.5-7B for ambiguous sentences.

Public API:
    extract_triples(text, source_document, source_url, config) -> list[Triple]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.knowledge_graph.ingestion._llm_extractor import (
    extract_with_llm,
    should_use_llm,
)
from src.knowledge_graph.ingestion._schemas import Triple
from src.knowledge_graph.ingestion._spacy_extractor import extract_with_spacy

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Default minimum confidence threshold for triples
DEFAULT_TRIPLE_MIN_CONFIDENCE = 0.65


def _get_confidence_threshold(config: Config) -> float:
    """Get the minimum confidence threshold from config.

    Args:
        config: Application configuration

    Returns:
        Minimum confidence threshold for accepting triples
    """
    try:
        thresholds = getattr(config, "confidence_thresholds", {})
        if isinstance(thresholds, dict):
            value = thresholds.get("triple_min", DEFAULT_TRIPLE_MIN_CONFIDENCE)
            return float(value)
    except (AttributeError, TypeError):
        pass

    return DEFAULT_TRIPLE_MIN_CONFIDENCE


def extract_triples(
    text: str,
    source_document: str,
    source_url: str,
    config: Config,
) -> list[Triple]:
    """Extract engineering knowledge triples from plain text.

    Runs spaCy first (fast, deterministic). For sentences where spaCy
    cannot confidently assign a KGRelation, falls back to Qwen2.5-7B.
    Filters out triples with confidence < config.confidence_thresholds["triple_min"]
    (default 0.65).
    Never raises — returns empty list on total failure.

    Args:
        text: Source text to extract triples from
        source_document: Document identifier (e.g., filename)
        source_url: URL or path to the source document
        config: Application configuration

    Returns:
        List of extracted Triple objects, filtered by confidence threshold.
        Returns empty list if extraction fails completely or no triples found.

    Example:
        >>> from src.knowledge_graph.ingestion import extract_triples
        >>> from src.config import get_config
        >>> config = get_config()
        >>> text = "A capacitor requires a voltage rating of at least 10V."
        >>> triples = extract_triples(text, "datasheet.pdf", "file:///docs/datasheet.pdf", config)
        >>> len(triples)
        1
        >>> triples[0].relation
        <KGRelation.REQUIRES: 'requires'>
    """
    if not text or not text.strip():
        logger.debug("Empty text provided, returning empty list")
        return []

    # Get confidence threshold
    min_confidence = _get_confidence_threshold(config)
    logger.info(
        f"Extracting triples from {source_document} (threshold: {min_confidence})"
    )

    all_triples: list[Triple] = []

    try:
        # Step 1: spaCy extraction (fast, deterministic)
        spacy_triples, pending_llm = extract_with_spacy(
            text,
            source_document,
            source_url,
            config,
        )
        logger.info(f"spaCy extracted {len(spacy_triples)} triples")

        # Filter spaCy triples by confidence
        filtered_spacy = [t for t in spacy_triples if t.confidence >= min_confidence]
        skipped_spacy = len(spacy_triples) - len(filtered_spacy)
        if skipped_spacy > 0:
            logger.debug(f"Filtered {skipped_spacy} spaCy triples below threshold")

        all_triples.extend(filtered_spacy)

        # Step 2: LLM fallback for pending sentences
        if pending_llm and should_use_llm(len(spacy_triples), len(pending_llm)):
            llm_triples = extract_with_llm(
                pending_llm,
                source_document,
                source_url,
                config,
            )
            logger.info(f"LLM extracted {len(llm_triples)} triples")

            # Filter LLM triples by confidence
            filtered_llm = [t for t in llm_triples if t.confidence >= min_confidence]
            skipped_llm = len(llm_triples) - len(filtered_llm)
            if skipped_llm > 0:
                logger.debug(f"Filtered {skipped_llm} LLM triples below threshold")

            all_triples.extend(filtered_llm)

        logger.info(
            f"Total triples extracted: {len(all_triples)} "
            f"(spaCy: {len(filtered_spacy)}, LLM: {len(all_triples) - len(filtered_spacy)})"
        )

    except Exception as e:
        logger.error(f"Triple extraction failed: {e}")
        # Never raise — return empty list on total failure
        return []

    return all_triples
