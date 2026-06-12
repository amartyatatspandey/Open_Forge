#!/usr/bin/env python3
"""Run Phase 1 DLA evaluation on golden corpus."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from eval.phase1.metrics import (  # noqa: E402
    TARGET_FOOTNOTE_RECALL,
    TARGET_SECTION_ACC,
    TARGET_TABLE_PRECISION,
    TARGET_TABLE_RECALL,
    Phase1Metrics,
    load_ground_truth,
    table_detection_metrics,
)
from src.logging_config import setup_logging
from src.phase1_dla.runner import run_phase1

logger = logging.getLogger(__name__)

GOLDEN_COMPONENTS = [
    "TI_SN74LVC1G04",
    "TI_TLV7021",
    "TI_INA219",
    "TI_LM5176",
    "TI_TPS62933",
]


def _format_pct(value: float) -> str:
    """Format a ratio as percentage string."""
    return f"{value:.1%}"


def _write_report(results: list[Phase1Metrics], report_path: Path) -> None:
    """Write markdown evaluation report."""
    lines = [
        "# Phase 1 DLA Evaluation Results",
        "",
        "| Component | Recall | Precision | Footnote Recall | Section Acc | Pass |",
        "|---|---|---|---|---|---|",
    ]
    for m in results:
        lines.append(
            f"| {m.component_id} | {_format_pct(m.table_recall)} | "
            f"{_format_pct(m.table_precision)} | {_format_pct(m.footnote_recall)} | "
            f"{_format_pct(m.section_classification_acc)} | "
            f"{'PASS' if m.passed else 'FAIL'} |"
        )
    all_passed = all(m.passed for m in results)
    lines.extend(
        [
            "",
            "## Targets",
            f"- Table recall: >= {_format_pct(TARGET_TABLE_RECALL)}",
            f"- Table precision: >= {_format_pct(TARGET_TABLE_PRECISION)}",
            f"- Footnote recall: >= {_format_pct(TARGET_FOOTNOTE_RECALL)}",
            f"- Section classification: >= {_format_pct(TARGET_SECTION_ACC)}",
            "",
            f"## Overall: {'PASS' if all_passed else 'NEEDS TUNING'}",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote report to %s", report_path)


def run_evaluation(corpus_dir: Path, report_path: Path) -> int:
    """Evaluate Phase 1 on all golden datasheets.

    Returns:
        Exit code 0 if all pass, 1 otherwise.
    """
    results: list[Phase1Metrics] = []
    for component_id in GOLDEN_COMPONENTS:
        pdf_path = corpus_dir / f"{component_id}_v1.pdf"
        gt_path = corpus_dir / f"{component_id}_v1_ground_truth.json"
        if not pdf_path.exists():
            logger.error("PDF not found: %s", pdf_path)
            return 1
        if not gt_path.exists():
            logger.error("Ground truth not found: %s", gt_path)
            return 1

        logger.info("Evaluating %s...", component_id)
        output = run_phase1(pdf_path)
        gt = load_ground_truth(gt_path)
        metrics = table_detection_metrics(output, gt)
        results.append(metrics)
        print(f"{component_id}:")
        print(f"  Table recall:     {_format_pct(metrics.table_recall)}")
        print(f"  Table precision:  {_format_pct(metrics.table_precision)}")
        print(f"  Footnote recall:  {_format_pct(metrics.footnote_recall)}")
        print(f"  Section acc:      {_format_pct(metrics.section_classification_acc)}")
        print(f"  Detections:       {metrics.num_detections} (GT sections: {metrics.num_gt_sections})")
        print(f"  Status:           {'PASS' if metrics.passed else 'FAIL'}")
        print()

    _write_report(results, report_path)
    return 0 if all(m.passed for m in results) else 1


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Phase 1 DLA golden corpus evaluation")
    parser.add_argument("--corpus", default="corpus/golden", help="Golden corpus directory")
    parser.add_argument(
        "--report",
        default="eval/phase1/PHASE1_RESULTS.md",
        help="Output markdown report path",
    )
    args = parser.parse_args()

    setup_logging()
    return run_evaluation(Path(args.corpus), Path(args.report))


if __name__ == "__main__":
    sys.exit(main())
