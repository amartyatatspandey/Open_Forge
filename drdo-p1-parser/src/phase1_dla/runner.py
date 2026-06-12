"""Phase 1 orchestrator: run full DLA pipeline on a PDF."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

from PIL import Image

from src.config import Config, get_config
from src.phase1_dla.classify_section import (
    classify_section_type,
    extract_heading_text,
    position_on_page,
    scan_page_section_hints,
)
from src.phase1_dla.detect import Detection, TableDetector, crop_region
from src.phase1_dla.footnote_linker import (
    build_footnote_map,
    extract_footnotes_from_crops,
    extract_footnotes_from_pdf,
)
from src.phase1_dla.multipage_merge import merge_multipage_tables
from src.phase1_dla.pdf_offset import detect_cover_offset
from src.phase1_dla.rasterize import rasterize_pdf
from src.schemas.pipeline import BoundingBox, DetectedTable, Phase1Output
from src.utils.exceptions import DLAError

logger = logging.getLogger(__name__)


def _bbox_iou(a_bbox: BoundingBox, b_bbox: BoundingBox) -> float:
    """Compute intersection-over-union for two bounding boxes."""
    x1 = max(a_bbox.x1, b_bbox.x1)
    y1 = max(a_bbox.y1, b_bbox.y1)
    x2 = min(a_bbox.x2, b_bbox.x2)
    y2 = min(a_bbox.y2, b_bbox.y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    intersection = (x2 - x1) * (y2 - y1)
    area_a = (a_bbox.x2 - a_bbox.x1) * (a_bbox.y2 - a_bbox.y1)
    area_b = (b_bbox.x2 - b_bbox.x1) * (b_bbox.y2 - b_bbox.y1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _dedupe_detections(
    detections: list[Detection],
    iou_threshold: float,
) -> list[Detection]:
    """Remove overlapping detections, keeping highest confidence."""
    sorted_dets = sorted(detections, key=lambda d: d.confidence, reverse=True)
    kept: list[Detection] = []
    for det in sorted_dets:
        if all(_bbox_iou(det.bbox, existing.bbox) < iou_threshold for existing in kept):
            kept.append(det)
    return kept


def _table_area(table: DetectedTable) -> int:
    """Compute table bounding box area in pixels."""
    return (table.bbox.x2 - table.bbox.x1) * (table.bbox.y2 - table.bbox.y1)


def _refine_with_page_hints(
    tables: list[DetectedTable],
    page_hints: dict[int, str],
    page_heights: dict[int, int],
    min_area_ratio: float,
    max_spec_page: int,
    cover_offset: int = 0,
) -> list[DetectedTable]:
    """Filter and reclassify tables using page-level section hints."""
    refined: list[DetectedTable] = []
    for table in tables:
        if table.page_number > max_spec_page and table.page_number not in page_hints:
            continue
        page_height = page_heights.get(table.page_number, 3300)
        page_width = table.bbox.x2  # approximate; area ratio uses height primarily
        page_area = page_height * max(page_width, table.bbox.x2)
        if page_area > 0 and _table_area(table) / page_area < min_area_ratio:
            continue
        hint = page_hints.get(table.page_number)
        printed_page = table.page_number - cover_offset
        section_type = table.section_type
        if table.heading_text is None and hint:
            section_type = hint
        elif hint and table.section_type == "other":
            section_type = hint
        elif hint and printed_page <= 6 and hint == "absolute_maximum_ratings":
            section_type = hint
        refined.append(
            DetectedTable(
                crop_bytes=table.crop_bytes,
                bbox=table.bbox,
                page_number=table.page_number,
                page_range=table.page_range,
                confidence=table.confidence,
                section_type=section_type,  # type: ignore[arg-type]
                heading_text=table.heading_text,
            )
        )
    return refined


def _limit_per_section_type(
    tables: list[DetectedTable],
    max_per_section: dict[str, int],
) -> list[DetectedTable]:
    """Keep top-confidence tables per section type up to configured limits."""
    counts: dict[str, int] = {}
    kept: list[DetectedTable] = []
    for table in sorted(tables, key=lambda t: t.confidence, reverse=True):
        limit = max_per_section.get(table.section_type, 1)
        if counts.get(table.section_type, 0) >= limit:
            continue
        kept.append(table)
        counts[table.section_type] = counts.get(table.section_type, 0) + 1
    return sorted(kept, key=lambda t: (t.page_number, t.bbox.y1))


def _filter_best_per_page_section(tables: list[DetectedTable]) -> list[DetectedTable]:
    """Keep highest-confidence detection per page and section type."""
    best: dict[tuple[int, str], DetectedTable] = {}
    for table in tables:
        key = (table.page_number, table.section_type)
        if key not in best or table.confidence > best[key].confidence:
            best[key] = table
    return sorted(best.values(), key=lambda t: (t.page_number, t.bbox.y1))


def run_phase1(pdf_path: str | Path, config: Config | None = None) -> Phase1Output:
    """Run full Phase 1 DLA pipeline on a datasheet PDF.

    Args:
        pdf_path: Path to input PDF.
        config: Optional config override.

    Returns:
        Validated Phase1Output with detected tables and footnotes.

    Raises:
        DLAError: If no tables are detected or pipeline fails.
        FileNotFoundError: If PDF does not exist.
    """
    cfg = config or get_config()
    pdf_file = Path(pdf_path)
    logger.info("Phase 1 DLA starting for %s", pdf_file.name)

    page_images = rasterize_pdf(pdf_file, config=cfg)
    cover_offset = detect_cover_offset(
        pdf_file,
        expected_printed_page=cfg.phase1_dla.expected_abs_max_printed_page,
    )
    page_hints = scan_page_section_hints(pdf_file, config=cfg)
    detector = TableDetector(config=cfg)

    detected_tables: list[DetectedTable] = []
    footnote_crops: list[bytes] = []
    footnote_pages: list[int] = []
    page_heights: dict[int, int] = {}

    for page_index, image_bytes in enumerate(page_images):
        page_number = page_index + 1
        image = Image.open(io.BytesIO(image_bytes))
        page_heights[page_number] = image.height

        detections = detector.detect_page(image_bytes)
        unique_tables = _dedupe_detections(
            detections.tables,
            iou_threshold=cfg.phase1_dla.table_iou_merge_threshold,
        )

        for table_det in unique_tables:
            crop = crop_region(image_bytes, table_det.bbox)
            heading = extract_heading_text(
                pdf_file, page_number, table_det.bbox, dpi=cfg.pipeline.pdf_dpi
            )
            position = position_on_page(table_det.bbox, image.height)
            section_type = classify_section_type(
                heading, page_number, position, config=cfg
            )
            detected_tables.append(
                DetectedTable(
                    crop_bytes=crop,
                    bbox=table_det.bbox,
                    page_number=page_number,
                    page_range=(page_number, page_number),
                    confidence=table_det.confidence,
                    section_type=section_type,
                    heading_text=heading,
                )
            )

        for fn_det in detections.footnotes:
            footnote_crops.append(crop_region(image_bytes, fn_det.bbox))
            footnote_pages.append(page_number)

    if not detected_tables:
        raise DLAError(f"No tables detected in {pdf_file.name}")

    refined_tables = _refine_with_page_hints(
        detected_tables,
        page_hints=page_hints,
        page_heights=page_heights,
        min_area_ratio=cfg.phase1_dla.min_table_area_ratio,
        max_spec_page=cfg.phase1_dla.max_spec_page,
        cover_offset=cover_offset,
    )
    spec_tables = [
        t
        for t in refined_tables
        if t.section_type != "other" or t.confidence >= 0.85
    ]
    filtered_tables = _filter_best_per_page_section(
        spec_tables if spec_tables else refined_tables
    )
    merged_tables = merge_multipage_tables(
        filtered_tables, page_heights=page_heights, config=cfg
    )
    merged_tables = _limit_per_section_type(
        merged_tables, cfg.phase1_dla.max_tables_per_section
    )
    crop_footnotes = extract_footnotes_from_crops(footnote_crops, footnote_pages)
    pdf_footnotes = extract_footnotes_from_pdf(pdf_file, max_pages=cfg.phase1_dla.max_spec_page)
    footnotes = crop_footnotes + pdf_footnotes
    footnote_map = build_footnote_map(footnotes)

    output = Phase1Output(
        pdf_path=str(pdf_file),
        detected_tables=merged_tables,
        footnotes=footnotes,
        footnote_map=footnote_map,
    )

    _write_debug_output(output, cfg, cover_offset=cover_offset)
    logger.info(
        "Phase 1 complete: %d tables, %d footnotes for %s",
        len(output.detected_tables),
        len(output.footnotes),
        pdf_file.name,
    )
    return output


def _write_debug_output(
    output: Phase1Output,
    config: Config,
    cover_offset: int = 0,
) -> None:
    """Write optional debug metadata to phase1 output directory."""
    out_dir = config.pipeline.phase1_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(output.pdf_path).stem
    meta_path = out_dir / f"{stem}_phase1_meta.json"
    meta = {
        "pdf_path": output.pdf_path,
        "cover_offset": cover_offset,
        "num_tables": len(output.detected_tables),
        "num_footnotes": len(output.footnotes),
        "section_types": [t.section_type for t in output.detected_tables],
        "page_numbers": [t.page_number for t in output.detected_tables],
        "footnote_markers": list(output.footnote_map.keys()),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
