"""Team E output pipeline — tscircuit, KiCad, and design report generation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from src.config import Config
from src.nir.migrations import check_version
from src.output.doc_generator import generate_design_report
from src.output.kicad_serializer import KiCadMCPClient, KiCadOutput, serialize_to_kicad
from src.output.tscircuit_serializer import TSCircuitOutput, serialize_to_tscircuit
from src.schemas.nir import NIR

logger = logging.getLogger(__name__)


class OutputResult(BaseModel):
    design_id: str
    tscircuit: Optional[TSCircuitOutput] = None
    kicad: Optional[KiCadOutput] = None
    report_path: Optional[Path] = None
    overall_success: bool = False


def run_output_pipeline(
    nir: NIR,
    output_dir: Path,
    config: Config,
    mcp_client: Optional[KiCadMCPClient] = None,
) -> OutputResult:
    """
    Team E public pipeline. Runs all three serializers.
    Each serializer runs independently — failure of one
    does not block the others.
    Never raises.

    Raises ValueError if NIR schema version does not match the serializer.
    """
    check_version(nir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tscircuit_result: Optional[TSCircuitOutput] = None
    kicad_result: Optional[KiCadOutput] = None
    report_path: Optional[Path] = None

    try:
        tscircuit_result = serialize_to_tscircuit(
            nir, output_dir / "tscircuit", config
        )
    except Exception as exc:
        logger.error("tscircuit serializer failed: %s", exc)

    try:
        kicad_result = serialize_to_kicad(
            nir, output_dir / "kicad", config, mcp_client
        )
    except Exception as exc:
        logger.error("KiCad serializer failed: %s", exc)

    try:
        report_path = generate_design_report(nir, output_dir / "report", config)
    except Exception as exc:
        logger.error("Doc generator failed: %s", exc)

    overall_success = any(
        [
            tscircuit_result is not None and tscircuit_result.success,
            kicad_result is not None and kicad_result.success,
            report_path is not None,
        ]
    )

    return OutputResult(
        design_id=nir.design_id,
        tscircuit=tscircuit_result,
        kicad=kicad_result,
        report_path=report_path,
        overall_success=overall_success,
    )


__all__ = [
    "OutputResult",
    "run_output_pipeline",
    "generate_design_report",
    "serialize_to_tscircuit",
    "serialize_to_kicad",
    "TSCircuitOutput",
    "KiCadOutput",
    "KiCadMCPClient",
]
