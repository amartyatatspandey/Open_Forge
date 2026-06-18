"""Tests for NIR builder and validator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.layout._schemas import LayoutSpec
from src.nir import build_nir
from src.nir.builder import assemble_nir
from src.nir.validator import validate_nir
from src.schematic._schemas import ERCResult, SchematicGraph
from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod
from src.schemas.intent import (
    BOMEntry,
    DesignMethodology,
    IntentDict,
    ValidatedBOM,
)
from src.schemas.nir import BoardSpec, ComponentRef, NetlistEntry, NIR, PinRef, ReviewFlag


@pytest.fixture
def mock_config() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sample_intent() -> IntentDict:
    return IntentDict(
        goal="buck_converter",
        application="test",
        design_methodology=DesignMethodology.POWER_MANAGEMENT,
        board_type="standard_SMD",
        raw_prompt="design a buck converter",
    )


@pytest.fixture
def board_spec() -> BoardSpec:
    return BoardSpec(
        layers=2,
        material="FR4",
        thickness_mm=1.6,
        min_trace_width_mm=0.15,
        min_clearance_mm=0.15,
    )


@pytest.fixture
def empty_layout(board_spec: BoardSpec) -> LayoutSpec:
    return LayoutSpec(
        placement_constraints=[],
        component_groups=[],
        routing_hints=[],
        board_spec=board_spec,
    )


def _make_bom(
    components: list[BOMEntry],
    intent: IntentDict,
    review_flags: list[str] | None = None,
) -> ValidatedBOM:
    return ValidatedBOM(
        design_id="design-001",
        intent=intent,
        components=components,
        total_confidence=0.9,
        review_required=False,
        review_flags=review_flags or [],
        created_at="2026-01-01T00:00:00Z",
    )


def _make_datasheet(component_id: str, package: str = "SOIC-8") -> ComponentDatasheet:
    return ComponentDatasheet(
        component_id=component_id,
        manufacturer="TI",
        description="Test IC",
        package=package,
        source_pdf_hash="abc",
        extraction_method=ExtractionMethod.P1_VECTOR,
        extraction_confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
    )


def _make_schematic(
    netlist: list[NetlistEntry] | None = None,
    review_flags: list[ReviewFlag] | None = None,
) -> SchematicGraph:
    return SchematicGraph(
        netlist=netlist or [],
        blocks=[],
        erc_result=ERCResult(passed=True, violations=[], rules_checked=0),
        synthesis_confidence=0.9,
        unresolved_pins=[],
        review_flags=review_flags or [],
    )


class TestBuildNir:
    def test_returns_nir_for_minimal_fixture(
        self,
        sample_intent: IntentDict,
        empty_layout: LayoutSpec,
        mock_config: MagicMock,
    ) -> None:
        bom = _make_bom([], sample_intent)
        schematic = _make_schematic()

        result = build_nir(bom, [], schematic, empty_layout, mock_config)

        assert isinstance(result, NIR)
        assert result.design_id == "design-001"

    def test_component_ref_matches_bom_entry(
        self,
        sample_intent: IntentDict,
        empty_layout: LayoutSpec,
    ) -> None:
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="regulator",
                    specific_part="TPS62933",
                    justification="main regulator",
                    source="kg",
                    confidence=0.92,
                )
            ],
            sample_intent,
        )
        datasheet = _make_datasheet("TPS62933", package="SOT-23-5")
        schematic = _make_schematic()

        nir = assemble_nir(bom, [datasheet], schematic, empty_layout)

        assert len(nir.components) == 1
        assert nir.components[0].ref == "U1"
        assert nir.components[0].component_id == "TPS62933"
        assert nir.components[0].footprint == "SOT-23-5"

    def test_netlist_unchanged_from_schematic(
        self,
        sample_intent: IntentDict,
        empty_layout: LayoutSpec,
    ) -> None:
        net = NetlistEntry(
            net_name="VCC",
            net_type="power",
            connections=[PinRef(ref="U1", pin_name="VCC", pin_number="1")],
            source_rule="power_net_assignment",
            net_confidence=0.95,
        )
        schematic = _make_schematic(netlist=[net])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="regulator",
                    specific_part="TPS62933",
                    justification="regulator",
                    source="kg",
                    confidence=0.9,
                )
            ],
            sample_intent,
        )

        nir = assemble_nir(bom, [_make_datasheet("TPS62933")], schematic, empty_layout)

        assert nir.netlist == schematic.netlist
        assert nir.netlist[0].net_name == "VCC"

    def test_confidence_scores_from_bom(
        self,
        sample_intent: IntentDict,
        empty_layout: LayoutSpec,
    ) -> None:
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="regulator",
                    specific_part="TPS62933",
                    justification="regulator",
                    source="kg",
                    confidence=0.88,
                )
            ],
            sample_intent,
        )
        schematic = _make_schematic()

        nir = assemble_nir(bom, [_make_datasheet("TPS62933")], schematic, empty_layout)

        assert nir.confidence_scores == {"U1": 0.88}

    def test_net_confidence_from_schematic(
        self,
        sample_intent: IntentDict,
        empty_layout: LayoutSpec,
    ) -> None:
        net = NetlistEntry(
            net_name="GND",
            net_type="power",
            connections=[PinRef(ref="U1", pin_name="GND", pin_number="2")],
            source_rule="power_net_assignment",
            net_confidence=0.87,
        )
        schematic = _make_schematic(netlist=[net])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="regulator",
                    specific_part="TPS62933",
                    justification="regulator",
                    source="kg",
                    confidence=0.9,
                )
            ],
            sample_intent,
        )

        nir = assemble_nir(bom, [_make_datasheet("TPS62933")], schematic, empty_layout)

        assert nir.net_confidence == {"GND": 0.87}

    def test_review_flags_merged_from_all_sources(
        self,
        sample_intent: IntentDict,
        empty_layout: LayoutSpec,
    ) -> None:
        schematic_flag = ReviewFlag(
            item_ref="U1.1",
            reason="schematic issue",
            severity="WARNING",
            stage="schematic_synthesis",
        )
        schematic = _make_schematic(review_flags=[schematic_flag])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="regulator",
                    specific_part="TPS62933",
                    justification="regulator",
                    source="kg",
                    confidence=0.9,
                )
            ],
            sample_intent,
            review_flags=["bom warning"],
        )

        raw = assemble_nir(bom, [_make_datasheet("TPS62933")], schematic, empty_layout)
        raw_with_bad_net = raw.model_copy(
            update={
                "netlist": raw.netlist
                + [
                    NetlistEntry(
                        net_name="BAD",
                        net_type="signal",
                        connections=[
                            PinRef(ref="U99", pin_name="OUT", pin_number="1"),
                        ],
                        source_rule="test",
                        net_confidence=0.5,
                    )
                ]
            }
        )
        validated = validate_nir(raw_with_bad_net)

        stages = {flag.stage for flag in validated.review_flags}
        assert "schematic_synthesis" in stages
        assert "bom_generation" in stages
        assert "nir_validation" in stages


class TestValidateNir:
    def _base_nir(self) -> NIR:
        return NIR(
            design_id="design-001",
            prompt="test",
            design_methodology="standard_SMD",
            components=[
                ComponentRef(
                    ref="U1",
                    component_id="TPS62933",
                    component_type="regulator",
                    footprint="SOIC-8",
                    datasheet_confidence=0.9,
                    justification="regulator",
                )
            ],
            netlist=[],
            placement_constraints=[],
            board_spec=BoardSpec(
                layers=2,
                material="FR4",
                thickness_mm=1.6,
                min_trace_width_mm=0.15,
                min_clearance_mm=0.15,
            ),
            created_at="2026-01-01T00:00:00Z",
        )

    def test_adds_critical_flag_for_unknown_netlist_ref(self) -> None:
        nir = self._base_nir().model_copy(
            update={
                "netlist": [
                    NetlistEntry(
                        net_name="SIG",
                        net_type="signal",
                        connections=[
                            PinRef(ref="U99", pin_name="OUT", pin_number="1"),
                        ],
                        source_rule="test",
                        net_confidence=0.8,
                    )
                ]
            }
        )

        validated = validate_nir(nir)

        critical = [f for f in validated.review_flags if f.severity == "CRITICAL"]
        assert any("unknown ref U99" in f.reason for f in critical)

    def test_adds_warning_for_single_connection_net(self) -> None:
        nir = self._base_nir().model_copy(
            update={
                "netlist": [
                    NetlistEntry(
                        net_name="SIG",
                        net_type="signal",
                        connections=[
                            PinRef(ref="U1", pin_name="OUT", pin_number="1"),
                        ],
                        source_rule="test",
                        net_confidence=0.8,
                    )
                ]
            }
        )

        validated = validate_nir(nir)

        warnings = [f for f in validated.review_flags if f.severity == "WARNING"]
        assert any("only 1 connection" in f.reason for f in warnings)

    def test_never_mutates_input_nir(self) -> None:
        nir = self._base_nir().model_copy(
            update={
                "netlist": [
                    NetlistEntry(
                        net_name="SIG",
                        net_type="signal",
                        connections=[
                            PinRef(ref="U99", pin_name="OUT", pin_number="1"),
                        ],
                        source_rule="test",
                        net_confidence=0.8,
                    )
                ]
            }
        )
        original_flag_count = len(nir.review_flags)

        validated = validate_nir(nir)

        assert validated is not nir
        assert len(nir.review_flags) == original_flag_count
        assert len(validated.review_flags) > original_flag_count

    def test_is_review_required_with_critical_flag(self) -> None:
        nir = self._base_nir().model_copy(
            update={
                "netlist": [
                    NetlistEntry(
                        net_name="SIG",
                        net_type="signal",
                        connections=[
                            PinRef(ref="U99", pin_name="OUT", pin_number="1"),
                        ],
                        source_rule="test",
                        net_confidence=0.8,
                    )
                ]
            }
        )

        validated = validate_nir(nir)

        assert validated.is_review_required() is True
