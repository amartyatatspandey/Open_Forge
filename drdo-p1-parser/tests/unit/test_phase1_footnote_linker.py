"""Unit tests for Phase 1 footnote linker."""

from __future__ import annotations

from src.phase1_dla.footnote_linker import (
    build_footnote_map,
    extract_footnotes_from_crops,
    link_footnotes_to_cells,
    parse_footnote_marker,
)
from src.schemas.pipeline import FootnoteLink


def test_parse_numbered_footnote_marker() -> None:
    """Parse (1) style markers from OCR text."""
    text = "(1) Stresses beyond these ratings may cause permanent damage."
    assert parse_footnote_marker(text) == "(1)"


def test_parse_asterisk_footnote_marker() -> None:
    """Parse asterisk footnote markers."""
    text = "* Test condition applies at TJ = 25°C."
    assert parse_footnote_marker(text) == "*"


def test_build_footnote_map() -> None:
    """Build marker-to-text dict from FootnoteLink list."""
    footnotes = [
        FootnoteLink(marker="(1)", text="Guaranteed by design.", page_number=3),
        FootnoteLink(marker="(2)", text="Applies at 25C.", page_number=3),
    ]
    result = build_footnote_map(footnotes)
    assert result["(1)"] == "Guaranteed by design."
    assert len(result) == 2


def test_link_footnotes_to_cells() -> None:
    """Link only markers found in table cells."""
    cells = [["V_CC (1)", "3.3"], ["I_CC", "10 mA"]]
    footnote_map = {"(1)": "Design note", "(2)": "Unused"}
    linked = link_footnotes_to_cells(cells, footnote_map)
    assert linked == {"(1)": "Design note"}


def test_extract_footnotes_from_text_crops(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Extract footnotes when OCR returns known text."""

    def _fake_ocr(_bytes: bytes) -> str:
        return "(1) Guaranteed by design."

    monkeypatch.setattr("src.phase1_dla.footnote_linker.ocr_image", _fake_ocr)
    footnotes = extract_footnotes_from_crops([b"fake"], [4])
    assert len(footnotes) == 1
    assert footnotes[0].marker == "(1)"
    assert footnotes[0].page_number == 4
