"""Gate tests for the structural verifier (Layers 1-3)."""
from src.schematic.structural_verifier import (
    verify_schematic,
    VerificationResult,
    VerifierLayer,
    LayerResult,
    LayerViolation,
    _LAYER_WEIGHTS,
)
from src.schemas.datasheet import (
    ComponentDatasheet, PinDefinition, PinRole, ExtractionMethod,
)
from src.schemas.nir import NetlistEntry, PinRef
from src.schemas.intent import ValidatedBOM, BOMEntry, IntentDict, DesignMethodology


NOW = "2026-01-01T00:00:00+00:00"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_ds(
    component_id: str,
    pins: list[tuple[str, str, PinRole]],  # (number, name, role)
) -> ComponentDatasheet:
    return ComponentDatasheet(
        component_id=component_id,
        manufacturer="TestCo",
        description=component_id,
        package="SOT-23",
        source_pdf_hash="a" * 64,
        pins=[
            PinDefinition(
                pin_number=num,
                raw_name=name,
                normalized_function=role.value.upper(),
                pin_role=role,
            )
            for num, name, role in pins
        ],
        extraction_method=ExtractionMethod.MANUAL,
        extraction_confidence=0.9,
        created_at=NOW,
    )


def _make_net(
    net_name: str,
    net_type: str,
    connections: list[tuple[str, str, str]],  # (ref, pin_name, pin_number)
) -> NetlistEntry:
    return NetlistEntry(
        net_name=net_name,
        net_type=net_type,  # type: ignore[arg-type]
        connections=[
            PinRef(ref=ref, pin_name=name, pin_number=num)
            for ref, name, num in connections
        ],
        source_rule="test",
        net_confidence=1.0,
    )


def _make_ref_map(
    entries: list[tuple[str, str, ComponentDatasheet]],
) -> dict[str, tuple[str, ComponentDatasheet]]:
    # entries: (component_id, ref, datasheet)
    return {cid: (ref, ds) for cid, ref, ds in entries}


def _make_bom(*entries: tuple[str, str]) -> ValidatedBOM:
    # entries: (ref, component_type)
    intent = IntentDict(
        goal="test",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt="test",
    )
    return ValidatedBOM(
        design_id="test-design",
        intent=intent,
        components=[
            BOMEntry(
                ref=ref,
                component_type=ctype,
                justification="test",
                source="test",
                confidence=0.9,
            )
            for ref, ctype in entries
        ],
        total_confidence=0.9,
        review_required=False,
        created_at=NOW,
    )


# ── VerificationResult schema ────────────────────────────────────────────────

def test_verify_empty_netlist_returns_result():
    result = verify_schematic([], {})
    assert isinstance(result, VerificationResult)
    assert 0.0 <= result.score <= 1.0

def test_verify_empty_netlist_score_near_one():
    result = verify_schematic([], {})
    assert result.score >= 0.9

def test_result_has_three_layer_results():
    result = verify_schematic([], {})
    layers = {lr.layer for lr in result.layer_results}
    assert VerifierLayer.ELECTRICAL_INVARIANTS in layers
    assert VerifierLayer.PIN_ROLE_COMPATIBILITY in layers
    assert VerifierLayer.SUBCATEGORY_TEMPLATES in layers

def test_get_layer_returns_correct_result():
    result = verify_schematic([], {})
    lr = result.get_layer(VerifierLayer.ELECTRICAL_INVARIANTS)
    assert lr is not None
    assert lr.layer == VerifierLayer.ELECTRICAL_INVARIANTS

def test_lowest_scoring_layer_returns_layer_result():
    result = verify_schematic([], {})
    lr = result.lowest_scoring_layer()
    assert lr is None or isinstance(lr, LayerResult)


# ── Layer 1: Electrical Invariants ────────────────────────────────────────────

def test_layer1_passes_on_valid_schematic():
    # LDO with correctly connected pins
    ds = _make_ds("LDO_001", [
        ("1", "IN", PinRole.POWER_IN),
        ("2", "GND", PinRole.GROUND),
        ("3", "OUT", PinRole.POWER_OUT),
    ])
    ref_map = _make_ref_map([("LDO_001", "U1", ds)])
    netlist = [
        _make_net("VIN", "power", [("U1", "IN", "1")]),
        _make_net("GND", "power", [("U1", "GND", "2")]),
        _make_net("VOUT", "power", [("U1", "OUT", "3")]),
    ]
    result = verify_schematic(netlist, ref_map)
    lr = result.get_layer(VerifierLayer.ELECTRICAL_INVARIANTS)
    assert lr is not None
    assert lr.score >= 0.8


# ── Layer 2: Pin-Role Compatibility ──────────────────────────────────────────

def test_layer2_detects_driver_conflict():
    # Two POWER_OUT pins on same net — short circuit
    ds_a = _make_ds("REG_A", [("3", "OUT", PinRole.POWER_OUT)])
    ds_b = _make_ds("REG_B", [("3", "OUT", PinRole.POWER_OUT)])
    ref_map = _make_ref_map([
        ("REG_A", "U1", ds_a),
        ("REG_B", "U2", ds_b),
    ])
    netlist = [
        _make_net("VOUT", "power", [("U1", "OUT", "3"), ("U2", "OUT", "3")]),
    ]
    result = verify_schematic(netlist, ref_map)
    lr = result.get_layer(VerifierLayer.PIN_ROLE_COMPATIBILITY)
    assert lr is not None
    assert lr.score < 1.0
    assert any("driver conflict" in v.message for v in lr.violations)

def test_layer2_critical_for_driver_conflict():
    ds_a = _make_ds("REG_A", [("3", "OUT", PinRole.POWER_OUT)])
    ds_b = _make_ds("REG_B", [("3", "OUT", PinRole.POWER_OUT)])
    ref_map = _make_ref_map([("REG_A", "U1", ds_a), ("REG_B", "U2", ds_b)])
    netlist = [_make_net("VOUT", "power", [("U1", "OUT", "3"), ("U2", "OUT", "3")])]
    result = verify_schematic(netlist, ref_map)
    assert any(v.severity == "CRITICAL" for v in result.critical_violations)

def test_layer2_detects_nc_pin_connected():
    ds = _make_ds("IC_001", [
        ("1", "VDD", PinRole.POWER_IN),
        ("2", "NC", PinRole.NC),
    ])
    ref_map = _make_ref_map([("IC_001", "U1", ds)])
    netlist = [
        _make_net("VDD", "power", [("U1", "VDD", "1")]),
        _make_net("SOME_NET", "signal", [("U1", "NC", "2"), ("U1", "VDD", "1")]),
    ]
    result = verify_schematic(netlist, ref_map)
    lr = result.get_layer(VerifierLayer.PIN_ROLE_COMPATIBILITY)
    assert lr is not None
    assert any("NC pin" in v.message for v in lr.violations)

def test_layer2_passes_valid_power_receiver():
    # POWER_OUT driving POWER_IN — valid
    ds_reg = _make_ds("LDO", [("3", "OUT", PinRole.POWER_OUT)])
    ds_ic = _make_ds("IC", [("1", "VDD", PinRole.POWER_IN)])
    ref_map = _make_ref_map([("LDO", "U1", ds_reg), ("IC", "U2", ds_ic)])
    netlist = [
        _make_net("VOUT", "power", [("U1", "OUT", "3"), ("U2", "VDD", "1")]),
    ]
    result = verify_schematic(netlist, ref_map)
    lr = result.get_layer(VerifierLayer.PIN_ROLE_COMPATIBILITY)
    assert lr is not None
    assert not any("driver conflict" in v.message for v in lr.violations)


# ── Layer 3: Subcategory Templates ────────────────────────────────────────────

def test_layer3_skipped_without_bom():
    result = verify_schematic([], {}, bom=None)
    lr = result.get_layer(VerifierLayer.SUBCATEGORY_TEMPLATES)
    assert lr is not None
    assert lr.skipped is True

def test_layer3_passes_ldo_with_all_roles_connected():
    ds = _make_ds("LDO", [
        ("1", "IN", PinRole.POWER_IN),
        ("2", "GND", PinRole.GROUND),
        ("3", "OUT", PinRole.POWER_OUT),
    ])
    ref_map = _make_ref_map([("LDO", "U1", ds)])
    bom = _make_bom(("U1", "ldo_regulator"))
    netlist = [
        _make_net("VIN", "power", [("U1", "IN", "1")]),
        _make_net("GND", "power", [("U1", "GND", "2")]),
        _make_net("VOUT", "power", [("U1", "OUT", "3")]),
    ]
    result = verify_schematic(netlist, ref_map, bom=bom)
    lr = result.get_layer(VerifierLayer.SUBCATEGORY_TEMPLATES)
    assert lr is not None
    assert lr.score == 1.0
    assert len(lr.violations) == 0

def test_layer3_critical_when_required_role_not_connected():
    # LDO output (POWER_OUT) not connected
    ds = _make_ds("LDO", [
        ("1", "IN", PinRole.POWER_IN),
        ("2", "GND", PinRole.GROUND),
        ("3", "OUT", PinRole.POWER_OUT),
    ])
    ref_map = _make_ref_map([("LDO", "U1", ds)])
    bom = _make_bom(("U1", "ldo_regulator"))
    netlist = [
        _make_net("VIN", "power", [("U1", "IN", "1")]),
        _make_net("GND", "power", [("U1", "GND", "2")]),
        # OUT pin NOT connected — missing from netlist
    ]
    result = verify_schematic(netlist, ref_map, bom=bom)
    lr = result.get_layer(VerifierLayer.SUBCATEGORY_TEMPLATES)
    assert lr is not None
    assert lr.score < 1.0
    assert any(v.severity == "CRITICAL" for v in lr.violations)

def test_layer3_no_template_match_skips_gracefully():
    ds = _make_ds("DIODE", [("1", "A", PinRole.SIGNAL_IN)])
    ref_map = _make_ref_map([("DIODE", "D1", ds)])
    bom = _make_bom(("D1", "diode"))  # no template for "diode"
    result = verify_schematic([], ref_map, bom=bom)
    lr = result.get_layer(VerifierLayer.SUBCATEGORY_TEMPLATES)
    assert lr is not None
    assert lr.skipped is True or lr.constraints_checked == 0


# ── Score computation ─────────────────────────────────────────────────────────

def test_score_is_between_zero_and_one():
    result = verify_schematic([], {})
    assert 0.0 <= result.score <= 1.0

def test_score_is_one_for_empty_valid_schematic():
    result = verify_schematic([], {})
    assert result.score >= 0.95

def test_score_decreases_on_violations():
    ds_a = _make_ds("REG_A", [("3", "OUT", PinRole.POWER_OUT)])
    ds_b = _make_ds("REG_B", [("3", "OUT", PinRole.POWER_OUT)])
    ref_map = _make_ref_map([("REG_A", "U1", ds_a), ("REG_B", "U2", ds_b)])
    netlist = [_make_net("VOUT", "power", [("U1", "OUT", "3"), ("U2", "OUT", "3")])]
    result = verify_schematic(netlist, ref_map)
    assert result.score < 1.0

def test_layer_weights_sum_to_one():
    total = sum(_LAYER_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9

def test_critical_violations_aggregated():
    ds_a = _make_ds("REG_A", [("3", "OUT", PinRole.POWER_OUT)])
    ds_b = _make_ds("REG_B", [("3", "OUT", PinRole.POWER_OUT)])
    ref_map = _make_ref_map([("REG_A", "U1", ds_a), ("REG_B", "U2", ds_b)])
    netlist = [_make_net("VOUT", "power", [("U1", "OUT", "3"), ("U2", "OUT", "3")])]
    result = verify_schematic(netlist, ref_map)
    assert len(result.critical_violations) > 0
    assert all(v.severity == "CRITICAL" for v in result.critical_violations)
