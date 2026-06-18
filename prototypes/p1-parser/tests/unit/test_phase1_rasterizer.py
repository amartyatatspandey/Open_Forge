"""Unit tests for Phase 1 rasterizer."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.phase1_dla.rasterize import PNG_MAGIC, rasterize_pdf
from src.utils.exceptions import DLAError

GOLDEN_PDF = Path("corpus/golden/TI_TLV7021_v1.pdf")


@pytest.mark.skipif(not GOLDEN_PDF.exists(), reason="Golden PDF not downloaded")
def test_rasterize_golden_corpus() -> None:
    """Rasterize one golden PDF and verify PNG output."""
    result = rasterize_pdf(GOLDEN_PDF)
    assert len(result) >= 5
    assert all(isinstance(b, bytes) for b in result)
    for png_bytes in result:
        assert png_bytes[:8] == PNG_MAGIC


def test_rasterize_nonexistent_raises() -> None:
    """Nonexistent PDF should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        rasterize_pdf("corpus/nonexistent.pdf")


@pytest.mark.skipif(not GOLDEN_PDF.exists(), reason="Golden PDF not downloaded")
def test_rasterize_empty_path_raises_dla_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero-page rasterization should raise DLAError."""

    def _empty_convert(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr("src.phase1_dla.rasterize.convert_from_path", _empty_convert)
    with pytest.raises(DLAError, match="0 pages"):
        rasterize_pdf(GOLDEN_PDF)
