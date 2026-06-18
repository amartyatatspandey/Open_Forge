"""Layout specification generation from schematic and KG rules."""

from __future__ import annotations

import logging

from src.config import Config
from src.layout._schemas import LayoutSpec
from src.layout.board_spec_selector import select_board_spec
from src.layout.constraint_collector import collect_constraints
from src.layout.group_builder import build_groups
from src.layout.routing_hint_generator import generate_routing_hints
from src.schemas.datasheet import ComponentDatasheet
from src.schemas.kg import DesignSubgraph
from src.schemas.nir import BoardSpec
from src.schematic._schemas import SchematicGraph

logger = logging.getLogger(__name__)

__all__ = ["LayoutSpec", "generate_layout_spec"]


def generate_layout_spec(
    schematic: SchematicGraph,
    datasheets: list[ComponentDatasheet],
    subgraph: DesignSubgraph,
    config: Config,
) -> LayoutSpec:
    """
    Generate placement constraints and routing hints from schematic,
    component datasheets, and KG-4 rules.
    Never raises. Returns LayoutSpec.
    """
    _ = config

    try:
        methodology = subgraph.design_methodology
        board_spec = select_board_spec(methodology)
        placement_constraints = collect_constraints(schematic, datasheets, subgraph)
        routing_hints = generate_routing_hints(schematic.netlist, board_spec)
        component_groups = build_groups(schematic.blocks)

        return LayoutSpec(
            placement_constraints=placement_constraints,
            component_groups=component_groups,
            routing_hints=routing_hints,
            board_spec=board_spec,
        )

    except Exception as exc:
        logger.error("Layout spec generation failed: %s", exc, exc_info=True)
        return LayoutSpec(
            placement_constraints=[],
            component_groups=[],
            routing_hints=[],
            board_spec=BoardSpec(
                layers=2,
                material="FR4",
                thickness_mm=1.6,
                min_trace_width_mm=0.15,
                min_clearance_mm=0.15,
            ),
        )
