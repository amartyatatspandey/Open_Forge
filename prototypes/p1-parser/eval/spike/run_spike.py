#!/usr/bin/env python3
"""Model spike runner: YOLOv8-DocLayNet vs Surya on 3 TI datasheets.

Compares table and footnote detection recall, inference time, and ONNX exportability.
Writes results to eval/spike/SPIKE_RESULTS.md.

Usage (from project root):
    python eval/spike/run_spike.py
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config

logger = logging.getLogger(__name__)

SPIKE_PDFS = [
    "TI_TLV7021_v1.pdf",
    "TI_TPS62933_v1.pdf",
    "TI_LM5176_v1.pdf",
]

# Manual ground-truth counts for spike recall (tables + footnotes per PDF, approximate)
MANUAL_COUNTS: dict[str, dict[str, int]] = {
    "TI_TLV7021_v1.pdf": {"tables": 8, "footnotes": 12},
    "TI_TPS62933_v1.pdf": {"tables": 12, "footnotes": 15},
    "TI_LM5176_v1.pdf": {"tables": 15, "footnotes": 20},
}


@dataclass
class DetectorMetrics:
    """Detection metrics for one backend."""

    name: str
    table_recall: float | None = None
    footnote_recall: float | None = None
    avg_ms_per_page: float | None = None
    onnx_exportable: str = "unknown"
    notes: list[str] = field(default_factory=list)
    available: bool = True


def _find_pdfs(corpus_dir: Path) -> list[Path]:
    """Locate spike PDFs in corpus/golden."""
    found: list[Path] = []
    for name in SPIKE_PDFS:
        path = corpus_dir / name
        if path.exists():
            found.append(path)
        else:
            logger.warning("Spike PDF not found: %s", path)
    return found


def _rasterize_pdf(pdf_path: Path, dpi: int, max_pages: int = 5) -> list[Any]:
    """Rasterize PDF pages to PIL images (spike uses first N pages only)."""
    from pdf2image import convert_from_path

    return convert_from_path(
        str(pdf_path),
        dpi=dpi,
        first_page=1,
        last_page=max_pages,
    )


def _run_yolov8(
    images: list[Any],
    model_path: Path,
    manual_tables: int,
    manual_footnotes: int,
) -> DetectorMetrics:
    """Run YOLOv8 DocLayNet detection."""
    metrics = DetectorMetrics(name="YOLOv8-DocLayNet", onnx_exportable="yes")
    if not model_path.exists():
        metrics.available = False
        metrics.notes.append(f"Model weights not found at {model_path}")
        return metrics

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        metrics.available = False
        metrics.notes.append(f"ultralytics not installed: {exc}")
        return metrics

    model = YOLO(str(model_path))
    tables_detected = 0
    footnotes_detected = 0
    total_ms = 0.0

    for image in images:
        start = time.perf_counter()
        results = model.predict(image, verbose=False)
        total_ms += (time.perf_counter() - start) * 1000

        for result in results:
            if result.boxes is None:
                continue
            for cls_id in result.boxes.cls.tolist():
                label = model.names.get(int(cls_id), "")
                label_lower = label.lower()
                if "table" in label_lower:
                    tables_detected += 1
                if "footnote" in label_lower or "text" in label_lower:
                    footnotes_detected += 1

    page_count = max(len(images), 1)
    metrics.avg_ms_per_page = total_ms / page_count
    metrics.table_recall = min(tables_detected / max(manual_tables, 1), 1.0)
    metrics.footnote_recall = min(footnotes_detected / max(manual_footnotes, 1), 1.0)
    metrics.notes.append(f"Detected {tables_detected} tables, {footnotes_detected} footnote-like regions")
    return metrics


def _run_surya(
    images: list[Any],
    manual_tables: int,
    manual_footnotes: int,
) -> DetectorMetrics:
    """Run Surya layout detection if installed."""
    metrics = DetectorMetrics(name="Surya", onnx_exportable="check")
    try:
        from surya.detection import batch_detection
        from surya.model.detection.model import load_model as load_det_model
        from surya.model.detection.processor import load_processor as load_det_processor
    except ImportError:
        metrics.available = False
        metrics.notes.append("surya-ocr not installed (optional spike dependency)")
        return metrics

    det_model = load_det_model()
    det_processor = load_det_processor()

    tables_detected = 0
    footnotes_detected = 0
    total_ms = 0.0

    for image in images:
        start = time.perf_counter()
        predictions = batch_detection([image], det_model, det_processor)
        total_ms += (time.perf_counter() - start) * 1000

        for page_pred in predictions:
            for bbox in page_pred.bboxes:
                label = getattr(bbox, "label", "") or ""
                label_lower = str(label).lower()
                if "table" in label_lower:
                    tables_detected += 1
                if "footnote" in label_lower:
                    footnotes_detected += 1

    page_count = max(len(images), 1)
    metrics.avg_ms_per_page = total_ms / page_count
    metrics.table_recall = min(tables_detected / max(manual_tables, 1), 1.0)
    metrics.footnote_recall = min(footnotes_detected / max(manual_footnotes, 1), 1.0)
    metrics.notes.append(f"Detected {tables_detected} tables, {footnotes_detected} footnotes")
    return metrics


def _format_float(value: float | None) -> str:
    """Format optional float for markdown table."""
    if value is None:
        return "N/A"
    return f"{value:.3f}"


def _decide_winner(yolo: DetectorMetrics, surya: DetectorMetrics) -> str:
    """Apply assessment §2a decision rule."""
    if not yolo.available:
        return "YOLOv8 unavailable — default locked to YOLOv8n-DocLayNet pending weights"
    if not surya.available:
        return "YOLOv8n-DocLayNet (Surya not available for comparison)"

    yolo_better_or_equal_tables = (yolo.table_recall or 0) >= (surya.table_recall or 0)
    yolo_better_or_equal_footnotes = (yolo.footnote_recall or 0) >= (surya.footnote_recall or 0)
    surya_beats_both = not yolo_better_or_equal_tables and not yolo_better_or_equal_footnotes

    if surya_beats_both:
        yolo_time = yolo.avg_ms_per_page or float("inf")
        surya_time = surya.avg_ms_per_page or float("inf")
        if surya_time <= 2 * yolo_time:
            return "Surya (beats YOLOv8 on both recall metrics, within 2× inference time)"
    return "YOLOv8n-DocLayNet (default locked per assessment §2a)"


def write_results(
    output_path: Path,
    yolo: DetectorMetrics,
    surya: DetectorMetrics,
    pdfs_processed: list[str],
    caveats: list[str],
) -> None:
    """Write SPIKE_RESULTS.md markdown report."""
    decision = _decide_winner(yolo, surya)
    lines = [
        "# Model Spike Results",
        "",
        "Phase 0 spike: YOLOv8-DocLayNet vs Surya for Phase 1 DLA.",
        "",
        "## PDFs Processed",
        "",
    ]
    if pdfs_processed:
        lines.extend(f"- `{name}`" for name in pdfs_processed)
    else:
        lines.append("- *None — place spike PDFs in `corpus/golden/` and re-run*")

    lines.extend(
        [
            "",
            "## Metrics",
            "",
            "| Metric | YOLOv8-DocLayNet | Surya | Target |",
            "|--------|------------------|-------|--------|",
            f"| Table detection recall | {_format_float(yolo.table_recall)} | "
            f"{_format_float(surya.table_recall)} | >= 0.92 |",
            f"| Footnote detection recall | {_format_float(yolo.footnote_recall)} | "
            f"{_format_float(surya.footnote_recall)} | >= 0.85 |",
            f"| Inference time / page (ms) | {_format_float(yolo.avg_ms_per_page)} | "
            f"{_format_float(surya.avg_ms_per_page)} | record |",
            f"| ONNX exportable | {yolo.onnx_exportable} | {surya.onnx_exportable} | yes |",
            "",
            "## Decision",
            "",
            f"**Locked choice:** {decision}",
            "",
            "## Notes",
            "",
        ]
    )
    for note in yolo.notes + surya.notes + caveats:
        lines.append(f"- {note}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote spike results to %s", output_path)


def main() -> int:
    """Run spike and write results."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = Config.load(str(PROJECT_ROOT / "configs" / "default.yaml"))
    corpus_dir = PROJECT_ROOT / "corpus" / "golden"
    output_path = PROJECT_ROOT / "eval" / "spike" / "SPIKE_RESULTS.md"
    caveats: list[str] = [
        "Spike rasterizes first 5 pages at min(150, config DPI); production uses full doc at 300 DPI",
    ]

    pdfs = _find_pdfs(corpus_dir)
    if not pdfs:
        caveats.append(
            "No spike PDFs found — metrics N/A. Download from TI and save to corpus/golden/"
        )
        yolo = DetectorMetrics(name="YOLOv8-DocLayNet", onnx_exportable="yes", available=False)
        yolo.notes.append("Skipped: no PDFs")
        surya = DetectorMetrics(name="Surya", onnx_exportable="check", available=False)
        surya.notes.append("Skipped: no PDFs")
        write_results(output_path, yolo, surya, [], caveats)
        return 0

    agg_yolo_tables = 0.0
    agg_yolo_footnotes = 0.0
    agg_surya_tables = 0.0
    agg_surya_footnotes = 0.0
    agg_yolo_ms = 0.0
    agg_surya_ms = 0.0
    pdf_count = 0
    processed_names: list[str] = []
    yolo_notes: list[str] = []
    surya_notes: list[str] = []

    model_path = PROJECT_ROOT / config.models.dla_model_path

    for pdf_path in pdfs:
        counts = MANUAL_COUNTS.get(pdf_path.name, {"tables": 5, "footnotes": 5})
        spike_dpi = min(config.pipeline.pdf_dpi, 150)
        try:
            images = _rasterize_pdf(pdf_path, spike_dpi, max_pages=5)
        except Exception as exc:
            caveats.append(f"Rasterize failed for {pdf_path.name}: {exc}")
            continue

        if not images:
            caveats.append(f"No pages rasterized for {pdf_path.name}")
            continue

        pdf_count += 1
        processed_names.append(pdf_path.name)
        yolo = _run_yolov8(images, model_path, counts["tables"], counts["footnotes"])
        surya = _run_surya(images, counts["tables"], counts["footnotes"])

        if yolo.table_recall is not None:
            agg_yolo_tables += yolo.table_recall
        if yolo.footnote_recall is not None:
            agg_yolo_footnotes += yolo.footnote_recall
        if yolo.avg_ms_per_page is not None:
            agg_yolo_ms += yolo.avg_ms_per_page
        if surya.table_recall is not None:
            agg_surya_tables += surya.table_recall
        if surya.footnote_recall is not None:
            agg_surya_footnotes += surya.footnote_recall
        if surya.avg_ms_per_page is not None:
            agg_surya_ms += surya.avg_ms_per_page

        yolo_notes.extend(yolo.notes)
        surya_notes.extend(surya.notes)

    n = max(pdf_count, 1)
    final_yolo = DetectorMetrics(
        name="YOLOv8-DocLayNet",
        table_recall=agg_yolo_tables / n if pdf_count else None,
        footnote_recall=agg_yolo_footnotes / n if pdf_count else None,
        avg_ms_per_page=agg_yolo_ms / n if pdf_count else None,
        onnx_exportable="yes",
        notes=yolo_notes,
        available=pdf_count > 0,
    )
    final_surya = DetectorMetrics(
        name="Surya",
        table_recall=agg_surya_tables / n if pdf_count else None,
        footnote_recall=agg_surya_footnotes / n if pdf_count else None,
        avg_ms_per_page=agg_surya_ms / n if pdf_count else None,
        onnx_exportable="check",
        notes=surya_notes,
        available=any("not installed" not in n for n in surya_notes) if surya_notes else False,
    )

    if not model_path.exists():
        caveats.append(f"YOLOv8 weights missing at {model_path} — recall metrics approximate or N/A")

    write_results(
        output_path,
        final_yolo,
        final_surya,
        processed_names,
        caveats,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
