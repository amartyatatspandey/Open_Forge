"""spaCy-based SVO (Subject-Verb-Object) triple extraction.

Uses spaCy dependency parsing to extract subject-verb-object triples
from engineering text sentences.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

from src.knowledge_graph.ingestion._schemas import Triple
from src.knowledge_graph.ingestion._verb_mapper import map_verb
from src.schemas.datasheet import ExtractionMethod

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Confidence for spaCy extraction (deterministic rule-based)
SPACY_CONFIDENCE = 0.80

# Sentence length constraints
MIN_SENTENCE_WORDS = 8
MAX_SENTENCE_WORDS = 60


def _load_spacy_model() -> Optional[Callable[[str], Any]]:
    """Load the spaCy English model.

    Returns:
        spaCy nlp object or None if model unavailable
    """
    try:
        import spacy
        # Load small model - fast, no GPU needed
        return spacy.load("en_core_web_sm")
    except ImportError:
        logger.warning("spaCy not installed, cannot extract triples")
        return None
    except OSError:
        logger.warning("spaCy model 'en_core_web_sm' not found, run: python -m spacy download en_core_web_sm")
        return None


def _extract_verb_phrase(token: Any, doc: Any) -> str:
    """Extract the full verb phrase including auxiliaries and prepositions.

    Args:
        token: The root verb token
        doc: The spaCy doc

    Returns:
        Full verb phrase string
    """
    parts = []

    # Add auxiliary verbs
    for child in token.children:
        if child.dep_ in ("aux", "auxpass"):
            parts.append(child.text)

    # Add main verb
    parts.append(token.text)

    # Add preposition if present (for phrasal verbs like "connects to")
    for child in token.children:
        if child.dep_ == "prep":
            parts.append(child.text)
            break  # Only first preposition

    return " ".join(parts).lower()


def _extract_subject(token: Any) -> Optional[str]:
    """Extract subject from a verb token.

    Args:
        token: The root verb token

    Returns:
        Subject noun phrase or None if not found
    """
    for child in token.children:
        if child.dep_ in ("nsubj", "nsubjpass"):
            # Return the full noun phrase
            return _get_full_noun_phrase(child)
    return None


def _extract_object(token: Any) -> Optional[str]:
    """Extract object from a verb token.

    Args:
        token: The root verb token

    Returns:
        Object noun phrase or None if not found
    """
    for child in token.children:
        if child.dep_ in ("dobj", "pobj", "attr", "oprd"):
            return _get_full_noun_phrase(child)
    return None


def _get_full_noun_phrase(token: Any) -> str:
    """Get the full noun phrase including modifiers.

    Args:
        token: The head noun token

    Returns:
        Full noun phrase string
    """
    # Start with the token itself
    words = [token.text]

    # Add modifiers (adjectives, compound nouns)
    for child in token.children:
        if child.dep_ in ("amod", "compound"):
            if child.i < token.i:
                words.insert(0, child.text)
            else:
                words.append(child.text)

    return " ".join(words)


def _is_valid_sentence(sent: Any) -> Tuple[bool, str]:
    """Check if sentence meets extraction criteria.

    Args:
        sent: spaCy sentence span

    Returns:
        Tuple of (is_valid, reason)
    """
    # Count words (exclude punctuation)
    words = [token for token in sent if not token.is_punct and not token.is_space]
    word_count = len(words)

    if word_count < MIN_SENTENCE_WORDS:
        return False, f"too short ({word_count} words)"

    if word_count > MAX_SENTENCE_WORDS:
        return False, f"too long ({word_count} words)"

    return True, ""


def extract_with_spacy(
    text: str,
    source_document: str,
    source_url: str,
    config: Config,
) -> Tuple[list[Triple], list[str]]:
    """Extract triples from text using spaCy.

    Parses text with spaCy, finds SVO structures, maps verbs to KGRelation.
    Returns confirmed triples + list of sentences needing LLM fallback.

    Args:
        text: Source text to extract from
        source_document: Document identifier
        source_url: Source document URL/path
        config: Application configuration

    Returns:
        Tuple of (extracted_triples, pending_llm_sentences)
    """
    nlp = _load_spacy_model()
    if nlp is None:
        logger.warning("spaCy model unavailable, returning empty")
        return [], []

    triples: list[Triple] = []
    pending_llm: list[str] = []

    try:
        doc = nlp(text)

        for sent in doc.sents:
            sentence_text = sent.text.strip()

            # Check sentence validity
            is_valid, reason = _is_valid_sentence(sent)
            if not is_valid:
                logger.debug(f"Skipping sentence: {reason}")
                continue

            # Find root verb
            root = None
            for token in sent:
                if token.dep_ == "ROOT" and token.pos_ == "VERB":
                    root = token
                    break

            if root is None:
                logger.debug(f"No root verb found in: {sentence_text[:50]}...")
                pending_llm.append(sentence_text)
                continue

            # Extract subject and object
            subject = _extract_subject(root)
            obj = _extract_object(root)

            if subject is None or obj is None:
                logger.debug(f"Missing subject or object in: {sentence_text[:50]}...")
                pending_llm.append(sentence_text)
                continue

            # Extract verb phrase
            verb_phrase = _extract_verb_phrase(root, doc)

            # Map to KGRelation
            relation = map_verb(verb_phrase)

            if relation is None:
                logger.debug(f"No verb mapping for '{verb_phrase}' in: {sentence_text[:50]}...")
                pending_llm.append(sentence_text)
                continue

            # Create triple
            triple = Triple(
                subject=subject,
                relation=relation,
                object_text=obj,
                source_sentence=sentence_text,
                source_document=source_document,
                source_url=source_url,
                confidence=SPACY_CONFIDENCE,
                extraction_method=ExtractionMethod.P1_VECTOR,
            )
            triples.append(triple)
            logger.debug(f"Extracted: {subject} {relation.value} {obj}")

    except Exception as e:
        logger.error(f"spaCy extraction failed: {e}")
        # Return what we have, pending sentences go to LLM

    logger.info(f"spaCy extracted {len(triples)} triples, {len(pending_llm)} pending LLM")
    return triples, pending_llm
