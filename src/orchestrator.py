"""OpenForge E2E orchestrator — single prompt-to-files entry point."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from src.config import Config
from src.datasheet.pipeline import DatasheetPipelineError, parse_datasheet
from src.intent.pipeline import run_intent_pipeline
from src.knowledge_graph import query_graph
from src.knowledge_graph.graph import KnowledgeGraph
from src.knowledge_graph.pin_normalizer import normalize_pins
from src.output import OutputResult, run_output_pipeline
from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod
from src.schemas.intent import DesignMethodology, ImprovedIntentDict, ValidatedBOM
from src.schemas.kg import DesignSubgraph
from src.schemas.nir import NIR
from src.synthesis.pipeline import _failure_nir, run_synthesis_pipeline

logger = logging.getLogger(__name__)

__all__ = ["E2EResult", "run_e2e"]


class E2EResult(BaseModel):
    design_id: str
    prompt: str
    validated_bom: ValidatedBOM
    datasheets_parsed: int
    datasheets_skipped: int
    nir: NIR
    output: OutputResult
    overall_success: bool


def _resolve_pdf(component_id: str, config: Config) -> Optional[Path]:
    # Fallback Path("corpus") when config lacks corpus_dir (e.g. partial test mocks).
    corpus = getattr(config, "corpus_dir", Path("corpus"))
    candidates = (
        corpus / "datasheets" / f"{component_id}.pdf",
        corpus / "golden" / f"{component_id}.pdf",
    )
    for path in candidates:
        if path.exists():
            return path
    return None


def _skeleton_datasheet(component_id: str) -> ComponentDatasheet:
    return ComponentDatasheet(
        component_id=component_id,
        manufacturer="",
        description="Skeleton — no PDF available",
        package="",
        source_pdf_hash="",
        electrical_parameters=[],
        absolute_max_ratings=[],
        pins=[],
        layout_constraints=[],
        extraction_method=ExtractionMethod.LLM_FALLBACK,
        extraction_confidence=0.0,
        review_required=True,
        review_flags=[f"No datasheet PDF found for {component_id}"],
        pipeline_version="skeleton",
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def _empty_bom(prompt: str) -> ValidatedBOM:
    intent = ImprovedIntentDict(
        goal="unknown",
        application="unknown",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt=prompt,
        clarification_required=True,
    )
    return ValidatedBOM(
        design_id=str(uuid.uuid4()),
        intent=intent,
        components=[],
        total_confidence=0.0,
        review_required=True,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def _failure_result(
    prompt: str,
    validated_bom: ValidatedBOM | None,
    reason: str,
) -> E2EResult:
    bom = validated_bom or _empty_bom(prompt)
    nir = _failure_nir(bom, reason)
    output = OutputResult(
        design_id=nir.design_id,
        overall_success=False,
    )
    return E2EResult(
        design_id=nir.design_id,
        prompt=prompt,
        validated_bom=bom,
        datasheets_parsed=0,
        datasheets_skipped=0,
        nir=nir,
        output=output,
        overall_success=False,
    )


def run_e2e(
    prompt: str,
    graph: KnowledgeGraph,
    output_dir: Path,
    config: Config,
) -> E2EResult:
    """
    Single entry point: natural language prompt → fabrication files.

    Steps: intent → KG re-query → datasheet parsing → pin normalisation
           → synthesis → serialization.

    Never raises. Returns E2EResult with overall_success=False on any
    internal failure. All failures are logged at ERROR level.
    """
    validated_bom: ValidatedBOM | None = None
    try:
        logger.info("Step 1: running intent pipeline")
        intent, validated_bom, _retrieval_result = run_intent_pipeline(
            prompt, graph, config
        )
        if validated_bom.review_required:
            logger.warning("BOM review_required=True; proceeding anyway")

        logger.info("Step 2: re-querying knowledge graph for subgraph")
        # run_intent_pipeline computes a subgraph internally but does not expose it.
        # Re-querying is acceptable duplication for the first E2E pass.
        subgraph: DesignSubgraph = query_graph(intent, graph, config)

        logger.info("Step 3: parsing datasheets for BOM components")
        raw_datasheets: list[ComponentDatasheet] = []
        for entry in validated_bom.components:
            component_id = entry.specific_part or entry.component_type
            pdf_path = _resolve_pdf(component_id, config)
            if pdf_path is None:
                logger.warning(
                    "No datasheet PDF found for %s; using skeleton datasheet",
                    component_id,
                )
                raw_datasheets.append(_skeleton_datasheet(component_id))
                continue

            try:
                raw_datasheets.append(
                    parse_datasheet(component_id, pdf_path, config)
                )
            except (DatasheetPipelineError, FileNotFoundError) as exc:
                logger.warning(
                    "Datasheet parse failed for %s: %s",
                    component_id,
                    exc,
                )
                raw_datasheets.append(_skeleton_datasheet(component_id))

        datasheets_skipped = sum(
            1 for ds in raw_datasheets if ds.pipeline_version == "skeleton"
        )
        datasheets_parsed = len(raw_datasheets) - datasheets_skipped

        logger.info("Step 4: normalizing pins")
        datasheets = normalize_pins(raw_datasheets, config)

        logger.info("Step 5: running synthesis pipeline")
        nir = run_synthesis_pipeline(validated_bom, datasheets, subgraph, config)

        logger.info("Step 6: running output pipeline")
        output = run_output_pipeline(nir, output_dir, config)

        result = E2EResult(
            design_id=nir.design_id,
            prompt=prompt,
            validated_bom=validated_bom,
            datasheets_parsed=datasheets_parsed,
            datasheets_skipped=datasheets_skipped,
            nir=nir,
            output=output,
            overall_success=output.overall_success,
        )
        logger.info(
            "E2E complete: design_id=%s parsed=%d skipped=%d success=%s",
            result.design_id,
            result.datasheets_parsed,
            result.datasheets_skipped,
            result.overall_success,
        )
        return result

    except Exception as exc:
        logger.error("E2E pipeline failed: %s", exc, exc_info=True)
        return _failure_result(
            prompt,
            validated_bom,
            f"E2E pipeline failed: {exc}",
        )
