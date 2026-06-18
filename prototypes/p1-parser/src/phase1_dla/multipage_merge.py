"""Phase 1: Merge table detections that span multiple pages."""

from __future__ import annotations

import io
import logging

from PIL import Image

from src.config import Config, get_config
from src.schemas.pipeline import BoundingBox, DetectedTable

logger = logging.getLogger(__name__)


def _bbox_width(bbox: BoundingBox) -> int:
    """Return bbox width in pixels."""
    return max(0, bbox.x2 - bbox.x1)


def _widths_match(width_a: int, width_b: int, tolerance: float) -> bool:
    """Check if two widths are within relative tolerance."""
    if width_a == 0 or width_b == 0:
        return False
    ratio = min(width_a, width_b) / max(width_a, width_b)
    return ratio >= (1.0 - tolerance)


def _x_aligned(bbox_a: BoundingBox, bbox_b: BoundingBox, tolerance: float) -> bool:
    """Check if two bboxes have similar x-alignment and width."""
    width_a = _bbox_width(bbox_a)
    width_b = _bbox_width(bbox_b)
    if not _widths_match(width_a, width_b, tolerance):
        return False
    x_overlap = min(bbox_a.x2, bbox_b.x2) - max(bbox_a.x1, bbox_b.x1)
    return x_overlap >= min(width_a, width_b) * (1.0 - tolerance)


def _is_bottom_table(table: DetectedTable, page_height: int) -> bool:
    """Return True if table sits in the bottom third of its page."""
    center_y = (table.bbox.y1 + table.bbox.y2) / 2
    return center_y >= (2 * page_height / 3)


def _is_top_table(table: DetectedTable, page_height: int) -> bool:
    """Return True if table sits in the top third of its page."""
    center_y = (table.bbox.y1 + table.bbox.y2) / 2
    return center_y <= (page_height / 3)


def _merge_crops(crop_a: bytes, crop_b: bytes) -> bytes:
    """Vertically concatenate two table crop images."""
    img_a = Image.open(io.BytesIO(crop_a)).convert("RGB")
    img_b = Image.open(io.BytesIO(crop_b)).convert("RGB")
    width = max(img_a.width, img_b.width)
    height = img_a.height + img_b.height
    merged = Image.new("RGB", (width, height), (255, 255, 255))
    merged.paste(img_a, (0, 0))
    merged.paste(img_b, (0, img_a.height))
    buffer = io.BytesIO()
    merged.save(buffer, format="PNG")
    return buffer.getvalue()


def _union_bbox(bbox_a: BoundingBox, bbox_b: BoundingBox) -> BoundingBox:
    """Compute union of two bounding boxes."""
    return BoundingBox(
        x1=min(bbox_a.x1, bbox_b.x1),
        y1=min(bbox_a.y1, bbox_b.y1),
        x2=max(bbox_a.x2, bbox_b.x2),
        y2=max(bbox_a.y2, bbox_b.y2),
    )


def should_merge_pair(
    table_a: DetectedTable,
    table_b: DetectedTable,
    page_height: int,
    tolerance: float,
) -> bool:
    """Return True if two consecutive-page tables should be merged.

    Args:
        table_a: Table on page N.
        table_b: Table on page N+1.
        page_height: Rasterized page height in pixels.
        tolerance: Relative width/x-alignment tolerance.

    Returns:
        True when continuation heuristic matches.
    """
    if table_b.page_number != table_a.page_number + 1:
        return False
    if table_a.section_type != table_b.section_type and "other" not in (
        table_a.section_type,
        table_b.section_type,
    ):
        return False
    if not _is_bottom_table(table_a, page_height):
        return False
    if not _is_top_table(table_b, page_height):
        return False
    return _x_aligned(table_a.bbox, table_b.bbox, tolerance)


def merge_multipage_tables(
    tables: list[DetectedTable],
    page_heights: dict[int, int] | None = None,
    config: Config | None = None,
) -> list[DetectedTable]:
    """Merge table detections that continue across consecutive pages.

    Args:
        tables: Detected tables sorted by page_number then y1.
        page_heights: Map of page_number to rasterized height in pixels.
        config: Optional config override.

    Returns:
        Merged list of DetectedTable objects.
    """
    if not tables:
        return []

    cfg = config or get_config()
    tolerance = cfg.phase1_dla.table_width_match_tolerance
    default_height = 3300

    sorted_tables = sorted(tables, key=lambda t: (t.page_number, t.bbox.y1))
    merged: list[DetectedTable] = []
    index = 0

    while index < len(sorted_tables):
        current = sorted_tables[index]
        page_height = (page_heights or {}).get(current.page_number, default_height)

        if index + 1 < len(sorted_tables):
            nxt = sorted_tables[index + 1]
            if should_merge_pair(current, nxt, page_height, tolerance):
                merged_crop = _merge_crops(current.crop_bytes, nxt.crop_bytes)
                merged_table = DetectedTable(
                    crop_bytes=merged_crop,
                    bbox=_union_bbox(current.bbox, nxt.bbox),
                    page_number=current.page_number,
                    page_range=(current.page_range[0], nxt.page_range[1]),
                    confidence=max(current.confidence, nxt.confidence),
                    section_type=current.section_type
                    if current.section_type != "other"
                    else nxt.section_type,
                    heading_text=current.heading_text or nxt.heading_text,
                )
                merged.append(merged_table)
                logger.info(
                    "Merged tables on pages %d-%d (%s)",
                    current.page_number,
                    nxt.page_number,
                    merged_table.section_type,
                )
                index += 2
                continue

        merged.append(current)
        index += 1

    return merged
