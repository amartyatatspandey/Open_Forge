"""Tests for schematic synthesis package."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.schematic import synthesize_schematic
from src.schematic._ref_mapper import build_ref_map
from src.schematic.block_classifier import classify_blocks
from src.schematic.erc import check_erc
from src.schematic.net_assigner import assign_power_nets, assign_protocol_nets
from src.schematic._schemas import SchematicGraph
from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod, PinDefinition
from src.schemas.intent import (
    BOMEntry,
    DesignMethodology,
    IntentDict,
    ValidatedBOM,
)
from src.schemas.kg import DesignSubgraph
from src.schemas.nir import NetlistEntry, PinRef


@pytest.fixture
def mock_config() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sample_intent() -> IntentDict:
    return IntentDict(
        goal="test",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt="test",
    )


def _make_datasheet(
    component_id: str,
    pins: list[PinDefinition],
    description: str = "Test IC",
) -> ComponentDatasheet:
    return ComponentDatasheet(
        component_id=component_id,
        manufacturer="TI",
        description=description,
        package="SOIC-8",
        source_pdf_hash="abc",
        extraction_method=ExtractionMethod.P1_VECTOR,
        extraction_confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
        pins=pins,
    )


def _make_bom(components: list[BOMEntry], intent: IntentDict) -> ValidatedBOM:
    return ValidatedBOM(
        design_id="test-design",
        intent=intent,
        components=components,
        total_confidence=0.9,
        review_required=False,
        created_at="2026-01-01T00:00:00Z",
    )


def _pin(
    pin_number: str,
    raw_name: str,
    normalized_function: str | None,
    pin_type: str = "io",
    confidence: float = 0.9,
) -> PinDefinition:
    return PinDefinition(
        pin_number=pin_number,
        raw_name=raw_name,
        normalized_function=normalized_function,
        normalization_confidence=confidence,
        pin_type=pin_type,
    )


class TestBuildRefMap:
    def test_links_bom_entry_to_matching_datasheet(self, sample_intent: IntentDict) -> None:
        ds = _make_datasheet("TPS62933", [_pin("1", "VIN", "POWER_INPUT")])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="regulator",
                    specific_part="TPS62933",
                    justification="main regulator",
                    source="test",
                    confidence=0.9,
                )
            ],
            sample_intent,
        )

        ref_map = build_ref_map(bom, [ds])

        assert "TPS62933" in ref_map
        assert ref_map["TPS62933"][0] == "U1"
        assert ref_map["TPS62933"][1] is ds

    def test_returns_none_datasheet_when_specific_part_missing(
        self, sample_intent: IntentDict
    ) -> None:
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U2",
                    component_type="regulator",
                    specific_part=None,
                    justification="unresolved",
                    source="test",
                    confidence=0.5,
                )
            ],
            sample_intent,
        )

        ref_map = build_ref_map(bom, [])

        assert ref_map["U2"] == ("U2", None)


class TestAssignPowerNets:
    def test_creates_vcc_net_with_power_positive_pins(self, sample_intent: IntentDict) -> None:
        ds1 = _make_datasheet("IC1", [_pin("1", "VCC", "POWER_POSITIVE")])
        ds2 = _make_datasheet("IC2", [_pin("2", "VDD", "POWER_POSITIVE")])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="mcu",
                    specific_part="IC1",
                    justification="mcu",
                    source="test",
                    confidence=0.9,
                ),
                BOMEntry(
                    ref="U2",
                    component_type="sensor",
                    specific_part="IC2",
                    justification="sensor",
                    source="test",
                    confidence=0.9,
                ),
            ],
            sample_intent,
        )
        ref_map = build_ref_map(bom, [ds1, ds2])

        nets = assign_power_nets(ref_map)
        vcc = next(n for n in nets if n.net_name == "VCC")

        assert vcc.net_type == "power"
        assert len(vcc.connections) == 2
        assert vcc.source_rule == "power_net_assignment"

    def test_creates_gnd_net_with_power_ground_pins(self, sample_intent: IntentDict) -> None:
        ds = _make_datasheet("IC1", [_pin("1", "GND", "POWER_GROUND")])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="mcu",
                    specific_part="IC1",
                    justification="mcu",
                    source="test",
                    confidence=0.9,
                )
            ],
            sample_intent,
        )
        ref_map = build_ref_map(bom, [ds])

        nets = assign_power_nets(ref_map)
        gnd = next(n for n in nets if n.net_name == "GND")

        assert gnd.net_type == "power"
        assert len(gnd.connections) == 1


class TestAssignProtocolNets:
    def test_spi_sck_shared_across_two_components(self, sample_intent: IntentDict) -> None:
        ds1 = _make_datasheet("MCU1", [_pin("1", "SCK", "SPI_CLOCK")])
        ds2 = _make_datasheet("SENSOR1", [_pin("1", "CLK", "SPI_CLOCK")])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="microcontroller",
                    specific_part="MCU1",
                    justification="mcu",
                    source="test",
                    confidence=0.9,
                ),
                BOMEntry(
                    ref="U2",
                    component_type="sensor",
                    specific_part="SENSOR1",
                    justification="sensor",
                    source="test",
                    confidence=0.9,
                ),
            ],
            sample_intent,
        )
        ref_map = build_ref_map(bom, [ds1, ds2])

        nets = assign_protocol_nets(ref_map, [])
        sck = next(n for n in nets if n.net_name == "SPI_SCK")

        assert len(sck.connections) == 2
        refs = {c.ref for c in sck.connections}
        assert refs == {"U1", "U2"}

    def test_spi_cs_unique_per_slave(self, sample_intent: IntentDict) -> None:
        ds = _make_datasheet("SLAVE1", [_pin("1", "CS", "SPI_CHIP_SELECT")])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U2",
                    component_type="sensor",
                    specific_part="SLAVE1",
                    justification="spi slave",
                    source="test",
                    confidence=0.9,
                )
            ],
            sample_intent,
        )
        ref_map = build_ref_map(bom, [ds])

        nets = assign_protocol_nets(ref_map, [])
        cs_net = next(n for n in nets if n.net_name == "SPI_CS_U2")

        assert len(cs_net.connections) == 1
        assert cs_net.connections[0].ref == "U2"


class TestClassifyBlocks:
    def test_buck_converter_in_power_block(self, sample_intent: IntentDict) -> None:
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="buck_converter",
                    specific_part="TPS62933",
                    justification="buck",
                    source="test",
                    confidence=0.9,
                )
            ],
            sample_intent,
        )

        blocks = classify_blocks(bom, [])

        power_block = next(b for b in blocks if b.block_type == "power")
        assert "U1" in power_block.refs

    def test_antenna_in_rf_block_with_isolation(self, sample_intent: IntentDict) -> None:
        bom = _make_bom(
            [
                BOMEntry(
                    ref="ANT1",
                    component_type="patch_antenna",
                    specific_part="ANT001",
                    justification="2.4GHz antenna",
                    source="test",
                    confidence=0.9,
                )
            ],
            sample_intent,
        )

        blocks = classify_blocks(bom, [])

        rf_block = next(b for b in blocks if b.block_type == "RF")
        assert "ANT1" in rf_block.refs
        assert rf_block.isolation_required is True


class TestERC:
    def test_flags_critical_when_two_outputs_share_net(self, sample_intent: IntentDict) -> None:
        ds1 = _make_datasheet("OUT1", [_pin("1", "OUT", None, pin_type="output")])
        ds2 = _make_datasheet("OUT2", [_pin("1", "OUT", None, pin_type="output")])
        bom = _make_bom(
            [
                BOMEntry(
                    ref="U1",
                    component_type="driver",
                    specific_part="OUT1",
                    justification="driver",
                    source="test",
                    confidence=0.9,
                ),
                BOMEntry(
                    ref="U2",
                    component_type="driver",
                    specific_part="OUT2",
                    justification="driver",
                    source="test",
                    confidence=0.9,
                ),
            ],
            sample_intent,
        )
        ref_map = build_ref_map(bom, [ds1, ds2])
        netlist = [
            NetlistEntry(
                net_name="CONFLICT_NET",
                net_type="signal",
                connections=[
                    PinRef(ref="U1", pin_name="OUT", pin_number="1"),
                    PinRef(ref="U2", pin_name="OUT", pin_number="1"),
                ],
                source_rule="test",
                net_confidence=0.9,
            )
        ]

        result = check_erc(netlist, ref_map)

        assert result.passed is False
        critical = [v for v in result.violations if v.rule_name == "no_output_conflict"]
        assert critical
        assert critical[0].severity == "CRITICAL"


class TestSynthesizeSchematic:
    def test_returns_schematic_graph_for_empty_bom(
        self, sample_intent: IntentDict, mock_config: MagicMock
    ) -> None:
        bom = _make_bom([], sample_intent)
        subgraph = DesignSubgraph(
            component_types=[],
            component_instances=[],
            design_rules=[],
            placement_rules=[],
            routing_hints=[],
            design_methodology="standard_SMD",
            path_confidences={},
            query_depth=0,
        )

        result = synthesize_schematic(bom, [], subgraph, mock_config)

        assert isinstance(result, SchematicGraph)
        assert result.netlist == []
        assert result.synthesis_confidence == 0.0
