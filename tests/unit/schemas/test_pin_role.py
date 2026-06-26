"""Gate tests for PinRole enum and PinDefinition extension."""
import pytest
from src.schemas.datasheet import (
    PinRole,
    PinDefinition,
    CANONICAL_TO_ROLE,
)


# ── PinRole enum ─────────────────────────────────────────────────────────────

def test_pin_role_has_required_values():
    required = {
        "POWER_IN", "POWER_OUT", "GROUND", "SIGNAL_IN", "SIGNAL_OUT",
        "BIDIRECTIONAL", "CLOCK", "ENABLE", "ENABLE_N", "RESET",
        "REFERENCE", "SENSE_POS", "SENSE_NEG", "DIFFERENTIAL_POS",
        "DIFFERENTIAL_NEG", "CHIP_SELECT", "FEEDBACK", "ADJUST",
        "INTERRUPT", "ANALOG_IN", "ANALOG_OUT", "EXPOSED_PAD", "NC",
    }
    actual = {e.name for e in PinRole}
    assert required.issubset(actual), f"Missing roles: {required - actual}"

def test_pin_role_is_str_enum():
    assert isinstance(PinRole.POWER_IN, str)
    assert PinRole.POWER_IN == "power_in"

def test_pin_role_values_are_lowercase_underscored():
    for role in PinRole:
        assert role.value == role.value.lower(), f"{role.name} value not lowercase"
        assert " " not in role.value, f"{role.name} value contains space"


# ── CANONICAL_TO_ROLE mapping ────────────────────────────────────────────────

def test_canonical_to_role_covers_key_canonical_strings():
    required_keys = {
        "POWER_POSITIVE", "POWER_INPUT", "POWER_GROUND",
        "ENABLE", "RESET", "SPI_CLOCK", "I2C_CLOCK", "I2C_DATA",
        "SPI_MOSI", "SPI_MISO", "CHIP_SELECT", "FEEDBACK",
        "NO_CONNECT", "ANALOG_INPUT", "ANALOG_OUTPUT",
    }
    for key in required_keys:
        assert key in CANONICAL_TO_ROLE, f"Missing mapping for: {key}"

def test_canonical_to_role_all_values_are_pin_role():
    for k, v in CANONICAL_TO_ROLE.items():
        assert isinstance(v, PinRole), f"Value for {k!r} is not PinRole: {v!r}"

def test_power_positive_maps_to_power_out():
    assert CANONICAL_TO_ROLE["POWER_POSITIVE"] == PinRole.POWER_OUT

def test_power_ground_maps_to_ground():
    assert CANONICAL_TO_ROLE["POWER_GROUND"] == PinRole.GROUND

def test_power_input_maps_to_power_in():
    assert CANONICAL_TO_ROLE["POWER_INPUT"] == PinRole.POWER_IN

def test_spi_clock_maps_to_clock():
    assert CANONICAL_TO_ROLE["SPI_CLOCK"] == PinRole.CLOCK

def test_enable_low_maps_to_enable_n():
    assert CANONICAL_TO_ROLE["ENABLE_LOW"] == PinRole.ENABLE_N


# ── PinDefinition.pin_role field ─────────────────────────────────────────────

def test_pin_definition_pin_role_defaults_to_none():
    pin = PinDefinition(pin_number="1", raw_name="VDD")
    assert pin.pin_role is None

def test_pin_definition_accepts_pin_role():
    pin = PinDefinition(pin_number="1", raw_name="VDD", pin_role=PinRole.POWER_IN)
    assert pin.pin_role == PinRole.POWER_IN

def test_pin_definition_normalized_function_unchanged():
    """Existing normalized_function field must still exist and work."""
    pin = PinDefinition(
        pin_number="1",
        raw_name="VDD",
        normalized_function="POWER_POSITIVE",
        pin_role=PinRole.POWER_OUT,
    )
    assert pin.normalized_function == "POWER_POSITIVE"
    assert pin.pin_role == PinRole.POWER_OUT

def test_pin_definition_model_copy_preserves_pin_role():
    pin = PinDefinition(pin_number="1", raw_name="VDD", pin_role=PinRole.POWER_IN)
    copied = pin.model_copy(update={"raw_name": "VCC"})
    assert copied.pin_role == PinRole.POWER_IN

def test_pin_definition_model_copy_can_update_pin_role():
    pin = PinDefinition(pin_number="1", raw_name="VDD", pin_role=PinRole.POWER_IN)
    updated = pin.model_copy(update={"pin_role": PinRole.POWER_OUT})
    assert updated.pin_role == PinRole.POWER_OUT


# ── Pin normalizer integration ────────────────────────────────────────────────

def test_normalizer_populates_pin_role_from_canonical_function():
    """After normalization, pin_role must be set for known canonical strings."""
    from unittest.mock import patch
    from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod
    from src.knowledge_graph.pin_normalizer import normalize_pins
    from src.config import get_config

    config = get_config()

    # Build a minimal datasheet with a pin whose raw name maps to a known canonical
    pin = PinDefinition(pin_number="1", raw_name="VDD")
    ds = ComponentDatasheet(
        component_id="TEST_PINROLE_001",
        manufacturer="TestCo",
        description="Test component",
        package="SOT-23",
        source_pdf_hash="a" * 64,
        pins=[pin],
        extraction_method=ExtractionMethod.MANUAL,
        extraction_confidence=0.9,
        created_at="2026-01-01T00:00:00+00:00",
    )

    # VDD should normalize to POWER_POSITIVE → pin_role = POWER_OUT
    normalized_list = normalize_pins([ds], config)
    normalized_pin = normalized_list[0].pins[0]

    assert normalized_pin.normalized_function == "POWER_POSITIVE"
    assert normalized_pin.pin_role == PinRole.POWER_OUT

def test_normalizer_pin_role_none_when_normalization_fails():
    """If all tiers fail, pin_role must stay None."""
    from unittest.mock import patch
    from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod
    from src.knowledge_graph.pin_normalizer import normalize_pins
    from src.config import get_config

    config = get_config()

    pin = PinDefinition(pin_number="1", raw_name="XYZQWERTY_UNKNOWN_PIN_NAME_99")
    ds = ComponentDatasheet(
        component_id="TEST_PINROLE_002",
        manufacturer="TestCo",
        description="Test component",
        package="SOT-23",
        source_pdf_hash="b" * 64,
        pins=[pin],
        extraction_method=ExtractionMethod.MANUAL,
        extraction_confidence=0.9,
        created_at="2026-01-01T00:00:00+00:00",
    )

    # Mock LLM fallback to also return None so all tiers fail
    with patch(
        "src.knowledge_graph.pin_normalizer.normalizer.normalize_via_llm",
        return_value=(None, 0.0, "llm"),
    ):
        normalized_list = normalize_pins([ds], config)
    normalized_pin = normalized_list[0].pins[0]

    assert normalized_pin.normalized_function is None
    assert normalized_pin.pin_role is None


# ── p1_importer integration ───────────────────────────────────────────────────

def test_p1_importer_stores_pin_role_in_kg_node_properties():
    """KGNode properties must include pin_role when pin has one."""
    from datetime import datetime, timezone
    from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod
    from src.knowledge_graph.importers.p1_importer import _create_pin_nodes

    now = datetime.now(timezone.utc).isoformat()
    pin = PinDefinition(
        pin_number="1",
        raw_name="VDD",
        normalized_function="POWER_POSITIVE",
        pin_role=PinRole.POWER_OUT,
    )
    ds = ComponentDatasheet(
        component_id="TEST_IMPORTER_001",
        manufacturer="TestCo",
        description="Test",
        package="SOT-23",
        source_pdf_hash="c" * 64,
        pins=[pin],
        extraction_method=ExtractionMethod.MANUAL,
        extraction_confidence=0.9,
        created_at=now,
    )
    nodes = _create_pin_nodes(ds, now)
    assert len(nodes) == 1
    assert nodes[0].properties.get("pin_role") == "power_out"

def test_p1_importer_omits_pin_role_when_none():
    """KGNode properties must NOT include pin_role key when pin_role is None."""
    from datetime import datetime, timezone
    from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod
    from src.knowledge_graph.importers.p1_importer import _create_pin_nodes

    now = datetime.now(timezone.utc).isoformat()
    pin = PinDefinition(pin_number="1", raw_name="UNKNOWN", pin_role=None)
    ds = ComponentDatasheet(
        component_id="TEST_IMPORTER_002",
        manufacturer="TestCo",
        description="Test",
        package="SOT-23",
        source_pdf_hash="d" * 64,
        pins=[pin],
        extraction_method=ExtractionMethod.MANUAL,
        extraction_confidence=0.9,
        created_at=now,
    )
    nodes = _create_pin_nodes(ds, now)
    assert "pin_role" not in nodes[0].properties
