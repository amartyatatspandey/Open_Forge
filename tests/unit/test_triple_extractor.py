"""Unit tests for src/knowledge_graph/ingestion/.

Tests triple extraction including spaCy-based extraction, verb mapping,
LLM fallback, and orchestration.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.knowledge_graph.ingestion import extract_triples
from src.knowledge_graph.ingestion._schemas import Triple
from src.knowledge_graph.ingestion._verb_mapper import VERB_TO_RELATION, map_verb
from src.schemas.datasheet import ExtractionMethod
from src.schemas.kg import KGRelation


# =============================================================================
# Verb Mapper Tests
# =============================================================================


class TestVerbMapper:
    """Tests for verb phrase to KGRelation mapping."""

    def test_requires_family_mappings(self) -> None:
        """Test REQUIRES family verb mappings."""
        assert map_verb("requires") == KGRelation.REQUIRES
        assert map_verb("require") == KGRelation.REQUIRES
        assert map_verb("needs") == KGRelation.REQUIRES
        assert map_verb("need") == KGRelation.REQUIRES
        assert map_verb("must have") == KGRelation.REQUIRES
        assert map_verb("depend on") == KGRelation.REQUIRES

    def test_uses_family_mappings(self) -> None:
        """Test USES family verb mappings."""
        assert map_verb("uses") == KGRelation.USES
        assert map_verb("use") == KGRelation.USES
        assert map_verb("utilizes") == KGRelation.USES
        assert map_verb("employs") == KGRelation.USES

    def test_is_a_family_mappings(self) -> None:
        """Test IS_A family verb mappings."""
        assert map_verb("is a") == KGRelation.IS_A
        assert map_verb("is an") == KGRelation.IS_A
        assert map_verb("is known as") == KGRelation.IS_A
        assert map_verb("refers to") == KGRelation.IS_A

    def test_has_property_family_mappings(self) -> None:
        """Test HAS_PROPERTY family verb mappings."""
        assert map_verb("has") == KGRelation.HAS_PROPERTY
        assert map_verb("have") == KGRelation.HAS_PROPERTY
        assert map_verb("exhibits") == KGRelation.HAS_PROPERTY
        assert map_verb("possesses") == KGRelation.HAS_PROPERTY
        assert map_verb("provides") == KGRelation.HAS_PROPERTY

    def test_connects_to_family_mappings(self) -> None:
        """Test CONNECTS_TO family verb mappings."""
        assert map_verb("connects") == KGRelation.CONNECTS_TO
        assert map_verb("connect") == KGRelation.CONNECTS_TO
        assert map_verb("connects to") == KGRelation.CONNECTS_TO
        assert map_verb("connect to") == KGRelation.CONNECTS_TO
        assert map_verb("links") == KGRelation.CONNECTS_TO
        assert map_verb("wire to") == KGRelation.CONNECTS_TO

    def test_part_of_family_mappings(self) -> None:
        """Test PART_OF family verb mappings."""
        assert map_verb("part of") == KGRelation.PART_OF
        assert map_verb("belongs to") == KGRelation.PART_OF
        assert map_verb("component of") == KGRelation.PART_OF

    def test_incompatible_with_family_mappings(self) -> None:
        """Test INCOMPATIBLE_WITH family verb mappings."""
        assert map_verb("incompatible with") == KGRelation.INCOMPATIBLE_WITH
        assert map_verb("cannot connect") == KGRelation.INCOMPATIBLE_WITH

    def test_map_verb_case_insensitive(self) -> None:
        """Test verb mapping is case-insensitive."""
        assert map_verb("REQUIRES") == KGRelation.REQUIRES
        assert map_verb("Requires") == KGRelation.REQUIRES
        assert map_verb("  ReQuIrEs  ") == KGRelation.REQUIRES

    def test_map_verb_whitespace_stripped(self) -> None:
        """Test verb mapping strips whitespace."""
        assert map_verb("  requires  ") == KGRelation.REQUIRES
        assert map_verb("  uses  ") == KGRelation.USES

    def test_map_verb_unknown_returns_none(self) -> None:
        """Test unknown verb phrase returns None."""
        assert map_verb("unknown verb") is None
        assert map_verb("xyz abc") is None
        assert map_verb("") is None

    def test_map_verb_empty_returns_none(self) -> None:
        """Test empty string returns None."""
        assert map_verb("") is None
        assert map_verb("   ") is None
        assert map_verb(None) is None  # type: ignore


# =============================================================================
# Triple Extraction Tests
# =============================================================================


@pytest.fixture
def mock_config() -> Config:
    """Create mock Config with confidence thresholds."""
    config = MagicMock(spec=Config)
    config.confidence_thresholds = {"triple_min": 0.65}
    return config


class TestExtractTriples:
    """Tests for extract_triples orchestration."""

    def test_empty_text_returns_empty_list(self, mock_config) -> None:
        """Test empty text returns empty list."""
        result = extract_triples("", "doc.pdf", "url", mock_config)
        assert result == []

    def test_whitespace_text_returns_empty_list(self, mock_config) -> None:
        """Test whitespace-only text returns empty list."""
        result = extract_triples("   \n\t  ", "doc.pdf", "url", mock_config)
        assert result == []

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_spacy_extraction_returns_triples(self, mock_spacy, mock_config) -> None:
        """Test 'A capacitor requires a voltage rating' → Triple with relation=REQUIRES."""
        # Mock spaCy returning a triple
        mock_spacy.return_value = (
            [
                Triple(
                    subject="capacitor",
                    relation=KGRelation.REQUIRES,
                    object_text="voltage rating",
                    source_sentence="A capacitor requires a voltage rating.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.80,
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            [],  # No pending LLM
        )

        text = "A capacitor requires a voltage rating."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert len(result) == 1
        assert result[0].subject == "capacitor"
        assert result[0].relation == KGRelation.REQUIRES
        assert result[0].object_text == "voltage rating"
        assert result[0].confidence >= 0.65

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_uses_relation_extraction(self, mock_spacy, mock_config) -> None:
        """Test 'Resistors use the ohm as their unit' → relation=USES."""
        mock_spacy.return_value = (
            [
                Triple(
                    subject="resistors",
                    relation=KGRelation.USES,
                    object_text="ohm",
                    source_sentence="Resistors use the ohm as their unit.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.80,
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            [],
        )

        text = "Resistors use the ohm as their unit."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert len(result) == 1
        assert result[0].relation == KGRelation.USES

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_is_a_relation_extraction(self, mock_spacy, mock_config) -> None:
        """Test 'An inductor is a passive component' → relation=IS_A."""
        mock_spacy.return_value = (
            [
                Triple(
                    subject="inductor",
                    relation=KGRelation.IS_A,
                    object_text="passive component",
                    source_sentence="An inductor is a passive component.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.80,
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            [],
        )

        text = "An inductor is a passive component."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert len(result) == 1
        assert result[0].relation == KGRelation.IS_A

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_has_property_relation_extraction(self, mock_spacy, mock_config) -> None:
        """Test 'The op-amp has high input impedance' → relation=HAS_PROPERTY."""
        mock_spacy.return_value = (
            [
                Triple(
                    subject="op-amp",
                    relation=KGRelation.HAS_PROPERTY,
                    object_text="high input impedance",
                    source_sentence="The op-amp has high input impedance.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.80,
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            [],
        )

        text = "The op-amp has high input impedance."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert len(result) == 1
        assert result[0].relation == KGRelation.HAS_PROPERTY

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_connects_to_relation_extraction(self, mock_spacy, mock_config) -> None:
        """Test 'MOSI connects to SDI' → relation=CONNECTS_TO."""
        mock_spacy.return_value = (
            [
                Triple(
                    subject="MOSI",
                    relation=KGRelation.CONNECTS_TO,
                    object_text="SDI",
                    source_sentence="MOSI connects to SDI.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.80,
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            [],
        )

        text = "MOSI connects to SDI."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert len(result) == 1
        assert result[0].relation == KGRelation.CONNECTS_TO

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_very_short_sentence_not_extracted(self, mock_spacy, mock_config) -> None:
        """Test very short sentence (<8 words) → not extracted."""
        # spaCy would mark short sentences as pending LLM or skip them
        mock_spacy.return_value = (
            [],  # No triples extracted
            ["Short text."],  # Pending LLM
        )

        text = "Short text."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        # Since LLM is not mocked, result should be empty (pending sentences go to LLM but LLM not available)
        assert result == []

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_no_subject_sentence_not_extracted(self, mock_spacy, mock_config) -> None:
        """Test sentence with no subject → not extracted."""
        # spaCy would not find subject, so no triple
        mock_spacy.return_value = (
            [],  # No triples
            ["Is working correctly."],  # Pending LLM
        )

        text = "Is working correctly."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert result == []

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_llm")
    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_llm_only_called_for_unmapped_sentences(
        self, mock_spacy, mock_llm, mock_config
    ) -> None:
        """Mock LLM — verify LLM is only called for sentences spaCy could not map."""
        # spaCy finds one triple, sends one sentence to LLM
        mock_spacy.return_value = (
            [
                Triple(
                    subject="resistor",
                    relation=KGRelation.REQUIRES,
                    object_text="current",
                    source_sentence="A resistor requires current.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.80,
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            ["Unknown verb phrase here."],  # One pending
        )

        # LLM returns a triple for the pending sentence
        mock_llm.return_value = [
            Triple(
                subject="unknown",
                relation=KGRelation.USES,
                object_text="object",
                source_sentence="Unknown verb phrase here.",
                source_document="doc.pdf",
                source_url="url",
                confidence=0.75,
                extraction_method=ExtractionMethod.LLM_FALLBACK,
            )
        ]

        text = "A resistor requires current. Unknown verb phrase here."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        # Verify LLM was called (and only called once for the pending sentence)
        mock_llm.assert_called_once()
        call_args = mock_llm.call_args
        assert call_args[0][0] == ["Unknown verb phrase here."]  # pending sentences

        # Should have both triples
        assert len(result) == 2

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_triple_below_threshold_filtered(self, mock_spacy, mock_config) -> None:
        """Test triple with confidence below threshold is filtered out."""
        mock_spacy.return_value = (
            [
                Triple(
                    subject="test",
                    relation=KGRelation.REQUIRES,
                    object_text="object",
                    source_sentence="Test requires object.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.50,  # Below 0.65 threshold
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            [],
        )

        text = "Test requires object."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert result == []  # Filtered out due to low confidence

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_triple_above_threshold_kept(self, mock_spacy, mock_config) -> None:
        """Test triple with confidence above threshold is kept."""
        mock_spacy.return_value = (
            [
                Triple(
                    subject="test",
                    relation=KGRelation.REQUIRES,
                    object_text="object",
                    source_sentence="Test requires object.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.70,  # Above 0.65 threshold
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            [],
        )

        text = "Test requires object."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert len(result) == 1
        assert result[0].confidence == 0.70

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_extract_triples_returns_empty_when_model_unavailable(
        self, mock_spacy, mock_config
    ) -> None:
        """Test extract_triples returns empty list when model unavailable (never raises)."""
        # spaCy unavailable would return empty triples and pending
        mock_spacy.return_value = (
            [],
            [],
        )

        text = "Some text about electronics."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        # Should return empty list, not raise
        assert result == []

    @patch("src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy")
    def test_extract_triples_uses_config_threshold(self, mock_spacy, mock_config) -> None:
        """Test extract_triples uses config.confidence_thresholds['triple_min']."""
        # Set custom threshold
        mock_config.confidence_thresholds = {"triple_min": 0.75}

        mock_spacy.return_value = (
            [
                Triple(
                    subject="test",
                    relation=KGRelation.REQUIRES,
                    object_text="object",
                    source_sentence="Test requires object.",
                    source_document="doc.pdf",
                    source_url="url",
                    confidence=0.70,  # Below new 0.75 threshold
                    extraction_method=ExtractionMethod.P1_VECTOR,
                )
            ],
            [],
        )

        text = "Test requires object."
        result = extract_triples(text, "doc.pdf", "url", mock_config)

        assert result == []  # Filtered by higher threshold


# =============================================================================
# Triple Schema Tests
# =============================================================================


class TestTripleSchema:
    """Tests for Triple Pydantic model."""

    def test_triple_creation_all_fields(self) -> None:
        """Test Triple creation with all required fields."""
        triple = Triple(
            subject="capacitor",
            relation=KGRelation.REQUIRES,
            object_text="voltage rating",
            source_sentence="A capacitor requires a voltage rating.",
            source_document="doc.pdf",
            source_url="file:///docs/doc.pdf",
            confidence=0.80,
            extraction_method=ExtractionMethod.P1_VECTOR,
        )

        assert triple.subject == "capacitor"
        assert triple.relation == KGRelation.REQUIRES
        assert triple.object_text == "voltage rating"
        assert triple.source_document == "doc.pdf"
        assert triple.confidence == 0.80

    def test_triple_confidence_bounds_validation(self) -> None:
        """Test Triple validates confidence bounds."""
        from pydantic import ValidationError

        # Valid boundaries
        Triple(
            subject="test",
            relation=KGRelation.REQUIRES,
            object_text="object",
            source_sentence="Test.",
            source_document="doc.pdf",
            source_url="url",
            confidence=0.0,
            extraction_method=ExtractionMethod.P1_VECTOR,
        )

        Triple(
            subject="test",
            relation=KGRelation.REQUIRES,
            object_text="object",
            source_sentence="Test.",
            source_document="doc.pdf",
            source_url="url",
            confidence=1.0,
            extraction_method=ExtractionMethod.P1_VECTOR,
        )

        # Invalid: negative confidence
        with pytest.raises(ValidationError):
            Triple(
                subject="test",
                relation=KGRelation.REQUIRES,
                object_text="object",
                source_sentence="Test.",
                source_document="doc.pdf",
                source_url="url",
                confidence=-0.1,
                extraction_method=ExtractionMethod.P1_VECTOR,
            )

        # Invalid: > 1.0 confidence
        with pytest.raises(ValidationError):
            Triple(
                subject="test",
                relation=KGRelation.REQUIRES,
                object_text="object",
                source_sentence="Test.",
                source_document="doc.pdf",
                source_url="url",
                confidence=1.01,
                extraction_method=ExtractionMethod.P1_VECTOR,
            )

    def test_triple_json_round_trip(self) -> None:
        """Test Triple round-trips to/from JSON."""
        original = Triple(
            subject="resistor",
            relation=KGRelation.USES,
            object_text="ohm",
            source_sentence="Resistors use the ohm as their unit.",
            source_document="datasheet.pdf",
            source_url="file:///docs/datasheet.pdf",
            confidence=0.82,
            extraction_method=ExtractionMethod.P1_VECTOR,
        )

        # Serialize
        json_str = original.model_dump_json()

        # Deserialize
        restored = Triple.model_validate_json(json_str)

        assert restored.subject == original.subject
        assert restored.relation == original.relation
        assert restored.object_text == original.object_text
        assert restored.confidence == original.confidence
