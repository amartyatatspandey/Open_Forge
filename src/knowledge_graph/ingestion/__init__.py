"""Knowledge graph ingestion package.

Extracts (subject, relation, object) triples from engineering text and maps
them to the KGRelation vocabulary. Uses spaCy first (fast, deterministic),
then falls back to Qwen2.5-7B for ambiguous sentences.

Public API:
    extract_triples(text, source_document, source_url, config) -> list[Triple]

Example:
    >>> from src.knowledge_graph.ingestion import extract_triples
    >>> from src.config import get_config
    >>> config = get_config()
    >>> triples = extract_triples(text, "doc.pdf", "url", config)
"""

from __future__ import annotations

from src.knowledge_graph.ingestion._schemas import Triple
from src.knowledge_graph.ingestion.triple_extractor import extract_triples

__all__ = ["extract_triples", "Triple"]
