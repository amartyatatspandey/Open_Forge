"""PDF cover-page offset detection for TI datasheets."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

_ABS_MAX_PATTERN = re.compile(r"absolute\s+maximum\s+ratings?", re.IGNORECASE)


def detect_cover_offset(
    pdf_path: str | Path,
    expected_printed_page: int = 5,
    scan_pages: int = 6,
) -> int:
    """Detect PDF index vs printed page offset using Absolute Maximum Ratings.

    Scans the first ``scan_pages`` PDF pages for the earliest occurrence of
    "Absolute Maximum Ratings" and compares to the typical TI printed page.

    Args:
        pdf_path: Path to the datasheet PDF.
        expected_printed_page: Typical printed page for abs-max (TI default 5).
        scan_pages: Number of PDF pages to scan from the start.

    Returns:
        ``found_pdf_page - expected_printed_page``, or 0 if not found.
        Negative values mean cover pages shift PDF index before printed numbers.
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        logger.warning("PDF not found for offset detection: %s", pdf_path)
        return 0

    with pdfplumber.open(pdf_file) as pdf:
        limit = min(scan_pages, len(pdf.pages))
        for index in range(limit):
            text = pdf.pages[index].extract_text() or ""
            if _ABS_MAX_PATTERN.search(text):
                found_pdf_page = index + 1
                offset = found_pdf_page - expected_printed_page
                logger.info(
                    "Cover offset for %s: %d (abs-max on PDF page %d, expected printed %d)",
                    pdf_file.name,
                    offset,
                    found_pdf_page,
                    expected_printed_page,
                )
                return offset

    logger.info("Cover offset for %s: 0 (abs-max heading not found in first %d pages)", pdf_file.name, scan_pages)
    return 0
