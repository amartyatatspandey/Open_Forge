"""Unit tests for PDF cover offset detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.phase1_dla.pdf_offset import detect_cover_offset

GOLDEN_PDF = Path("corpus/golden/TI_TLV7021_v1.pdf")


@pytest.mark.skipif(not GOLDEN_PDF.exists(), reason="Golden PDF not downloaded")
def test_detect_cover_offset_tlv7021() -> None:
    """TLV7021 should return a non-zero or zero integer offset."""
    offset = detect_cover_offset(GOLDEN_PDF, expected_printed_page=5)
    assert isinstance(offset, int)


def test_detect_cover_offset_missing_pdf() -> None:
    """Missing PDF returns safe fallback offset 0."""
    assert detect_cover_offset("corpus/nonexistent.pdf") == 0
