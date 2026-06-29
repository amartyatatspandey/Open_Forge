"""Team C intent-to-BOM pipeline orchestration."""

from __future__ import annotations

import logging
from typing import Optional

from src.bom.generator import generate_bom
from src.bom.validator import validate_bom
from src.completion import CompletionEngineError, run_completion_engine
from src.config import Config
from src.intent.parser import parse_intent
from src.knowledge_graph import query_graph
from src.knowledge_graph.graph import KnowledgeGraph
from src.retrieval import RetrievalEngine
from src.retrieval.schemas import RetrievalResult
from src.review.queue import enqueue_bom
from src.schemas.intent import (
    DesignMethodology,
    ImprovedIntentDict,
    IntentDict,
    ValidatedBOM,
)

logger = logging.getLogger(__name__)


def _run_stage2(intent: ImprovedIntentDict, config: Config) -> ImprovedIntentDict:
    """
    Run Stage 2 requirement completion engine.
    On CompletionEngineError: log warning, return original intent unchanged.
    Never raises.
    """
    try:
        return run_completion_engine(intent, config)
    except CompletionEngineError as exc:
        logger.warning(
            "Stage 2 completion engine failed — proceeding with Stage 1 output: %s",
            exc,
        )
        return intent
    except Exception as exc:
        logger.warning(
            "Stage 2 unexpected error — proceeding with Stage 1 output: %s",
            exc,
        )
        return intent


def _run_retrieval(intent: ImprovedIntentDict, config: Config) -> Optional[RetrievalResult]:
    """
    Run Stage 2.5 KB retrieval. Returns None if database_url is absent or on any error.
    Never raises.
    """
    database_url = getattr(config, "database_url", None)
    if not database_url:
        logger.info("Stage 2.5: skipping KB retrieval — no database_url configured")
        return None

    try:
        logger.info("Stage 2.5: running KB retrieval")
        engine = RetrievalEngine(db_url=database_url, config=config)
        result = engine.run_retrieval(intent)
        logger.info(
            "Stage 2.5: retrieval complete — %d candidates, %d missing",
            len(result.component_candidates),
            len(result.missing_components),
        )
        return result
    except Exception as exc:
        logger.warning("Stage 2.5 retrieval failed — proceeding without KB results: %s", exc)
        return None


def run_intent_pipeline(
    prompt: str,
    graph: KnowledgeGraph,
    config: Config,
) -> tuple[IntentDict, ValidatedBOM, Optional[RetrievalResult]]:
    """
    Full Team C pipeline: prompt -> IntentDict -> KG query -> ValidatedBOM.
    Never raises. Returns review_required=True BOM on any internal failure.
    """
    try:
        intent = parse_intent(prompt, config)

        if intent.clarification_required:
            logger.warning(f"Clarification required for prompt: {prompt!r}")
            empty_bom = _empty_bom(intent)
            return intent, empty_bom, None

        logger.info("Stage 2: running requirement completion engine")
        intent = _run_stage2(intent, config)
        logger.info(
            "Stage 2: complete — clarification_required=%s",
            intent.clarification_required,
        )

        if intent.clarification_required:
            logger.warning("Stage 2 set clarification_required=True — halting pipeline")
            empty_bom = _empty_bom(intent)
            return intent, empty_bom, None

        logger.info("Stage 2.5: running KB retrieval")
        retrieval_result = _run_retrieval(intent, config)

        subgraph = query_graph(intent, graph, config)
        bom = generate_bom(subgraph, intent, config, retrieval_result=retrieval_result)
        validated_bom = validate_bom(bom, config)

        if validated_bom.review_required:
            enqueue_bom(validated_bom, config)

        return intent, validated_bom, retrieval_result

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        fallback_intent = ImprovedIntentDict(
            goal="unknown",
            application="unknown",
            design_methodology=DesignMethodology.STANDARD_SMD,
            board_type="standard_SMD",
            raw_prompt=prompt,
            clarification_required=True,
        )
        return fallback_intent, _empty_bom(fallback_intent), None


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
