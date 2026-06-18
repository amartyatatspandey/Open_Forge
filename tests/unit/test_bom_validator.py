"""Tests for the BOM validator module.

Tests validate_bom() and supplier_cache covering various validation scenarios
including voltage conflicts, logic level mismatches, and supplier availability.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.bom.validator import validate_bom
from src.bom.supplier_cache import (
    AvailabilityStatus,
    check_availability,
    upsert_availability,
)
from src.schemas.intent import (
    BOMEntry,
    DesignMethodology,
    IntentDict,
    ValidatedBOM,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_config():
    """Create a mock Config with supplier_cache_path."""
    config = MagicMock()
    # Use a temporary directory for cache
    temp_dir = tempfile.mkdtemp()
    config.supplier_cache_path = Path(temp_dir) / "supplier_cache.db"
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


def _create_bom_entry(
    ref: str,
    component_type: str,
    specific_part: str | None = None,
    value_constraints: dict | None = None,
    review_flag: bool = False,
) -> BOMEntry:
    """Helper to create a BOMEntry."""
    return BOMEntry(
        ref=ref,
        component_type=component_type,
        specific_part=specific_part,
        value_constraints=value_constraints or {},
        justification=f"Test {component_type}",
        source="test",
        confidence=0.9,
        alternatives=[],
        review_flag=review_flag,
    )


def _create_validated_bom(
    components: list[BOMEntry],
    intent: IntentDict | None = None,
    review_flags: list[str] | None = None,
    review_required: bool = False,
) -> ValidatedBOM:
    """Helper to create a ValidatedBOM for testing."""
    if intent is None:
        intent = IntentDict(
            goal="test",
            frequency=None,
            application="test",
            explicit_constraints=[],
            inferred_constraints=[],
            design_methodology=DesignMethodology.STANDARD_SMD,
            board_type="2-layer FR4",
            ambiguities=[],
            clarification_required=False,
            raw_prompt="test",
        )
    return ValidatedBOM(
        design_id="test-design-001",
        intent=intent,
        components=components,
        cross_component_rules=[],
        total_confidence=0.9,
        review_required=review_required,
        review_flags=review_flags or [],
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


# =============================================================================
# Test 1: validate_bom returns NEW ValidatedBOM (does not mutate input)
# =============================================================================


def test_validate_bom_returns_new_instance_does_not_mutate_input(mock_config, sample_intent):
    """1. validate_bom returns NEW ValidatedBOM (does not mutate input)."""
    entry = _create_bom_entry("U1", "regulator")
    original_bom = _create_validated_bom([entry], intent=sample_intent)
    original_components_id = id(original_bom.components)
    original_flags = list(original_bom.review_flags)

    validated = validate_bom(original_bom, mock_config)

    # Must return a new instance
    assert validated is not original_bom

    # Original BOM should be unchanged
    assert original_bom.components is not validated.components
    assert id(original_bom.components) == original_components_id
    assert original_bom.review_flags == original_flags


# =============================================================================
# Test 2: Two power components with different voltages → WARNING review_flag added
# =============================================================================


def test_voltage_conflict_generates_warning_flag(mock_config, sample_intent):
    """2. Two power components with different voltages → WARNING review_flag added."""
    entry1 = _create_bom_entry(
        "U1", "buck_regulator",
        value_constraints={"output_voltage": 5.0}
    )
    entry2 = _create_bom_entry(
        "U2", "ldo_regulator",
        value_constraints={"output_voltage": 3.3}
    )
    bom = _create_validated_bom([entry1, entry2], intent=sample_intent)

    validated = validate_bom(bom, mock_config)

    # Should have a voltage conflict flag
    voltage_flags = [f for f in validated.review_flags if "voltage conflict" in f.lower()]
    assert len(voltage_flags) == 1
    assert "U1" in voltage_flags[0]
    assert "U2" in voltage_flags[0]


# =============================================================================
# Test 3: Two ICs with different logic voltages → WARNING review_flag added
# =============================================================================


def test_logic_level_mismatch_generates_warning_flag(mock_config, sample_intent):
    """3. Two ICs with different logic voltages → WARNING review_flag added."""
    entry1 = _create_bom_entry(
        "U1", "microcontroller",
        value_constraints={"logic_voltage": 3.3}
    )
    entry2 = _create_bom_entry(
        "U2", "ic_interface",
        value_constraints={"logic_voltage": 5.0}
    )
    bom = _create_validated_bom([entry1, entry2], intent=sample_intent)

    validated = validate_bom(bom, mock_config)

    # Should have a logic level mismatch flag
    logic_flags = [f for f in validated.review_flags if "logic level mismatch" in f.lower()]
    assert len(logic_flags) == 1
    assert "U1" in logic_flags[0]
    assert "U2" in logic_flags[0]


# =============================================================================
# Test 4: Unknown component in supplier cache → INFO review_flag, review_required unchanged
# =============================================================================


def test_unknown_component_adds_info_flag_does_not_set_review_required(mock_config, sample_intent):
    """4. Unknown component in supplier cache → INFO review_flag, review_required unchanged."""
    entry = _create_bom_entry("U1", "regulator", specific_part="UNKNOWN_PART_12345")
    bom = _create_validated_bom([entry], intent=sample_intent, review_required=False)

    validated = validate_bom(bom, mock_config)

    # Should have an INFO-level flag about unverified availability
    info_flags = [f for f in validated.review_flags if "unverified" in f.lower()]
    assert len(info_flags) >= 1
    assert "UNKNOWN_PART_12345" in info_flags[0]

    # review_required should remain False (no CRITICAL flags)
    assert validated.review_required is False


# =============================================================================
# Test 5: Unavailable component → WARNING flag, entry.review_flag=True
# =============================================================================


def test_unavailable_component_sets_warning_and_review_flag(mock_config, sample_intent):
    """5. Unavailable component → WARNING flag, entry.review_flag=True."""
    # Pre-populate cache with unavailable component
    upsert_availability(
        "UNAVAILABLE_PART",
        AvailabilityStatus.UNAVAILABLE,
        None,
        0,
        "DigiKey",
        "2026-06-18",
        mock_config,
    )

    entry = _create_bom_entry("U1", "regulator", specific_part="UNAVAILABLE_PART")
    bom = _create_validated_bom([entry], intent=sample_intent)

    validated = validate_bom(bom, mock_config)

    # Should have a WARNING-level flag about unavailable component
    warning_flags = [f for f in validated.review_flags if "unavailable" in f.lower()]
    assert len(warning_flags) >= 1
    assert "UNAVAILABLE_PART" in warning_flags[0]

    # The entry should have review_flag=True
    assert validated.components[0].review_flag is True


# =============================================================================
# Test 6: No compatibility issues → review_flags unchanged from input
# =============================================================================


def test_no_issues_preserves_existing_flags(mock_config, sample_intent):
    """6. No compatibility issues → review_flags unchanged from input."""
    entry = _create_bom_entry("U1", "capacitor")  # No power/voltage properties
    existing_flags = ["Existing flag from earlier stage"]
    bom = _create_validated_bom([entry], intent=sample_intent, review_flags=existing_flags)

    validated = validate_bom(bom, mock_config)

    # Existing flags should be preserved
    assert all(f in validated.review_flags for f in existing_flags)

    # No new flags should be added (no voltage, logic, or supplier checks triggered)
    # Just the existing one
    assert len(validated.review_flags) == len(existing_flags)


# =============================================================================
# Test 7: validate_bom never raises on empty components list
# =============================================================================


def test_validate_bom_never_raises_on_empty_components(mock_config, sample_intent):
    """7. validate_bom never raises on empty components list."""
    bom = _create_validated_bom([], intent=sample_intent)

    try:
        validated = validate_bom(bom, mock_config)
        assert isinstance(validated, ValidatedBOM)
        assert validated.components == []
    except Exception as e:
        pytest.fail(f"validate_bom raised an exception on empty components: {e}")


# =============================================================================
# Test 8: supplier_cache.check_availability returns UNKNOWN for unknown component_id
# =============================================================================


def test_check_availability_returns_unknown_for_unknown_component(mock_config):
    """8. supplier_cache.check_availability returns UNKNOWN for unknown component_id."""
    status = check_availability("NONEXISTENT_PART_99999", mock_config)
    assert status == AvailabilityStatus.UNKNOWN


# =============================================================================
# Test 9: supplier_cache round-trips upsert and check correctly
# =============================================================================


def test_supplier_cache_round_trip_upsert_and_check(mock_config):
    """9. supplier_cache round-trips upsert and check correctly."""
    # Insert available component
    upsert_availability(
        "AVAILABLE_PART",
        AvailabilityStatus.AVAILABLE,
        1.50,
        1000,
        "DigiKey",
        "2026-06-18",
        mock_config,
    )

    # Insert unavailable component
    upsert_availability(
        "OUT_OF_STOCK_PART",
        AvailabilityStatus.UNAVAILABLE,
        None,
        0,
        "Mouser",
        "2026-06-18",
        mock_config,
    )

    # Check round-trip for available
    status1 = check_availability("AVAILABLE_PART", mock_config)
    assert status1 == AvailabilityStatus.AVAILABLE

    # Check round-trip for unavailable
    status2 = check_availability("OUT_OF_STOCK_PART", mock_config)
    assert status2 == AvailabilityStatus.UNAVAILABLE


# =============================================================================
# Test 10: supplier_cache returns UNKNOWN (not raises) on missing DB file
# =============================================================================


def test_check_availability_returns_unknown_on_missing_db_file():
    """10. supplier_cache returns UNKNOWN (not raises) on missing DB file."""
    # Create a mock config pointing to a non-existent directory
    config = MagicMock()
    nonexistent_path = Path("/nonexistent/directory/supplier_cache.db")
    config.supplier_cache_path = nonexistent_path

    try:
        status = check_availability("ANY_PART", config)
        # Should return UNKNOWN, not raise
        assert status == AvailabilityStatus.UNKNOWN
    except Exception as e:
        pytest.fail(f"check_availability raised an exception on missing DB: {e}")


# =============================================================================
# Additional tests
# =============================================================================


def test_same_voltage_no_conflict_flag(mock_config, sample_intent):
    """Two power components with same voltage should not generate conflict."""
    entry1 = _create_bom_entry(
        "U1", "buck_regulator",
        value_constraints={"output_voltage": 3.3}
    )
    entry2 = _create_bom_entry(
        "U2", "ldo_regulator",
        value_constraints={"output_voltage": 3.3}  # Same voltage
    )
    bom = _create_validated_bom([entry1, entry2], intent=sample_intent)

    validated = validate_bom(bom, mock_config)

    # Should not have a voltage conflict flag
    voltage_flags = [f for f in validated.review_flags if "voltage conflict" in f.lower()]
    assert len(voltage_flags) == 0


def test_available_component_no_flag(mock_config, sample_intent):
    """Available component should not add any flags."""
    # Pre-populate cache with available component
    upsert_availability(
        "IN_STOCK_PART",
        AvailabilityStatus.AVAILABLE,
        2.99,
        500,
        "DigiKey",
        "2026-06-18",
        mock_config,
    )

    entry = _create_bom_entry("U1", "regulator", specific_part="IN_STOCK_PART")
    bom = _create_validated_bom([entry], intent=sample_intent)

    validated = validate_bom(bom, mock_config)

    # Should not have any availability-related flags
    availability_flags = [f for f in validated.review_flags if "unavailable" in f.lower() or "unverified" in f.lower()]
    assert len(availability_flags) == 0

    # Entry review_flag should remain False
    assert validated.components[0].review_flag is False


def test_component_without_specific_part_skips_availability_check(mock_config, sample_intent):
    """Components without specific_part should skip supplier availability check."""
    entry = _create_bom_entry("U1", "regulator", specific_part=None)
    bom = _create_validated_bom([entry], intent=sample_intent)

    validated = validate_bom(bom, mock_config)

    # Should not have any availability flags
    availability_flags = [f for f in validated.review_flags if "availability" in f.lower()]
    assert len(availability_flags) == 0


def test_upsert_updates_existing_component(mock_config):
    """Upsert should update existing component status."""
    # First insert as available
    upsert_availability(
        "CHANGING_PART",
        AvailabilityStatus.AVAILABLE,
        1.00,
        100,
        "DigiKey",
        "2026-06-01",
        mock_config,
    )

    # Verify available
    status1 = check_availability("CHANGING_PART", mock_config)
    assert status1 == AvailabilityStatus.AVAILABLE

    # Update to unavailable
    upsert_availability(
        "CHANGING_PART",
        AvailabilityStatus.UNAVAILABLE,
        None,
        0,
        "DigiKey",
        "2026-06-18",
        mock_config,
    )

    # Verify updated
    status2 = check_availability("CHANGING_PART", mock_config)
    assert status2 == AvailabilityStatus.UNAVAILABLE