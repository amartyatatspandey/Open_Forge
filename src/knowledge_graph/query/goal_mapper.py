"""Goal mapper — converts an intent goal string to KG start nodes.

Applied in order, stopping at first strategy that returns results:
  Strategy 1: exact label match (case-insensitive)
  Strategy 2: all goal words present in node label
  Strategy 3: any goal word (len > 3) present — top 5 by match count
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.schemas.kg import KGNode, KGNodeType

if TYPE_CHECKING:
    from src.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Only these node types qualify as traversal start nodes
_START_NODE_TYPES = (KGNodeType.COMPONENT_TYPE, KGNodeType.DESIGN_RECIPE)


def _goal_words(goal: str) -> list[str]:
    """Split goal into deduped words using both '_' and ' ' as separators."""
    words: list[str] = []
    seen: set[str] = set()
    for part in goal.replace("_", " ").split():
        w = part.lower()
        if w not in seen:
            seen.add(w)
            words.append(w)
    return words


def map_goal_to_nodes(goal: str, graph: KnowledgeGraph) -> list[KGNode]:
    """Find KG start nodes for a goal string.

    Only COMPONENT_TYPE and DESIGN_RECIPE nodes qualify as start nodes.

    Three strategies applied in order; returns at first hit:
    - Strategy 1: exact label match (case-insensitive)
    - Strategy 2: all goal words present in node label
    - Strategy 3: any word (len > 3) present — top 5 by descending match count

    Returns [] and logs WARNING if all strategies yield nothing.

    Args:
        goal: Design goal from IntentDict (e.g. "patch_antenna", "5V buck converter")
        graph: KnowledgeGraph to search

    Returns:
        List of KGNode start nodes; may be empty.
    """
    candidates: list[KGNode] = []
    for node_type in _START_NODE_TYPES:
        candidates.extend(graph.find_nodes_by_type(node_type))

    if not candidates:
        logger.warning(f"No COMPONENT_TYPE or DESIGN_RECIPE nodes in graph for goal: {goal!r}")
        return []

    goal_lower = goal.lower()
    words = _goal_words(goal)

    # ── Strategy 1: exact label match ────────────────────────────────────────
    exact = [n for n in candidates if n.label.lower() == goal_lower]
    if exact:
        logger.debug(f"Goal {goal!r}: Strategy 1 matched {len(exact)} node(s)")
        return exact

    # ── Strategy 2: all words present ────────────────────────────────────────
    all_words = [
        n for n in candidates
        if all(w in n.label.lower() for w in words)
    ]
    if all_words:
        logger.debug(f"Goal {goal!r}: Strategy 2 matched {len(all_words)} node(s)")
        return all_words

    # ── Strategy 3: any word (len > 3) present, ranked, top 5 ───────────────
    significant_words = [w for w in words if len(w) > 3]
    if significant_words:
        scored: list[tuple[int, KGNode]] = []
        for n in candidates:
            label_lower = n.label.lower()
            count = sum(1 for w in significant_words if w in label_lower)
            if count > 0:
                scored.append((count, n))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            top5 = [n for _, n in scored[:5]]
            logger.debug(
                f"Goal {goal!r}: Strategy 3 matched {len(scored)} node(s), returning top {len(top5)}"
            )
            return top5

    logger.warning(f"No KG nodes found for goal: {goal!r}")
    return []
