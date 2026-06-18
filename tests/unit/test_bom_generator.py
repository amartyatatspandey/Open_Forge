"""Tests for the BOM generator package.

Tests generate_bom() and component selection covering various scenarios
including empty subgraphs, component instances, and confidence thresholds.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.bom import generate_bom
from src.schemas.datasheet import ExtractionMethod
from src.schemas.intent import (
    BOMEntry,
    DesignMethodology,
    FrequencySpec,
    IntentDict,
    ValidatedBOM,
)
from src.schemas.kg import DesignSubgraph, KGNode, KGNodeType


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_config():
    """Create a mock Config with BOM thresholds."""
    config = MagicMock()
    config.confidence_thresholds = {
        "bom_total": 0.85,
        "bom_component": 0.75,
        "pin_normalization": 0.70,
    }
    return config


@pytest.fixture
def sample_intent():
    """Create a sample IntentDict for testing."""
    return IntentDict(
        goal="buck_converter",
        frequency=None,
        application="industrial",
        explicit_constraints=["compact"],
        inferred_constraints=["low_power"],
        design_methodology=DesignMethodology.POWER_MANAGEMENT,
        board_type="double_sided_SMD",
        ambiguities=[],
        clarification_required=False,
        raw_prompt="design a buck converter",
    )


def _create_component_type(
    node_id: str,
    label: str,
    confidence: float = 0.9,
    source: str = "test_datasheet.pdf",
) -> KGNode:
    """Helper to create a COMPONENT_TYPE KGNode."""
    return KGNode(
        id=f"component_type:{node_id}",
        node_type=KGNodeType.COMPONENT_TYPE,
        layer=2,
        label=label,
        properties={},
        source=source,
        confidence=confidence,
        extraction_method=ExtractionMethod.MANUAL,
        created_at="2026-01-01T00:00:00Z",
    )


def _create_component_instance(
    node_id: str,
    label: str,
    component_type: str,
    confidence: float = 0.95,
) -> KGNode:
    """Helper to create a COMPONENT_INSTANCE KGNode."""
    return KGNode(
        id=f"component_instance:{node_id}",
        node_type=KGNodeType.COMPONENT_INSTANCE,
        layer=3,
        label=label,
        properties={"component_type": component_type},
        source="test_datasheet.pdf",
        confidence=confidence,
        extraction_method=ExtractionMethod.MANUAL,
        created_at="2026-01-01T00:00:00Z",
    )


def _create_subgraph(
    component_types: list[KGNode],
    component_instances: list[KGNode] | None = None,
    path_confidences: dict[str, float] | None = None,
) -> DesignSubgraph:
    """Helper to create a DesignSubgraph."""
    if component_instances is None:
        component_instances = []
    if path_confidences is None:
        path_confidences = {node.id: node.confidence for node in component_types}
    
    return DesignSubgraph(
        component_types=component_types,
        component_instances=component_instances,
        design_rules=[],
        placement_rules=[],
        routing_hints=[],
        design_methodology="power_management",
        path_confidences=path_confidences,
        query_depth=2,
    )


# =============================================================================
# Test 1: Empty subgraph → ValidatedBOM with empty components, review_required=True
# =============================================================================


def test_empty_subgraph_returns_empty_bom_with_review_required(mock_config, sample_intent):
    """1. Empty subgraph → ValidatedBOM with empty components, review_required=True."""
    # Create empty subgraph
    empty_subgraph = DesignSubgraph(
        component_types=[],
        component_instances=[],
        design_rules=[],
        placement_rules=[],
        routing_hints=[],
        design_methodology="test",
        path_confidences={},
        query_depth=0,
    )
    
    bom = generate_bom(empty_subgraph, sample_intent, mock_config)
    
    assert isinstance(bom, ValidatedBOM)
    assert bom.components == []
    assert bom.review_required is True
    assert bom.total_confidence == 0.0


# =============================================================================
# Test 2: Subgraph with 2 COMPONENT_TYPE nodes → BOM with 2 entries
# =============================================================================


def test_subgraph_with_two_components_generates_two_entries(mock_config, sample_intent):
    """2. Subgraph with 2 COMPONENT_TYPE nodes → BOM with 2 entries."""
    regulator = _create_component_type("regulator", "ldo_regulator", confidence=0.9)
    capacitor = _create_component_type("capacitor", "input_capacitor", confidence=0.85)
    
    subgraph = _create_subgraph(
        component_types=[regulator, capacitor],
        path_confidences={
            regulator.id: 0.9,
            capacitor.id: 0.85,
        }
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    assert len(bom.components) == 2
    component_labels = {e.component_type for e in bom.components}
    assert "ldo_regulator" in component_labels
    assert "input_capacitor" in component_labels


# =============================================================================
# Test 3: COMPONENT_INSTANCE in subgraph → BOMEntry.specific_part populated
# =============================================================================


def test_component_instance_in_subgraph_populates_specific_part(mock_config, sample_intent):
    """3. COMPONENT_INSTANCE in subgraph → BOMEntry.specific_part populated."""
    regulator = _create_component_type("regulator", "ldo_regulator")
    specific_reg = _create_component_instance("tps62933", "TPS62933", "ldo_regulator")
    
    subgraph = _create_subgraph(
        component_types=[regulator],
        component_instances=[specific_reg],
        path_confidences={regulator.id: 0.9}
    )
    
    # The instance's component_type property should match
    specific_reg.properties["component_type"] = "ldo_regulator"
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    # Find the regulator entry
    regulator_entry = next((e for e in bom.components if "regulator" in e.component_type), None)
    assert regulator_entry is not None
    assert regulator_entry.specific_part == "TPS62933"
    assert regulator_entry.review_flag is False


# =============================================================================
# Test 4: No COMPONENT_INSTANCE → BOMEntry.specific_part is None, review_flag=True
# =============================================================================


def test_no_component_instance_leaves_specific_part_none(mock_config, sample_intent):
    """4. No COMPONENT_INSTANCE → BOMEntry.specific_part is None, review_flag=True."""
    regulator = _create_component_type("regulator", "ldo_regulator")
    
    subgraph = _create_subgraph(
        component_types=[regulator],
        component_instances=[],  # No instances
        path_confidences={regulator.id: 0.9}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    regulator_entry = bom.components[0]
    assert regulator_entry.specific_part is None
    assert regulator_entry.review_flag is True


# =============================================================================
# Test 5: BOMEntry.ref follows REF_DESIGNATOR_MAP ("capacitor" → "C1")
# =============================================================================


def test_reference_designator_follows_map(mock_config, sample_intent):
    """5. BOMEntry.ref follows REF_DESIGNATOR_MAP ("capacitor" → "C1")."""
    capacitor = _create_component_type("capacitor", "capacitor")
    
    subgraph = _create_subgraph(
        component_types=[capacitor],
        path_confidences={capacitor.id: 0.9}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    assert len(bom.components) == 1
    assert bom.components[0].ref == "C1"


# =============================================================================
# Test 6: Two capacitors → "C1" and "C2" (counter increments per type)
# =============================================================================


def test_multiple_same_type_gets_incrementing_refs(mock_config, sample_intent):
    """6. Two capacitors → "C1" and "C2" (counter increments per type)."""
    cap1 = _create_component_type("cap1", "input_capacitor")
    cap2 = _create_component_type("cap2", "output_capacitor")
    
    subgraph = _create_subgraph(
        component_types=[cap1, cap2],
        path_confidences={cap1.id: 0.9, cap2.id: 0.85}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    refs = {e.ref for e in bom.components}
    # Both should be C-prefixed with different numbers
    assert "C1" in refs
    assert "C2" in refs


# =============================================================================
# Test 7: total_confidence below threshold → review_required=True
# =============================================================================


def test_low_total_confidence_triggers_review(mock_config, sample_intent):
    """7. total_confidence below threshold → review_required=True."""
    # Create components with very low confidence
    low_conf_component = _create_component_type("bad", "unknown_type", confidence=0.4)
    
    subgraph = _create_subgraph(
        component_types=[low_conf_component],
        path_confidences={low_conf_component.id: 0.4}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    assert bom.total_confidence < 0.85  # Below threshold
    assert bom.review_required is True


# =============================================================================
# Test 8: Any entry confidence below bom_component threshold → review_required=True
# =============================================================================


def test_low_component_confidence_triggers_review(mock_config, sample_intent):
    """8. Any entry confidence below bom_component threshold → review_required=True."""
    # Mix of high and low confidence components
    good_component = _create_component_type("good", "regulator", confidence=0.95)
    bad_component = _create_component_type("bad", "sensor", confidence=0.5)
    
    subgraph = _create_subgraph(
        component_types=[good_component, bad_component],
        path_confidences={good_component.id: 0.95, bad_component.id: 0.5}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    # One component below 0.75 should trigger review
    assert bom.review_required is True


# =============================================================================
# Test 9: design_id is a valid UUID string
# =============================================================================


def test_design_id_is_valid_uuid(mock_config, sample_intent):
    """9. design_id is a valid UUID string."""
    import uuid
    
    regulator = _create_component_type("regulator", "ldo_regulator")
    subgraph = _create_subgraph(
        component_types=[regulator],
        path_confidences={regulator.id: 0.9}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    # Should be a valid UUID
    try:
        uuid.UUID(bom.design_id)
        is_valid_uuid = True
    except ValueError:
        is_valid_uuid = False
    
    assert is_valid_uuid


# =============================================================================
# Test 10: generate_bom never raises when subgraph has malformed nodes
# =============================================================================


def test_generate_bom_never_raises_with_malformed_nodes(mock_config, sample_intent):
    """10. generate_bom never raises when subgraph has malformed nodes."""
    # Create a component node with missing required fields (simulating corruption)
    # This should be handled gracefully
    try:
        malformed_node = KGNode(
            id="component_type:malformed",
            node_type=KGNodeType.COMPONENT_TYPE,
            layer=2,
            label="",  # Empty label - might cause issues
            properties={},
            source="",
            confidence=0.0,
            extraction_method=ExtractionMethod.MANUAL,
            created_at="",
        )
        
        subgraph = _create_subgraph(
            component_types=[malformed_node],
            path_confidences={malformed_node.id: 0.0}
        )
        
        # Should not raise
        bom = generate_bom(subgraph, sample_intent, mock_config)
        
        # Should return a ValidatedBOM
        assert isinstance(bom, ValidatedBOM)
        # Either empty or with the malformed entry
        assert len(bom.components) >= 0
        
    except Exception as e:
        pytest.fail(f"generate_bom raised an exception: {e}")


# =============================================================================
# Additional tests
# =============================================================================


def test_bom_entry_has_justification(mock_config, sample_intent):
    """BOM entries should have justification text."""
    regulator = _create_component_type("regulator", "ldo_regulator")
    
    subgraph = _create_subgraph(
        component_types=[regulator],
        path_confidences={regulator.id: 0.9}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    entry = bom.components[0]
    assert entry.justification != ""
    assert "ldo regulator" in entry.justification.lower() or "required" in entry.justification.lower()


def test_bom_entry_source_is_set(mock_config, sample_intent):
    """BOM entries should have source information."""
    regulator = _create_component_type("regulator", "ldo_regulator", source="TI_datasheet.pdf")
    
    subgraph = _create_subgraph(
        component_types=[regulator],
        path_confidences={regulator.id: 0.9}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    entry = bom.components[0]
    assert entry.source == "TI_datasheet.pdf"


def test_created_at_is_iso_format(mock_config, sample_intent):
    """created_at should be ISO 8601 format."""
    import re
    
    regulator = _create_component_type("regulator", "ldo_regulator")
    subgraph = _create_subgraph(
        component_types=[regulator],
        path_confidences={regulator.id: 0.9}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    # Should be ISO 8601 format with Z suffix
    iso_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
    assert re.match(iso_pattern, bom.created_at)


def test_validated_bom_contains_intent(mock_config, sample_intent):
    """ValidatedBOM should contain the original intent."""
    regulator = _create_component_type("regulator", "ldo_regulator")
    subgraph = _create_subgraph(
        component_types=[regulator],
        path_confidences={regulator.id: 0.9}
    )
    
    bom = generate_bom(subgraph, sample_intent, mock_config)
    
    assert bom.intent is not None
    assert bom.intent.goal == sample_intent.goal
