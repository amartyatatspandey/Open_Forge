"""NIR assembly and validation."""

from __future__ import annotations

import logging

from src.config import Config
from src.layout._schemas import LayoutSpec
from src.nir.builder import assemble_nir
from src.nir.migrations import migrate
from src.nir.validator import validate_nir
from src.schemas.datasheet import ComponentDatasheet
from src.schemas.intent import ValidatedBOM
from src.schemas.nir import BoardSpec, NIR, ReviewFlag
from src.schematic._schemas import ERCResult, SchematicGraph

logger = logging.getLogger(__name__)

__all__ = ["build_nir", "migrate"]


def build_nir(
    bom: ValidatedBOM,
    datasheets: list[ComponentDatasheet],
    schematic: SchematicGraph,
    layout: LayoutSpec,
    config: Config,
) -> NIR:
    """
    Assemble and validate the Neutral Intermediate Representation.
    Runs all structural validation checks.
    Returns NIR with review_flags populated.
    Never raises.
    """
    _ = config

    try:
        raw_nir = assemble_nir(bom, datasheets, schematic, layout)
        return validate_nir(raw_nir)

    except Exception as exc:
        logger.error("NIR build failed: %s", exc, exc_info=True)
        return NIR(
            design_id=bom.design_id,
            prompt=bom.intent.raw_prompt,
            design_methodology=bom.intent.design_methodology.value,
            components=[],
            netlist=[],
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
            review_flags=[
                ReviewFlag(
                    item_ref=bom.design_id,
                    reason=f"NIR build failed: {exc}",
                    severity="CRITICAL",
                    stage="nir_assembly",
                )
            ],
            created_at="1970-01-01T00:00:00Z",
        )
