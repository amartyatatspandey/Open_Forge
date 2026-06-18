"""Phase 1: Extract footnotes and link markers to table cells."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from PIL import Image

from src.schemas.pipeline import FootnoteLink

logger = logging.getLogger(__name__)

_MARKER_PATTERN = re.compile(
    r"^\s*[\(\*†]?\s*(\d+)\s*[\)\.\:]",
    re.MULTILINE,
)
_ASTERISK_PATTERN = re.compile(r"^\s*\*\s+", re.MULTILINE)


def ocr_image(image_bytes: bytes) -> str:
    """OCR a footnote crop image to text.

    Args:
        image_bytes: PNG bytes of footnote region.

    Returns:
        Extracted text, or empty string on failure.
    """
    try:
        import pytesseract

        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image) or ""
    except Exception as exc:
        logger.warning("OCR failed, returning empty text: %s", exc)
        return ""


def parse_footnote_marker(text: str) -> str | None:
    """Extract footnote marker from OCR text.

    Args:
        text: Raw OCR text from a footnote region.

    Returns:
        Marker string like "(1)" or "*", or None.
    """
    numbered = _MARKER_PATTERN.search(text)
    if numbered:
        return f"({numbered.group(1)})"
    if _ASTERISK_PATTERN.search(text):
        return "*"
    return None


def extract_footnotes_from_crops(
    footnote_crops: list[bytes],
    page_numbers: list[int],
) -> list[FootnoteLink]:
    """OCR footnote crops and build FootnoteLink entries.

    Args:
        footnote_crops: PNG bytes for each footnote region.
        page_numbers: 1-indexed page number per crop.

    Returns:
        List of parsed footnote links.
    """
    footnotes: list[FootnoteLink] = []
    for crop_bytes, page_num in zip(footnote_crops, page_numbers):
        text = ocr_image(crop_bytes).strip()
        if not text:
            continue
        marker = parse_footnote_marker(text)
        if marker is None:
            marker = f"page{page_num}_fn{len(footnotes) + 1}"
        footnotes.append(
            FootnoteLink(marker=marker, text=text, page_number=page_num)
        )
        logger.debug("Extracted footnote %s on page %d", marker, page_num)
    return footnotes


def build_footnote_map(footnotes: list[FootnoteLink]) -> dict[str, str]:
    """Build marker-to-text lookup dict for Phase 3 injection.

    Args:
        footnotes: Parsed footnote links.

    Returns:
        Dictionary mapping marker to footnote text.
    """
    return {fn.marker: fn.text for fn in footnotes}


def extract_footnotes_from_pdf(pdf_path: str | Path, max_pages: int = 25) -> list[FootnoteLink]:
    """Extract numbered footnotes from PDF page text via pdfplumber.

    Args:
        pdf_path: Path to source PDF.
        max_pages: Maximum pages to scan.

    Returns:
        Footnote links parsed from page text.
    """
    import pdfplumber

    footnotes: list[FootnoteLink] = []
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        return footnotes

    footnote_line = re.compile(
        r"^\s*\((\d+)\)\s+(.+)$",
        re.MULTILINE,
    )
    with pdfplumber.open(pdf_file) as pdf:
        for index, page in enumerate(pdf.pages[:max_pages]):
            page_number = index + 1
            text = page.extract_text() or ""
            for match in footnote_line.finditer(text):
                marker = f"({match.group(1)})"
                body = match.group(2).strip()
                footnotes.append(
                    FootnoteLink(marker=marker, text=body, page_number=page_number)
                )
    return footnotes


def link_footnotes_to_cells(
    table_cells: list[list[str]],
    footnote_map: dict[str, str],
) -> dict[str, str]:
    """Scan table cells for footnote markers present in footnote_map.

    Args:
        table_cells: 2D grid of cell text from Phase 2 TSR.
        footnote_map: Marker-to-text mapping from footnote extraction.

    Returns:
        Subset of footnote_map for markers found in cells.
    """
    linked: dict[str, str] = {}
    for row in table_cells:
        for cell in row:
            for marker, text in footnote_map.items():
                if marker in cell and marker not in linked:
                    linked[marker] = text
    return linked
