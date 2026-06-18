"""Team D synthesis pipeline orchestration."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from src.config import Config
from src.layout import generate_layout_spec
from src.nir import build_nir
from src.review.queue import enqueue_nir
from src.schemas.datasheet import ComponentDatasheet
from src.schemas.intent import ValidatedBOM
from src.schemas.kg import DesignSubgraph
from src.schemas.nir import BoardSpec, NIR, ReviewFlag
from src.schematic import synthesize_schematic

logger = logging.getLogger(__name__)


def _failure_nir(bom: ValidatedBOM, reason: str) -> NIR:
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
                reason=reason,
                severity="CRITICAL",
                stage="synthesis_pipeline",
            )
        ],
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def run_synthesis_pipeline(
    bom: ValidatedBOM,
    datasheets: list[ComponentDatasheet],
    subgraph: DesignSubgraph,
    config: Config,
) -> NIR:
    """
    Full Team D pipeline: BOM + datasheets + KG subgraph → NIR.
    Orchestrates schematic synthesis → layout engine → NIR builder.
    Never raises. Returns NIR with review_required=True on failure.
    Logs each stage at INFO level with duration.
    """
    try:
        start = time.perf_counter()
        logger.info("Stage schematic synthesis starting")
        schematic = synthesize_schematic(bom, datasheets, subgraph, config)
        logger.info(
            "Stage schematic synthesis completed in %.3fs",
            time.perf_counter() - start,
        )

        start = time.perf_counter()
        logger.info("Stage layout spec generation starting")
        layout = generate_layout_spec(schematic, datasheets, subgraph, config)
        logger.info(
            "Stage layout spec generation completed in %.3fs",
            time.perf_counter() - start,
        )

        start = time.perf_counter()
        logger.info("Stage NIR build starting")
        nir = build_nir(bom, datasheets, schematic, layout, config)
        logger.info(
            "Stage NIR build completed in %.3fs",
            time.perf_counter() - start,
        )

        if nir.is_review_required():
            enqueue_nir(nir, config)

        return nir

    except Exception as exc:
        logger.error("Synthesis pipeline failed: %s", exc, exc_info=True)
        return _failure_nir(bom, f"Synthesis pipeline failed: {exc}")
