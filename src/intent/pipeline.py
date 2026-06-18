"""Team C intent-to-BOM pipeline orchestration."""

from __future__ import annotations

import logging

from src.bom.generator import generate_bom
from src.bom.validator import validate_bom
from src.config import Config
from src.intent.parser import parse_intent
from src.knowledge_graph import query_graph
from src.knowledge_graph.graph import KnowledgeGraph
from src.review.queue import enqueue_bom
from src.schemas.intent import DesignMethodology, IntentDict, ValidatedBOM
from src.schemas.kg import DesignSubgraph

logger = logging.getLogger(__name__)


def run_intent_pipeline(
    prompt: str,
    graph: KnowledgeGraph,
    config: Config,
) -> tuple[IntentDict, ValidatedBOM]:
    """
    Full Team C pipeline: prompt -> IntentDict -> KG query -> ValidatedBOM.
    Never raises. Returns review_required=True BOM on any internal failure.
    """
    try:
        intent = parse_intent(prompt, config)

        if intent.clarification_required:
            logger.warning(f"Clarification required for prompt: {prompt!r}")
            empty_bom = _empty_bom(intent)
            return intent, empty_bom

        subgraph = query_graph(intent, graph, config)
        bom = generate_bom(subgraph, intent, config)
        validated_bom = validate_bom(bom, config)

        if validated_bom.review_required:
            enqueue_bom(validated_bom, config)

        return intent, validated_bom

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        fallback_intent = IntentDict(
            goal="unknown",
            application="unknown",
            design_methodology=DesignMethodology.STANDARD_SMD,
            board_type="standard_SMD",
            raw_prompt=prompt,
            clarification_required=True,
        )
        return fallback_intent, _empty_bom(fallback_intent)


def _empty_bom(intent: IntentDict) -> ValidatedBOM:
    import uuid
    from datetime import datetime

    return ValidatedBOM(
        design_id=str(uuid.uuid4()),
        intent=intent,
        components=[],
        total_confidence=0.0,
        review_required=True,
        created_at=datetime.utcnow().isoformat() + "Z",
    )
