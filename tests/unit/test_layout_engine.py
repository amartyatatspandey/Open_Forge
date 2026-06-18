"""Tests for layout specification generation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.layout import LayoutSpec, generate_layout_spec
from src.layout.board_spec_selector import select_board_spec
from src.layout.constraint_collector import collect_constraints
from src.layout.group_builder import build_groups
from src.layout.routing_hint_generator import generate_routing_hints
from src.schematic._schemas import ERCResult, FunctionalBlock, SchematicGraph
from src.schemas.datasheet import (
    ComponentDatasheet,
    ExtractionMethod,
    PlacementConstraint as DSConstraint,
)
from src.schemas.kg import DesignSubgraph, KGNode, KGNodeType
from src.schemas.nir import BoardSpec, NetlistEntry, PinRef


@pytest.fixture
def mock_config() -> MagicMock:
    return MagicMock()


@pytest.fixture
def empty_schematic() -> SchematicGraph:
    return SchematicGraph(
        netlist=[],
        blocks=[],
        erc_result=ERCResult(passed=True, violations=[], rules_checked=0),
        synthesis_confidence=0.0,
        unresolved_pins=[],
        review_flags=[],
    )


def _ds_constraint(
    subject: str,
    relative_to: str,
    max_distance_mm: float,
    hard: bool = True,
) -> DSConstraint:
    return DSConstraint(
        constraint_type="proximity",
        subject=subject,
        relative_to=relative_to,
        relative_to_type="pin",
        max_distance_mm=max_distance_mm,
        hard=hard,
        source_sentence="Place near pin",
        confidence=0.95,
    )


def _kg_placement_rule(
    subject: str,
    relative_to: str,
    max_distance_mm: float,
) -> KGNode:
    return KGNode(
        id=f"placement_rule:{subject}:{relative_to}",
        node_type=KGNodeType.PLACEMENT_RULE,
        layer=4,
        label=f"rule_{subject}",
        properties={
            "constraint_type": "proximity",
            "subject": subject,
            "relative_to": relative_to,
            "relative_to_type": "pin",
            "max_distance_mm": max_distance_mm,
            "hard": True,
        },
        source="kg4",
        confidence=0.8,
        extraction_method=ExtractionMethod.MANUAL,
        created_at="2026-01-01T00:00:00Z",
    )


def _make_datasheet(
    component_id: str,
    layout_constraints: list[DSConstraint],
) -> ComponentDatasheet:
    return ComponentDatasheet(
        component_id=component_id,
        manufacturer="TI",
        description="Test IC",
        package="SOIC-8",
        source_pdf_hash="abc",
        extraction_method=ExtractionMethod.P1_VECTOR,
        extraction_confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
        layout_constraints=layout_constraints,
    )


def _empty_subgraph(methodology: str = "standard_SMD") -> DesignSubgraph:
    return DesignSubgraph(
        component_types=[],
        component_instances=[],
        design_rules=[],
        placement_rules=[],
        routing_hints=[],
        design_methodology=methodology,
        path_confidences={},
        query_depth=0,
    )


class TestCollectConstraints:
    def test_phase5_overrides_kg4_for_same_subject(self, empty_schematic: SchematicGraph) -> None:
        datasheet = _make_datasheet(
            "TPS62933",
            [_ds_constraint("C1", "U1.VCC", max_distance_mm=2.0)],
        )
        subgraph = _empty_subgraph()
        subgraph.placement_rules.append(
            _kg_placement_rule("C1", "U1.VCC", max_distance_mm=10.0)
        )

        constraints = collect_constraints(empty_schematic, [datasheet], subgraph)

        assert len(constraints) == 1
        assert constraints[0].ref == "C1"
        assert constraints[0].max_distance_mm == 2.0
        assert constraints[0].source.startswith("phase5:")

    def test_kg4_used_when_no_phase5_constraint(self, empty_schematic: SchematicGraph) -> None:
        subgraph = _empty_subgraph()
        subgraph.placement_rules.append(
            _kg_placement_rule("C2", "U1.GND", max_distance_mm=5.0)
        )

        constraints = collect_constraints(empty_schematic, [], subgraph)

        assert len(constraints) == 1
        assert constraints[0].ref == "C2"
        assert constraints[0].max_distance_mm == 5.0
        assert constraints[0].source == "kg4"


class TestRoutingHints:
    def test_rf_net_generates_impedance_controlled_hint(self) -> None:
        board_spec = BoardSpec(
            layers=2,
            material="FR4",
            thickness_mm=1.6,
            min_trace_width_mm=0.15,
            min_clearance_mm=0.15,
        )
        netlist = [
            NetlistEntry(
                net_name="RF_OUT",
                net_type="RF",
                connections=[PinRef(ref="ANT1", pin_name="RF", pin_number="1")],
                source_rule="test",
                net_confidence=0.9,
            )
        ]

        hints = generate_routing_hints(netlist, board_spec)

        assert len(hints) == 1
        assert hints[0].hint_type == "impedance_controlled"
        assert hints[0].nets == ["RF_OUT"]
        assert hints[0].value == 50.0

    def test_clock_net_generates_isolation_hint(self) -> None:
        board_spec = select_board_spec("standard_SMD")
        netlist = [
            NetlistEntry(
                net_name="SPI_SCK",
                net_type="clock",
                connections=[PinRef(ref="U1", pin_name="SCK", pin_number="1")],
                source_rule="test",
                net_confidence=0.9,
            )
        ]

        hints = generate_routing_hints(netlist, board_spec)

        assert len(hints) == 1
        assert hints[0].hint_type == "isolation"
        assert hints[0].nets == ["SPI_SCK"]


class TestBoardSpecSelector:
    def test_rf_highfreq_selects_rogers(self) -> None:
        spec = select_board_spec("RF_highfreq")
        assert spec.material == "Rogers_4003C"

    def test_standard_smd_selects_fr4(self) -> None:
        spec = select_board_spec("standard_SMD")
        assert spec.material == "FR4"


class TestGroupBuilder:
    def test_isolation_required_propagates(self) -> None:
        blocks = [
            FunctionalBlock(
                name="rf_block",
                refs=["ANT1", "U3"],
                block_type="RF",
                isolation_required=True,
            )
        ]

        groups = build_groups(blocks)

        assert len(groups) == 1
        assert groups[0].isolation_required is True
        assert groups[0].keep_together is True


class TestGenerateLayoutSpec:
    def test_returns_layout_spec_for_empty_inputs(
        self, empty_schematic: SchematicGraph, mock_config: MagicMock
    ) -> None:
        result = generate_layout_spec(
            empty_schematic,
            [],
            _empty_subgraph(),
            mock_config,
        )

        assert isinstance(result, LayoutSpec)
        assert result.placement_constraints == []
        assert result.component_groups == []
        assert result.routing_hints == []
        assert result.board_spec.material == "FR4"
