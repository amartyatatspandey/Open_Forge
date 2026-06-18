"""Unit tests for src/schemas/nir.py.

Tests Native Intermediate Representation (NIR) schema models,
including component references, netlist entries, placement constraints,
and the root NIR container with its helper methods.
"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.nir import (
    BoardSpec,
    ComponentGroup,
    ComponentRef,
    NIR,
    NetlistEntry,
    PinRef,
    PlacementConstraint,
    ReviewFlag,
    RoutingHint,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def minimal_valid_nir() -> NIR:
    """Minimal valid NIR with 2 components, 2 nets, 1 placement constraint."""
    now = datetime.now(timezone.utc).isoformat()
    return NIR(
        design_id="TEST_BUCK_001",
        prompt="Design a 3.3V buck regulator using TPS62933",
        design_methodology="buck_regulator_recipe_v1",
        components=[
            ComponentRef(
                ref="U1",
                component_id="TPS62933DRLR",
                component_type="regulator",
                footprint="SOT-23-5",
                manufacturer="Texas Instruments",
                datasheet_confidence=0.97,
                justification="3A buck converter with high efficiency",
            ),
            ComponentRef(
                ref="C1",
                component_id="GRM188R71H105KA12D",
                component_type="capacitor",
                footprint="0603",
                value="1uF",
                manufacturer="Murata",
                datasheet_confidence=0.95,
                justification="Input decoupling capacitor",
            ),
        ],
        netlist=[
            NetlistEntry(
                net_name="VIN",
                net_type="power",
                connections=[
                    PinRef(ref="U1", pin_name="VIN", pin_number="1"),
                    PinRef(ref="C1", pin_name="P1", pin_number="1"),
                ],
                source_rule="power_entry_rule",
                net_confidence=0.95,
            ),
            NetlistEntry(
                net_name="GND",
                net_type="power",
                connections=[
                    PinRef(ref="U1", pin_name="GND", pin_number="2"),
                    PinRef(ref="C1", pin_name="P2", pin_number="2"),
                ],
                source_rule="ground_rule",
                net_confidence=0.98,
            ),
        ],
        placement_constraints=[
            PlacementConstraint(
                ref="C1",
                constraint_type="proximity",
                relative_to="U1.VIN",
                relative_to_type="pin",
                max_distance_mm=5.0,
                hard=True,
                source="datasheet_layout_section",
                confidence=0.85,
            )
        ],
        board_spec=BoardSpec(
            layers=2,
            material="FR-4",
            thickness_mm=1.6,
            min_trace_width_mm=0.15,
            min_clearance_mm=0.15,
        ),
        created_at=now,
    )


@pytest.fixture
def nir_with_review_flags(minimal_valid_nir: NIR) -> NIR:
    """NIR fixture with review flags of different severities."""
    minimal_valid_nir.review_flags = [
        ReviewFlag(
            item_ref="U1",
            reason="High confidence in component identification",
            severity="INFO",
            stage="extraction",
        ),
        ReviewFlag(
            item_ref="C1",
            reason="Low confidence in value extraction",
            severity="WARNING",
            stage="datasheet_parsing",
        ),
        ReviewFlag(
            item_ref="R1",
            reason="Missing feedback resistor in design",
            severity="CRITICAL",
            stage="validation",
            suggested_resolution="Add 10kΩ feedback resistor between VOUT and FB",
        ),
    ]
    return minimal_valid_nir


@pytest.fixture
def nir_without_critical_flags(minimal_valid_nir: NIR) -> NIR:
    """NIR fixture with only WARNING and INFO flags, no CRITICAL."""
    minimal_valid_nir.review_flags = [
        ReviewFlag(
            item_ref="U1",
            reason="Component identified successfully",
            severity="INFO",
            stage="extraction",
        ),
        ReviewFlag(
            item_ref="C1",
            reason="Datasheet extraction confidence borderline",
            severity="WARNING",
            stage="datasheet_parsing",
            suggested_resolution="Verify capacitor value manually",
        ),
    ]
    return minimal_valid_nir


# =============================================================================
# NIR Validation Tests
# =============================================================================


class TestNIRValidation:
    """Tests for basic NIR validation."""

    def test_minimal_valid_nir_validates(self, minimal_valid_nir: NIR) -> None:
        """Test that the minimal valid NIR fixture validates successfully."""
        assert minimal_valid_nir.design_id == "TEST_BUCK_001"
        assert len(minimal_valid_nir.components) == 2
        assert len(minimal_valid_nir.netlist) == 2
        assert len(minimal_valid_nir.placement_constraints) == 1

    def test_nir_json_round_trip(self, minimal_valid_nir: NIR) -> None:
        """Test NIR round-trips JSON correctly."""
        json_str = minimal_valid_nir.model_dump_json()
        restored = NIR.model_validate_json(json_str)

        assert restored.design_id == minimal_valid_nir.design_id
        assert restored.prompt == minimal_valid_nir.prompt
        assert len(restored.components) == len(minimal_valid_nir.components)
        assert len(restored.netlist) == len(minimal_valid_nir.netlist)
        assert restored.created_at == minimal_valid_nir.created_at

    def test_nir_python_dict_round_trip(self, minimal_valid_nir: NIR) -> None:
        """Test NIR round-trips through Python dict."""
        data_dict = minimal_valid_nir.model_dump()
        restored = NIR.model_validate(data_dict)

        assert restored.design_id == minimal_valid_nir.design_id
        assert restored.schema_version == minimal_valid_nir.schema_version

    def test_nir_json_file_round_trip(self, minimal_valid_nir: NIR, tmp_path) -> None:
        """Test NIR serializes to/from JSON file."""
        json_path = tmp_path / "test_nir.json"

        with open(json_path, "w") as f:
            json.dump(minimal_valid_nir.model_dump(), f, indent=2)

        with open(json_path) as f:
            data = json.load(f)
        restored = NIR.model_validate(data)

        assert restored.design_id == minimal_valid_nir.design_id


# =============================================================================
# ComponentRef Tests
# =============================================================================


class TestComponentRef:
    """Tests for ComponentRef model."""

    def test_valid_instantiation(self) -> None:
        """Test valid ComponentRef instantiation."""
        comp = ComponentRef(
            ref="U1",
            component_id="TPS62933DRLR",
            component_type="regulator",
            footprint="SOT-23-5",
            manufacturer="Texas Instruments",
            datasheet_confidence=0.97,
            justification="High efficiency buck converter",
        )
        assert comp.ref == "U1"
        assert comp.component_id == "TPS62933DRLR"
        assert comp.footprint == "SOT-23-5"
        assert comp.value is None  # Optional, should be None for ICs

    def test_with_optional_value(self) -> None:
        """Test ComponentRef with value for passives."""
        cap = ComponentRef(
            ref="C1",
            component_id="GRM188R71H105KA12D",
            component_type="capacitor",
            footprint="0603",
            value="10uF",
            manufacturer="Murata",
            datasheet_confidence=0.95,
            justification="Input decoupling",
        )
        assert cap.value == "10uF"

    def test_datasheet_confidence_bounds(self) -> None:
        """Test datasheet_confidence must be in [0.0, 1.0]."""
        # Valid bounds
        ComponentRef(
            ref="U1",
            component_id="TEST",
            component_type="test",
            footprint="0603",
            datasheet_confidence=0.0,
            justification="test",
        )
        ComponentRef(
            ref="U2",
            component_id="TEST",
            component_type="test",
            footprint="0603",
            datasheet_confidence=1.0,
            justification="test",
        )

        # Invalid: negative
        with pytest.raises(ValidationError) as exc_info:
            ComponentRef(
                ref="U3",
                component_id="TEST",
                component_type="test",
                footprint="0603",
                datasheet_confidence=-0.1,
                justification="test",
            )
        assert "datasheet_confidence" in str(exc_info.value).lower()

        # Invalid: > 1.0
        with pytest.raises(ValidationError) as exc_info:
            ComponentRef(
                ref="U4",
                component_id="TEST",
                component_type="test",
                footprint="0603",
                datasheet_confidence=1.01,
                justification="test",
            )
        assert "datasheet_confidence" in str(exc_info.value).lower()


# =============================================================================
# NetlistEntry Tests
# =============================================================================


class TestNetlistEntry:
    """Tests for NetlistEntry model."""

    def test_valid_netlist_entry(self) -> None:
        """Test valid NetlistEntry instantiation."""
        net = NetlistEntry(
            net_name="VCC_3V3",
            net_type="power",
            connections=[
                PinRef(ref="U1", pin_name="VCC", pin_number="5"),
                PinRef(ref="C2", pin_name="P1", pin_number="1"),
            ],
            source_rule="power_distribution",
            net_confidence=0.95,
        )
        assert net.net_name == "VCC_3V3"
        assert net.net_type == "power"
        assert len(net.connections) == 2
        assert net.net_confidence == 0.95

    def test_net_type_literal_validation(self) -> None:
        """Test net_type accepts valid literals only."""
        valid_types = ["power", "signal", "RF", "clock", "differential", "analog"]

        for nt in valid_types:
            net = NetlistEntry(
                net_name=f"NET_{nt.upper()}",
                net_type=nt,  # type: ignore[arg-type]
                connections=[PinRef(ref="U1", pin_name="PIN", pin_number="1")],
                source_rule="test",
                net_confidence=0.9,
            )
            assert net.net_type == nt

    def test_net_type_rejects_invalid(self) -> None:
        """Test net_type rejects invalid string values."""
        with pytest.raises(ValidationError) as exc_info:
            NetlistEntry(
                net_name="INVALID",
                net_type="invalid_type",  # type: ignore[arg-type]
                connections=[PinRef(ref="U1", pin_name="PIN", pin_number="1")],
                source_rule="test",
                net_confidence=0.9,
            )
        assert "net_type" in str(exc_info.value).lower()

    def test_net_confidence_bounds(self) -> None:
        """Test net_confidence must be in [0.0, 1.0] — BS-3 fix."""
        # Valid bounds
        NetlistEntry(
            net_name="TEST",
            net_type="signal",
            connections=[PinRef(ref="U1", pin_name="PIN", pin_number="1")],
            source_rule="test",
            net_confidence=0.0,
        )
        NetlistEntry(
            net_name="TEST2",
            net_type="signal",
            connections=[PinRef(ref="U1", pin_name="PIN", pin_number="1")],
            source_rule="test",
            net_confidence=1.0,
        )

        # Invalid: negative
        with pytest.raises(ValidationError) as exc_info:
            NetlistEntry(
                net_name="TEST",
                net_type="signal",
                connections=[PinRef(ref="U1", pin_name="PIN", pin_number="1")],
                source_rule="test",
                net_confidence=-0.1,
            )
        assert "net_confidence" in str(exc_info.value).lower()

        # Invalid: > 1.0
        with pytest.raises(ValidationError) as exc_info:
            NetlistEntry(
                net_name="TEST",
                net_type="signal",
                connections=[PinRef(ref="U1", pin_name="PIN", pin_number="1")],
                source_rule="test",
                net_confidence=1.01,
            )
        assert "net_confidence" in str(exc_info.value).lower()


# =============================================================================
# PlacementConstraint Tests
# =============================================================================


class TestPlacementConstraint:
    """Tests for PlacementConstraint model."""

    def test_valid_instantiation(self) -> None:
        """Test valid PlacementConstraint instantiation."""
        pc = PlacementConstraint(
            ref="C1",
            constraint_type="proximity",
            relative_to="U1.VIN",
            relative_to_type="pin",
            max_distance_mm=5.0,
            min_distance_mm=1.0,
            layer="top",
            hard=True,
            source="datasheet_layout_section",
            confidence=0.85,
        )
        assert pc.ref == "C1"
        assert pc.constraint_type == "proximity"
        assert pc.relative_to_type == "pin"
        assert pc.max_distance_mm == 5.0
        assert pc.layer == "top"

    def test_relative_to_type_valid_literals(self) -> None:
        """Test relative_to_type accepts the three valid literals — BS-2 fix."""
        valid_types = ["component", "pin", "board_edge"]

        for rtt in valid_types:
            pc = PlacementConstraint(
                ref="U1",
                constraint_type="proximity",
                relative_to="target",
                relative_to_type=rtt,  # type: ignore[arg-type]
                source="test",
                confidence=0.8,
            )
            assert pc.relative_to_type == rtt

    def test_relative_to_type_rejects_invalid(self) -> None:
        """Test PlacementConstraint rejects relative_to_type outside the three literals."""
        with pytest.raises(ValidationError) as exc_info:
            PlacementConstraint(
                ref="U1",
                constraint_type="proximity",
                relative_to="target",
                relative_to_type="invalid_type",  # type: ignore[arg-type]
                source="test",
                confidence=0.8,
            )
        assert "relative_to_type" in str(exc_info.value).lower()

    def test_relative_to_type_rejects_empty(self) -> None:
        """Test relative_to_type rejects empty string."""
        with pytest.raises(ValidationError) as exc_info:
            PlacementConstraint(
                ref="U1",
                constraint_type="proximity",
                relative_to="target",
                relative_to_type="",  # type: ignore[arg-type]
                source="test",
                confidence=0.8,
            )
        assert "relative_to_type" in str(exc_info.value).lower()

    def test_constraint_type_valid_literals(self) -> None:
        """Test constraint_type accepts valid literals."""
        valid_types = ["proximity", "keepout", "layer", "orientation", "group"]

        for ct in valid_types:
            pc = PlacementConstraint(
                ref="U1",
                constraint_type=ct,  # type: ignore[arg-type]
                relative_to="target",
                relative_to_type="component",
                source="test",
                confidence=0.8,
            )
            assert pc.constraint_type == ct

    def test_layer_valid_literals(self) -> None:
        """Test layer accepts valid literals."""
        valid_layers = ["top", "bottom", "any"]

        for layer in valid_layers:
            pc = PlacementConstraint(
                ref="U1",
                constraint_type="layer",
                relative_to="board",
                relative_to_type="board_edge",
                layer=layer,
                source="test",
                confidence=0.8,
            )
            assert pc.layer == layer

    def test_distance_must_be_non_negative(self) -> None:
        """Test distance fields must be non-negative."""
        # Valid: zero
        pc = PlacementConstraint(
            ref="U1",
            constraint_type="proximity",
            relative_to="U2",
            relative_to_type="component",
            min_distance_mm=0.0,
            source="test",
            confidence=0.8,
        )
        assert pc.min_distance_mm == 0.0

        # Invalid: negative
        with pytest.raises(ValidationError) as exc_info:
            PlacementConstraint(
                ref="U1",
                constraint_type="proximity",
                relative_to="U2",
                relative_to_type="component",
                max_distance_mm=-5.0,
                source="test",
                confidence=0.8,
            )
        assert "max_distance_mm" in str(exc_info.value).lower()


# =============================================================================
# RoutingHint Tests
# =============================================================================


class TestRoutingHint:
    """Tests for RoutingHint model."""

    def test_valid_instantiation(self) -> None:
        """Test valid RoutingHint instantiation."""
        rh = RoutingHint(
            nets=["USB_DP", "USB_DM"],
            hint_type="differential_pair",
            value=90.0,
            unit="Ohm",
            note="90Ω differential impedance for USB 2.0",
        )
        assert rh.nets == ["USB_DP", "USB_DM"]
        assert rh.hint_type == "differential_pair"
        assert rh.value == 90.0
        assert rh.unit == "Ohm"

    def test_hint_type_valid_literals(self) -> None:
        """Test hint_type accepts all valid literals."""
        valid_hints = [
            "impedance_controlled",
            "length_matched",
            "differential_pair",
            "min_width",
            "max_length",
            "isolation",
        ]

        for ht in valid_hints:
            rh = RoutingHint(
                nets=["NET1"],
                hint_type=ht,  # type: ignore[arg-type]
                note=f"Test hint: {ht}",
            )
            assert rh.hint_type == ht


# =============================================================================
# ComponentGroup Tests
# =============================================================================


class TestComponentGroup:
    """Tests for ComponentGroup model."""

    def test_valid_instantiation(self) -> None:
        """Test valid ComponentGroup instantiation."""
        cg = ComponentGroup(
            name="Buck_Regulator_Stage",
            refs=["U1", "L1", "C1", "C2"],
            keep_together=True,
            isolation_required=False,
        )
        assert cg.name == "Buck_Regulator_Stage"
        assert cg.refs == ["U1", "L1", "C1", "C2"]
        assert cg.keep_together is True

    def test_defaults(self) -> None:
        """Test ComponentGroup default values."""
        cg = ComponentGroup(
            name="Test_Group",
            refs=["R1", "R2"],
        )
        assert cg.keep_together is True  # Default
        assert cg.isolation_required is False  # Default


# =============================================================================
# BoardSpec Tests
# =============================================================================


class TestBoardSpec:
    """Tests for BoardSpec model."""

    def test_valid_instantiation(self) -> None:
        """Test valid BoardSpec instantiation."""
        bs = BoardSpec(
            layers=4,
            material="FR-4",
            thickness_mm=1.6,
            copper_weight_oz=1.0,
            min_trace_width_mm=0.15,
            min_clearance_mm=0.15,
            min_via_drill_mm=0.3,
            surface_finish="ENIG",
        )
        assert bs.layers == 4
        assert bs.material == "FR-4"
        assert bs.thickness_mm == 1.6

    def test_layers_literal_validation(self) -> None:
        """Test layers accepts only 1, 2, 4, or 6."""
        valid_layers = [1, 2, 4, 6]

        for layer_count in valid_layers:
            bs = BoardSpec(
                layers=layer_count,  # type: ignore[arg-type]
                material="FR-4",
                thickness_mm=1.6,
                min_trace_width_mm=0.15,
                min_clearance_mm=0.15,
            )
            assert bs.layers == layer_count

    def test_layers_rejects_invalid(self) -> None:
        """Test layers rejects values other than 1, 2, 4, 6."""
        invalid_layers = [3, 5, 8, 0, -1]

        for invalid in invalid_layers:
            with pytest.raises(ValidationError):
                BoardSpec(
                    layers=invalid,  # type: ignore[arg-type]
                    material="FR-4",
                    thickness_mm=1.6,
                    min_trace_width_mm=0.15,
                    min_clearance_mm=0.15,
                )

    def test_defaults(self) -> None:
        """Test BoardSpec default values."""
        bs = BoardSpec(
            layers=2,
            material="FR-4",
            thickness_mm=1.6,
            min_trace_width_mm=0.15,
            min_clearance_mm=0.15,
        )
        assert bs.copper_weight_oz == 1.0  # Default
        assert bs.min_via_drill_mm == 0.3  # Default
        assert bs.surface_finish == "HASL"  # Default


# =============================================================================
# ReviewFlag Tests
# =============================================================================


class TestReviewFlag:
    """Tests for ReviewFlag model."""

    def test_valid_instantiation(self) -> None:
        """Test valid ReviewFlag instantiation."""
        rf = ReviewFlag(
            item_ref="U1",
            reason="Missing decoupling capacitor",
            severity="CRITICAL",
            stage="validation",
            suggested_resolution="Add 10uF capacitor near VCC pin",
        )
        assert rf.item_ref == "U1"
        assert rf.severity == "CRITICAL"
        assert rf.stage == "validation"
        assert rf.suggested_resolution is not None

    def test_severity_valid_literals(self) -> None:
        """Test severity accepts valid literals."""
        valid_severities = ["CRITICAL", "WARNING", "INFO"]

        for sev in valid_severities:
            rf = ReviewFlag(
                item_ref="TEST",
                reason="Test flag",
                severity=sev,  # type: ignore[arg-type]
                stage="test",
            )
            assert rf.severity == sev

    def test_severity_rejects_invalid(self) -> None:
        """Test severity rejects invalid values."""
        with pytest.raises(ValidationError):
            ReviewFlag(
                item_ref="TEST",
                reason="Test flag",
                severity="ERROR",  # type: ignore[arg-type]
                stage="test",
            )


# =============================================================================
# NIR Helper Method Tests
# =============================================================================


class TestNIRHelperMethods:
    """Tests for NIR helper methods."""

    def test_get_component_found(self, minimal_valid_nir: NIR) -> None:
        """Test get_component returns correct component when found."""
        comp = minimal_valid_nir.get_component("U1")
        assert comp is not None
        assert comp.ref == "U1"
        assert comp.component_id == "TPS62933DRLR"

    def test_get_component_not_found(self, minimal_valid_nir: NIR) -> None:
        """Test get_component returns None when component not found."""
        comp = minimal_valid_nir.get_component("R99")
        assert comp is None

    def test_get_net_found(self, minimal_valid_nir: NIR) -> None:
        """Test get_net returns correct net when found."""
        net = minimal_valid_nir.get_net("VIN")
        assert net is not None
        assert net.net_name == "VIN"
        assert net.net_type == "power"

    def test_get_net_not_found(self, minimal_valid_nir: NIR) -> None:
        """Test get_net returns None when net not found."""
        net = minimal_valid_nir.get_net("NONEXISTENT")
        assert net is None

    def test_critical_flags_returns_only_critical(
        self, nir_with_review_flags: NIR
    ) -> None:
        """Test critical_flags() returns only CRITICAL severity flags."""
        critical = nir_with_review_flags.critical_flags()
        assert len(critical) == 1
        assert critical[0].severity == "CRITICAL"
        assert critical[0].item_ref == "R1"

    def test_is_review_required_true_when_critical(
        self, nir_with_review_flags: NIR
    ) -> None:
        """Test is_review_required() returns True when CRITICAL flags present."""
        assert nir_with_review_flags.is_review_required() is True

    def test_is_review_required_false_when_no_critical(
        self, nir_without_critical_flags: NIR
    ) -> None:
        """Test is_review_required() returns False when no CRITICAL flags."""
        assert nir_without_critical_flags.is_review_required() is False

    def test_critical_flags_empty_when_no_flags(self, minimal_valid_nir: NIR) -> None:
        """Test critical_flags() returns empty list when no flags."""
        critical = minimal_valid_nir.critical_flags()
        assert critical == []

    def test_is_review_required_false_when_empty_flags(
        self, minimal_valid_nir: NIR
    ) -> None:
        """Test is_review_required() returns False when flags list empty."""
        assert minimal_valid_nir.is_review_required() is False


# =============================================================================
# NIR Serialization Tests
# =============================================================================


class TestNIRSerialization:
    """Tests for NIR serialization with confidence fields."""

    def test_confidence_scores_in_serialized_json(
        self, minimal_valid_nir: NIR
    ) -> None:
        """Test confidence_scores dict is present in serialized JSON."""
        # Add some confidence scores
        minimal_valid_nir.confidence_scores = {
            "U1": 0.97,
            "C1": 0.95,
        }

        data_dict = minimal_valid_nir.model_dump()

        assert "confidence_scores" in data_dict
        assert data_dict["confidence_scores"]["U1"] == 0.97
        assert data_dict["confidence_scores"]["C1"] == 0.95

    def test_net_confidence_in_serialized_json(
        self, minimal_valid_nir: NIR
    ) -> None:
        """Test net_confidence dict is present in serialized JSON — BS-3."""
        # Add some net confidence scores
        minimal_valid_nir.net_confidence = {
            "VIN": 0.95,
            "GND": 0.98,
        }

        data_dict = minimal_valid_nir.model_dump()

        assert "net_confidence" in data_dict
        assert data_dict["net_confidence"]["VIN"] == 0.95
        assert data_dict["net_confidence"]["GND"] == 0.98

    def test_both_confidence_fields_in_json_output(
        self, minimal_valid_nir: NIR
    ) -> None:
        """Test both confidence_scores and net_confidence appear in final JSON."""
        minimal_valid_nir.confidence_scores = {"U1": 0.97}
        minimal_valid_nir.net_confidence = {"VIN": 0.95}

        json_str = minimal_valid_nir.model_dump_json()
        parsed = json.loads(json_str)

        # Both fields must be present
        assert "confidence_scores" in parsed
        assert "net_confidence" in parsed

        # Values must be preserved
        assert parsed["confidence_scores"]["U1"] == 0.97
        assert parsed["net_confidence"]["VIN"] == 0.95

    def test_all_fields_present_in_json(self, minimal_valid_nir: NIR) -> None:
        """Test that all expected fields appear in JSON output."""
        json_str = minimal_valid_nir.model_dump_json()
        parsed = json.loads(json_str)

        expected_fields = [
            "schema_version",
            "design_id",
            "prompt",
            "design_methodology",
            "components",
            "netlist",
            "placement_constraints",
            "component_groups",
            "routing_hints",
            "board_spec",
            "bom",
            "justifications",
            "source_citations",
            "confidence_scores",
            "net_confidence",
            "review_flags",
            "extraction_metadata",
            "created_at",
            "pipeline_version",
        ]

        for field in expected_fields:
            assert field in parsed, f"Expected field '{field}' not in JSON output"


# =============================================================================
# Integration Tests
# =============================================================================


class TestNIRIntegration:
    """Integration tests for complete NIR workflows."""

    def test_build_complex_buck_regulator_design(self) -> None:
        """Test building a complex buck regulator NIR with all features."""
        now = datetime.now(timezone.utc).isoformat()

        # Components
        u1 = ComponentRef(
            ref="U1",
            component_id="TPS62933DRLR",
            component_type="regulator",
            footprint="SOT-23-5",
            manufacturer="Texas Instruments",
            datasheet_confidence=0.97,
            justification="High efficiency 3A buck converter",
        )
        l1 = ComponentRef(
            ref="L1",
            component_id="SRN6045-4R7M",
            component_type="inductor",
            footprint="IND_6x6",
            value="4.7uH",
            manufacturer="Bourns",
            datasheet_confidence=0.94,
            justification="4.7uH inductor for 3.3V output at 2A",
        )
        cin = ComponentRef(
            ref="C1",
            component_id="GRM188R71H105KA12D",
            component_type="capacitor",
            footprint="0603",
            value="10uF",
            manufacturer="Murata",
            datasheet_confidence=0.95,
            justification="Input decoupling",
        )
        cout = ComponentRef(
            ref="C2",
            component_id="GRM21BR71H475KE51L",
            component_type="capacitor",
            footprint="0805",
            value="47uF",
            manufacturer="Murata",
            datasheet_confidence=0.95,
            justification="Output filter capacitor",
        )

        # Nets
        vin_net = NetlistEntry(
            net_name="VIN",
            net_type="power",
            connections=[
                PinRef(ref="U1", pin_name="VIN", pin_number="1"),
                PinRef(ref="C1", pin_name="P1", pin_number="1"),
            ],
            source_rule="power_entry",
            net_confidence=0.95,
        )
        gnd_net = NetlistEntry(
            net_name="GND",
            net_type="power",
            connections=[
                PinRef(ref="U1", pin_name="GND", pin_number="2"),
                PinRef(ref="C1", pin_name="P2", pin_number="2"),
                PinRef(ref="C2", pin_name="P2", pin_number="2"),
                PinRef(ref="L1", pin_name="P2", pin_number="2"),
            ],
            source_rule="ground_plane",
            net_confidence=0.98,
        )
        sw_net = NetlistEntry(
            net_name="SW",
            net_type="signal",
            connections=[
                PinRef(ref="U1", pin_name="SW", pin_number="3"),
                PinRef(ref="L1", pin_name="P1", pin_number="1"),
            ],
            source_rule="switch_node",
            net_confidence=0.92,
        )
        vout_net = NetlistEntry(
            net_name="VOUT",
            net_type="power",
            connections=[
                PinRef(ref="U1", pin_name="VOUT", pin_number="5"),
                PinRef(ref="C2", pin_name="P1", pin_number="1"),
                PinRef(ref="L1", pin_name="P2", pin_number="2"),
            ],
            source_rule="output_power",
            net_confidence=0.94,
        )

        # Placement constraints
        cin_constraint = PlacementConstraint(
            ref="C1",
            constraint_type="proximity",
            relative_to="U1.VIN",
            relative_to_type="pin",
            max_distance_mm=5.0,
            layer="top",
            hard=True,
            source="TPS62933_datasheet_layout",
            confidence=0.88,
        )
        cout_constraint = PlacementConstraint(
            ref="C2",
            constraint_type="proximity",
            relative_to="U1.VOUT",
            relative_to_type="pin",
            max_distance_mm=5.0,
            layer="top",
            hard=True,
            source="TPS62933_datasheet_layout",
            confidence=0.88,
        )

        # Component group
        buck_group = ComponentGroup(
            name="Buck_Regulator",
            refs=["U1", "L1", "C1", "C2"],
            keep_together=True,
            isolation_required=False,
        )

        # Board spec
        board = BoardSpec(
            layers=4,
            material="FR-4",
            thickness_mm=1.6,
            copper_weight_oz=1.0,
            min_trace_width_mm=0.15,
            min_clearance_mm=0.15,
            min_via_drill_mm=0.3,
            surface_finish="ENIG",
        )

        # Build NIR
        nir = NIR(
            design_id="BUCK_3V3_2A_v1",
            prompt="Design a 3.3V buck regulator delivering 2A from 5V input",
            design_methodology="buck_regulator_standard_recipe",
            components=[u1, l1, cin, cout],
            netlist=[vin_net, gnd_net, sw_net, vout_net],
            placement_constraints=[cin_constraint, cout_constraint],
            component_groups=[buck_group],
            board_spec=board,
            confidence_scores={
                "U1": 0.97,
                "L1": 0.94,
                "C1": 0.95,
                "C2": 0.95,
            },
            net_confidence={
                "VIN": 0.95,
                "GND": 0.98,
                "SW": 0.92,
                "VOUT": 0.94,
            },
            created_at=now,
        )

        # Verify
        assert nir.design_id == "BUCK_3V3_2A_v1"
        assert len(nir.components) == 4
        assert len(nir.netlist) == 4
        assert len(nir.placement_constraints) == 2
        assert len(nir.component_groups) == 1

        # Test lookups
        u1_lookup = nir.get_component("U1")
        assert u1_lookup is not None
        assert u1_lookup.component_id == "TPS62933DRLR"

        vout_lookup = nir.get_net("VOUT")
        assert vout_lookup is not None
        assert len(vout_lookup.connections) == 3

        # Test no critical flags
        assert nir.is_review_required() is False

        # Test JSON round-trip
        json_str = nir.model_dump_json()
        restored = NIR.model_validate_json(json_str)
        assert restored.design_id == nir.design_id
        assert len(restored.components) == len(nir.components)
