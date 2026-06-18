"""Semantic search over KnowledgeGraph nodes using FAISS + sentence-transformers.

Builds a vector index over COMPONENT_TYPE, COMPONENT_INSTANCE, and DESIGN_RECIPE
nodes for fast similarity search. Uses FAISS IndexFlatIP (inner product) with
L2-normalized vectors for cosine similarity.

Public API:
    build_search_index(graph, index_path, config) -> int
    search_components(query, graph, index_path, ...) -> list[ComponentSearchResult]

Example:
    >>> from src.knowledge_graph import KnowledgeGraph, build_search_index, search_components
    >>> from src.config import get_config
    >>> graph = KnowledgeGraph.load(Path("graph.graphml"))
    >>> count = build_search_index(graph, Path("index.faiss"), config)
    >>> results = search_components("3.3V LDO regulator", graph, Path("index.faiss"), config=config)
    >>> for r in results[:3]:
    ...     print(f"{r.node.label}: {r.similarity_score:.3f}")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

from src.schemas.kg import ComponentSearchResult, KGNode, KGNodeType

if TYPE_CHECKING:
    from src.config import Config
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Optional dependencies - mocked in tests if not available
try:
    import faiss
except ImportError:
    faiss = None  # type: ignore

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

# Node types eligible for semantic indexing
_INDEXED_NODE_TYPES = {
    KGNodeType.COMPONENT_TYPE,
    KGNodeType.COMPONENT_INSTANCE,
    KGNodeType.DESIGN_RECIPE,
}

# Embedding model configuration
_EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_EMBEDDING_DIMENSION = 384

_embedding_model: Any = None
_index_cache: dict[str, dict[str, Any]] = {}


def _get_embedding_model(config: Config) -> Any:
    """Load sentence-transformers embedding model (lazy, cached per process)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError(
            "sentence-transformers is required for semantic search. "
            "Install with: pip install sentence-transformers"
        ) from e

    # Use a module-level cache to avoid reloading
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model: {_EMBEDDING_MODEL_NAME}")
        _embedding_model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
    return _embedding_model


def _encode_node(node: KGNode) -> str:
    """Encode node to searchable text representation."""
    # Include label, type, and properties for rich embeddings
    text_parts = [node.label, node.node_type.value]
    if node.properties:
        # Serialize properties as additional context
        props_str = json.dumps(node.properties, sort_keys=True, default=str)
        text_parts.append(props_str)
    return " ".join(text_parts)


def _load_index_with_meta(
    index_path: Path,
) -> tuple[Any, list[str], dict[str, Any] | None] | tuple[None, None, None]:
    """Load FAISS index, node_id mapping, and metadata. Returns (index, node_ids, meta) or Nones."""
    if faiss is None:
        raise ImportError(
            "faiss-cpu is required for semantic search. "
            "Install with: pip install faiss-cpu"
        )

    if not index_path.exists():
        return None, None, None

    sidecar_path = index_path.with_suffix(".json")
    meta_path = index_path.with_suffix(".meta")

    if not sidecar_path.exists():
        logger.warning(f"Index sidecar missing: {sidecar_path}")
        return None, None, None

    try:
        index = faiss.read_index(str(index_path))
        with open(sidecar_path, "r", encoding="utf-8") as f:
            node_ids = cast(list[str], json.load(f))
        meta: dict[str, Any] | None = None
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = cast(dict[str, Any], json.load(f))
        return index, node_ids, meta
    except Exception as e:
        logger.warning(f"Failed to load index from {index_path}: {e}")
        return None, None, None


def _save_index_with_meta(
    index: Any,
    node_ids: list[str],
    meta: dict[str, Any],
    index_path: Path,
) -> None:
    """Save FAISS index, node_id mapping, and metadata."""
    if faiss is None:
        raise ImportError("faiss-cpu is required")

    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))

    sidecar_path = index_path.with_suffix(".json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(node_ids, f)

    meta_path = index_path.with_suffix(".meta")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f)

    logger.info(f"Saved index with {len(node_ids)} nodes to {index_path}")


def _is_index_stale(meta: Optional[dict[str, Any]], graph: KnowledgeGraph) -> bool:
    """Check if index metadata differs from current graph stats."""
    if meta is None:
        return True
    current_stats = graph.stats()
    indexed_count = int(meta.get("node_count", 0))
    current_count = int(current_stats.get("node_count", 0))
    return indexed_count != current_count


def _find_matching_properties(node: KGNode, query: str) -> list[str]:
    """Identify which node property values appear in the query string."""
    query_lower = query.lower()
    matches = []
    for prop_name, prop_value in node.properties.items():
        # Check if property value (as string) appears in query
        value_str = str(prop_value).lower()
        if value_str in query_lower or value_str.replace(" ", "") in query_lower.replace(" ", ""):
            matches.append(prop_name)
        # Also check if property name itself is semantically relevant
        # (e.g., "output_voltage" mentioned in query context)
        name_parts = prop_name.replace("_", " ").lower()
        if any(part in query_lower for part in name_parts.split() if len(part) > 3):
            # Additional check: ensure the property value is also somewhat present
            # This avoids false positives like matching "type" on "prototype"
            pass  # Only value matching for now, can be extended
    return matches


def build_search_index(
    graph: KnowledgeGraph,
    index_path: Path,
    config: Config,
) -> int:
    """Build FAISS index over COMPONENT_TYPE, COMPONENT_INSTANCE, DESIGN_RECIPE nodes.

    Saves index + node_id mapping (.bin + .json sidecar) + metadata (.meta).
    The metadata includes graph stats for staleness detection.

    Args:
        graph: KnowledgeGraph containing nodes to index
        index_path: Path to save the FAISS index (typically .faiss extension)
        config: Application configuration

    Returns:
        Count of indexed nodes

    Raises:
        ImportError: If sentence-transformers or faiss-cpu not installed

    Example:
        >>> count = build_search_index(graph, Path("output/kg_index.faiss"), config)
        >>> print(f"Indexed {count} nodes")
        Indexed 42 nodes
    """
    if faiss is None or np is None:
        raise ImportError(
            "faiss-cpu and numpy are required for semantic search. "
            "Install with: pip install faiss-cpu numpy"
        )

    # Collect eligible nodes
    nodes_to_index: list[KGNode] = []
    for node_type in _INDEXED_NODE_TYPES:
        nodes_to_index.extend(graph.find_nodes_by_type(node_type))

    if not nodes_to_index:
        logger.warning("No eligible nodes found for indexing")
        return 0

    # Encode nodes to text
    texts = [_encode_node(node) for node in nodes_to_index]
    node_ids = [node.id for node in nodes_to_index]

    # Generate embeddings
    model = _get_embedding_model(config)
    logger.info(f"Encoding {len(texts)} nodes...")
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    # Ensure float32 and L2 normalization for cosine similarity via inner product
    embeddings = embeddings.astype("float32")
    faiss.normalize_L2(embeddings)

    # Build FAISS index (inner product = cosine on normalized vectors)
    index = faiss.IndexFlatIP(_EMBEDDING_DIMENSION)
    index.add(embeddings)

    # Save with metadata for staleness detection
    meta = {
        "node_count": graph.stats().get("node_count", 0),
        "indexed_count": len(nodes_to_index),
        "model": _EMBEDDING_MODEL_NAME,
        "dimension": _EMBEDDING_DIMENSION,
    }
    _save_index_with_meta(index, node_ids, meta, index_path)

    logger.info(f"Built index with {len(nodes_to_index)} nodes")
    return len(nodes_to_index)


# Module-level cache for loaded index
def _get_cached_index(
    index_path: Path, graph: KnowledgeGraph, config: Config
) -> tuple[Any, list[str]]:
    """Get cached index or load from disk. Rebuilds if stale or missing."""
    global _index_cache
    cache_key = str(index_path.resolve())

    # Check if we have a valid cached index
    if cache_key in _index_cache:
        cached = _index_cache[cache_key]
        # Verify not stale
        if not _is_index_stale(cached.get("meta"), graph):
            return cached["index"], cast(list[str], cached["node_ids"])

    # Load from disk or rebuild
    index, node_ids, meta = _load_index_with_meta(index_path)

    if index is None or _is_index_stale(meta, graph):
        logger.info("Index missing or stale, rebuilding...")
        build_search_index(graph, index_path, config)
        index, node_ids, meta = _load_index_with_meta(index_path)

    if index is None or node_ids is None:
        raise RuntimeError(f"Failed to build or load index at {index_path}")

    # Cache for subsequent calls
    _index_cache[cache_key] = {
        "index": index,
        "node_ids": node_ids,
        "meta": meta,
    }

    return index, node_ids


def search_components(
    query: str,
    graph: KnowledgeGraph,
    index_path: Path,
    component_type_filter: Optional[str] = None,
    max_results: int = 10,
    config: Optional[Config] = None,
) -> list[ComponentSearchResult]:
    """Semantic search over indexed nodes using FAISS.

    Loads index from index_path (cached after first load). Automatically rebuilds
    if index is stale (graph node count changed) or missing.

    Args:
        query: Natural language search query (e.g., "3.3V LDO regulator")
        graph: KnowledgeGraph for node retrieval
        index_path: Path to FAISS index file
        component_type_filter: Optional filter by node_type.value or
            node.properties["component_type"]
        max_results: Maximum number of results to return (default 10)
        config: Application configuration (required for model loading)

    Returns:
        List of ComponentSearchResult ordered by similarity_score descending.
        Returns empty list on any failure (never raises).

    Example:
        >>> results = search_components(
        ...     "low noise amplifier 2.4GHz",
        ...     graph,
        ...     Path("output/kg_index.faiss"),
        ...     component_type_filter="amplifier",
        ...     max_results=5,
        ...     config=config,
        ... )
        >>> for r in results:
        ...     print(f"{r.node.label}: {r.similarity_score:.3f}")
    """
    if config is None:
        logger.error("search_components requires config parameter")
        return []

    if faiss is None or np is None:
        logger.error("FAISS/numpy not available")
        return []

    try:
        # Load or build index (handles staleness check internally)
        index, node_ids = _get_cached_index(index_path, graph, config)

        # Encode query
        model = _get_embedding_model(config)
        query_embedding = model.encode([query], convert_to_numpy=True)
        query_embedding = query_embedding.astype("float32")
        faiss.normalize_L2(query_embedding)

        # Search (get more than max_results to allow for filtering)
        search_k = min(len(node_ids), max_results * 3) if component_type_filter else min(len(node_ids), max_results)
        search_k = max(search_k, max_results)  # Ensure at least max_results candidates

        distances, indices = index.search(query_embedding, search_k)

        # Build results
        results: list[ComponentSearchResult] = []
        for idx, score in zip(indices[0], distances[0]):
            if idx < 0 or idx >= len(node_ids):
                continue

            node_id = node_ids[idx]
            node = graph.get_node(node_id)
            if node is None:
                continue

            # Apply component type filter if specified
            if component_type_filter:
                node_type_matches = node.node_type.value == component_type_filter
                prop_matches = node.properties.get("component_type") == component_type_filter
                if not (node_type_matches or prop_matches):
                    continue

            # Find matching properties
            matching_props = _find_matching_properties(node, query)

            results.append(
                ComponentSearchResult(
                    node=node,
                    similarity_score=float(score),  # FAISS inner product (cosine on normalized vectors)
                    matching_properties=matching_props,
                )
            )

            if len(results) >= max_results:
                break

        # Sort by similarity score descending (FAISS already returns sorted, but filter may reorder)
        results.sort(key=lambda r: r.similarity_score, reverse=True)

        logger.debug(f"Search for '{query}' returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Search failed for query '{query}': {e}", exc_info=True)
        return []
