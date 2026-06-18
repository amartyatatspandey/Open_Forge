"""LLM-based triple extraction fallback.

Uses Qwen2.5-7B via Instructor to extract triples from sentences
where spaCy could not confidently assign a KGRelation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from src.knowledge_graph.ingestion._schemas import Triple
from src.knowledge_graph.ingestion._verb_mapper import map_verb
from src.schemas.datasheet import ExtractionMethod
from src.schemas.kg import KGRelation

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Minimum confidence threshold for accepting LLM extraction
MIN_LLM_CONFIDENCE = 0.65

# Confidence for LLM extraction
LLM_CONFIDENCE_BASE = 0.72


class LLMTripleOutput(BaseModel):
    """Schema for LLM triple extraction response.

    Instructor-enforced output format for LLM-based triple extraction.
    """

    model_config = {"extra": "forbid"}

    subject: str = Field(
        description="The subject entity of the relationship",
    )
    relation: str = Field(
        description="One of: requires, uses, has_property, connects_to, is_a, part_of, incompatible_with",
    )
    object_text: str = Field(
        description="The object entity of the relationship",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in this extraction (0.0-1.0)",
    )


SYSTEM_PROMPT = """You are an engineering knowledge extraction system.

Extract the engineering relationship from the provided sentence.

Return a structured extraction with:
- subject: The main entity or component being described
- relation: The relationship type (choose from: requires, uses, has_property, connects_to, is_a, part_of, incompatible_with)
- object: The entity related to the subject
- confidence: Your confidence in this extraction (0.0-1.0)

Relation guidelines:
- requires: Subject needs/depends on object to function
- uses: Subject employs/utilizes object
- has_property: Subject possesses/exhibits object as a characteristic
- connects_to: Subject links/interfaces with object
- is_a: Subject is a type/kind of object
- part_of: Subject is a component/constituent of object
- incompatible_with: Subject conflicts with/cannot work with object

Return confidence=0.0 if no clear engineering relationship exists in the sentence.
Be precise and extract only what is explicitly stated in the text."""


def _load_llm(config: Config) -> Optional[object]:
    """Load the Qwen2.5-7B model via Instructor.

    Args:
        config: Application configuration with model paths

    Returns:
        Instructor client or None if model unavailable
    """
    try:
        import instructor
        from openai import OpenAI
    except ImportError:
        logger.warning("instructor or openai not available for LLM extraction")
        return None

    # Placeholder: In production, load Qwen2.5-7B-Instruct
    logger.debug("LLM model loading not implemented in prototype")
    return None


def _map_relation_string(relation_str: str) -> Optional[KGRelation]:
    """Map relation string from LLM to KGRelation.

    Args:
        relation_str: Relation string from LLM

    Returns:
        KGRelation or None if unmappable
    """
    if not relation_str:
        return None

    # Try direct mapping via verb mapper
    relation = map_verb(relation_str)
    if relation is not None:
        return relation

    # Manual mapping for common variations
    mapping = {
        "requires": KGRelation.REQUIRES,
        "uses": KGRelation.USES,
        "has_property": KGRelation.HAS_PROPERTY,
        "connects_to": KGRelation.CONNECTS_TO,
        "is_a": KGRelation.IS_A,
        "part_of": KGRelation.PART_OF,
        "incompatible_with": KGRelation.INCOMPATIBLE_WITH,
    }

    normalized = relation_str.strip().lower().replace(" ", "_")
    return mapping.get(normalized)


def extract_with_llm(
    sentences: list[str],
    source_document: str,
    source_url: str,
    config: Config,
) -> list[Triple]:
    """Extract triples from sentences using LLM.

    Called for sentences where spaCy could not determine a KGRelation.
    Uses Qwen2.5-7B via Instructor to extract subject, relation, object.

    Args:
        sentences: List of sentences needing LLM extraction
        source_document: Document identifier
        source_url: Source document URL/path
        config: Application configuration

    Returns:
        List of extracted Triples (filtered by confidence)
    """
    if not sentences:
        return []

    llm_client = _load_llm(config)
    if llm_client is None:
        logger.warning("LLM unavailable, cannot extract from pending sentences")
        return []

    triples: list[Triple] = []

    # In production, this would batch sentences and call LLM via Instructor
    # For prototype, return empty (LLM not implemented)
    logger.info(f"Would extract {len(sentences)} sentences via LLM")

    # Placeholder: In production, iterate sentences and call LLM
    for sentence in sentences:
        try:
            # This would be the actual LLM call in production:
            # response = instructor_client.chat.completions.create(
            #     model="Qwen2.5-7B-Instruct",
            #     response_model=LLMTripleOutput,
            #     messages=[{"role": "system", "content": SYSTEM_PROMPT},
            #               {"role": "user", "content": sentence}]
            # )

            # For prototype, skip (LLM not available)
            logger.debug(f"LLM extraction placeholder for: {sentence[:50]}...")
            continue

        except Exception as e:
            logger.warning(f"LLM extraction failed for sentence: {e}")
            continue

    return triples


def should_use_llm(triples_from_spacy: int, pending_sentences: int) -> bool:
    """Determine if LLM fallback should be attempted.

    Args:
        triples_from_spacy: Number of triples already extracted by spaCy
        pending_sentences: Number of sentences pending LLM extraction

    Returns:
        True if LLM should be attempted
    """
    # Always attempt LLM if there are pending sentences
    # (assuming LLM is available)
    return pending_sentences > 0
