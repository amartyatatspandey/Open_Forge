"""Unit tests for Phase 1 multipage table merge."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from src.phase1_dla.multipage_merge import merge_multipage_tables, should_merge_pair
from src.schemas.pipeline import BoundingBox, DetectedTable


def _png_bytes(width: int = 100, height: int = 50) -> bytes:
    """Create minimal valid PNG bytes."""
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _table(
    page: int,
    y1: int,
    y2: int,
    section: str = "electrical_characteristics",
) -> DetectedTable:
    """Helper to build a DetectedTable for merge tests."""
    return DetectedTable(
        crop_bytes=_png_bytes(),
        bbox=BoundingBox(x1=50, y1=y1, x2=550, y2=y2),
        page_number=page,
        page_range=(page, page),
        confidence=0.9,
        section_type=section,  # type: ignore[arg-type]
    )


def test_should_merge_consecutive_bottom_top_tables() -> None:
    """Bottom-of-page N + top-of-page N+1 with same section should merge."""
    table_a = _table(page=6, y1=2200, y2=3000)
    table_b = _table(page=7, y1=50, y2=800)
    assert should_merge_pair(table_a, table_b, page_height=3300, tolerance=0.15)


def test_should_not_merge_different_pages_gap() -> None:
    """Non-consecutive pages should not merge."""
    table_a = _table(page=6, y1=2200, y2=3000)
    table_b = _table(page=8, y1=50, y2=800)
    assert not should_merge_pair(table_a, table_b, page_height=3300, tolerance=0.15)


def test_merge_multipage_tables_combines_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    """Merge helper reduces two tables to one."""
    monkeypatch.setattr(
        "src.phase1_dla.multipage_merge._merge_crops",
        lambda crop_a, crop_b: crop_a + crop_b,
    )
    tables = [
        _table(page=6, y1=2200, y2=3000),
        _table(page=7, y1=50, y2=800),
    ]
    merged = merge_multipage_tables(tables, page_heights={6: 3300, 7: 3300})
    assert len(merged) == 1
    assert merged[0].page_range == (6, 7)
