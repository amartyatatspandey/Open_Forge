"""Unit tests for Phase 1 section classifier."""

from __future__ import annotations

import pytest

from src.phase1_dla.classify_section import classify_section_type, position_on_page
from src.schemas.pipeline import BoundingBox


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("6.5 Electrical Characteristics", "electrical_characteristics"),
        ("7.5 Electrical Characteristics (continued)", "electrical_characteristics"),
        ("5 Pin Configuration and Functions", "pinout"),
        ("6.1 Absolute Maximum Ratings", "absolute_maximum_ratings"),
        ("8.3 Switching Characteristics", "timing"),
        ("12 Ordering Information", "ordering"),
        ("Revision History", "other"),
    ],
)
def test_classify_section_from_heading(heading: str, expected: str) -> None:
    """Keyword-based classification for known section headings."""
    page_number = 2 if expected == "other" else 5
    result = classify_section_type(heading, page_number=page_number, position="middle")
    assert result == expected


def test_classify_position_fallback_abs_max() -> None:
    """Early-page top position should fallback to abs_max."""
    result = classify_section_type(None, page_number=2, position="top")
    assert result == "absolute_maximum_ratings"


def test_classify_position_fallback_electrical() -> None:
    """Mid-document pages should fallback to electrical characteristics."""
    result = classify_section_type(None, page_number=6, position="middle")
    assert result == "electrical_characteristics"


def test_position_on_page_thirds() -> None:
    """Vertical position helper returns top/middle/bottom."""
    top_bbox = BoundingBox(x1=0, y1=0, x2=100, y2=100)
    mid_bbox = BoundingBox(x1=0, y1=400, x2=100, y2=500)
    bot_bbox = BoundingBox(x1=0, y1=800, x2=100, y2=900)
    assert position_on_page(top_bbox, 900) == "top"
    assert position_on_page(mid_bbox, 900) == "middle"
    assert position_on_page(bot_bbox, 900) == "bottom"
