#!/usr/bin/env python3
"""Run Phase 2 TSR evaluation on golden corpus (metrics deferred)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from eval.phase2.metrics import (  # noqa: E402
    TARGET_CELL_ACCURACY,
    TARGET_MERGED_CELL_ACCURACY,
)
from src.logging_config import setup_logging
from src.phase1_dla.runner import run_phase1
from src.phase2_tsr.runner import run_phase2

logger = logging.getLogger(__name__)

GOLDEN_COMPONENTS = [
    "TI_SN74LVC1G04",
    "TI_TLV7021",
    "TI_INA219",
    "TI_LM5176",
    "TI_TPS62933",
]


def main() -> int:
    """Run Phase 1 + Phase 2 on golden PDFs; save outputs; defer metrics."""
    parser = argparse.ArgumentParser(description="Phase 2 TSR golden corpus eval")
    parser.add_argument("--corpus", type=Path, default=Path("corpus/golden"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("eval/phase2/PHASE2_RESULTS.md"),
    )
    parser.add_argument(
        "--save-outputs",
        action="store_true",
        help="Write golden_phase2_outputs.json",
    )
    args = parser.parse_args()

    setup_logging()
    results: list[dict] = []

    for component in GOLDEN_COMPONENTS:
        pdf_path = args.corpus / f"{component}_v1.pdf"
        if not pdf_path.exists():
            logger.warning("PDF not found: %s", pdf_path)
            continue
        logger.info("Running Phase 2 for %s...", component)
        phase1_out = run_phase1(pdf_path)
        phase2_out = run_phase2(phase1_out)
        results.append(
            {
                "component_id": component,
                "pdf_path": str(pdf_path),
                "num_grids": phase2_out.num_tables,
                "metadata": phase2_out.metadata,
            }
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 2 TSR Evaluation Results",
        "",
        "**Metrics deferred** — grid-level golden GT not yet annotated.",
        "",
        f"Targets (when GT available): cell_accuracy >= {TARGET_CELL_ACCURACY:.0%}, "
        f"merged_cell_accuracy >= {TARGET_MERGED_CELL_ACCURACY:.0%}",
        "",
        "| Component | Grids Extracted | Path A Wins | Path B Wins |",
        "|---|---|---|---|",
    ]
    for row in results:
        meta = row["metadata"]
        lines.append(
            f"| {row['component_id']} | {row['num_grids']} | "
            f"{meta.get('path_a_wins', 0)} | {meta.get('path_b_wins', 0)} |"
        )
    lines.append("")
    lines.append("## Overall: METRICS DEFERRED")
    args.report.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote report to %s", args.report)

    if args.save_outputs:
        out_path = args.report.parent / "golden_phase2_outputs.json"
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        logger.info("Wrote outputs to %s", out_path)

    print("Phase 2 eval complete. Cell-level metrics deferred until grid GT exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
