"""Text extraction from PDF pages using pdfplumber.

Extracts plain text from specific page numbers, handling whitespace
normalization and hyphenated line break joining.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from src.datasheet.phase5_layout._schemas import PageTextBlock

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Minimum character threshold for valid page content
MIN_PAGE_CHARS = 50


def _clean_page_text(raw_text: str) -> str:
    """Clean and normalize extracted page text.

    Performs the following transformations:
    1. Joins hyphenated line breaks ("exam-\nple" → "example")
    2. Normalizes excessive whitespace to single spaces
    3. Strips leading/trailing whitespace

    Args:
        raw_text: Raw text from pdfplumber page extraction

    Returns:
        Cleaned and normalized text string
    """
    text = raw_text

    # Join hyphenated line breaks: word- followed by newline + lowercase = join
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)

    # Replace all whitespace sequences with single space
    text = re.sub(r'\s+', ' ', text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def extract_page_texts(
    pdf_path: Path,
    page_numbers: list[int],
) -> list[PageTextBlock]:
    """Extract text from specific PDF pages using pdfplumber.

    Opens the PDF and extracts text from only the specified page numbers.
    Each page is cleaned (hyphenated line breaks joined, whitespace normalized).
    Pages with fewer than 50 characters are logged as WARNING and skipped.

    Args:
        pdf_path: Path to the source PDF file
        page_numbers: List of 1-indexed page numbers to extract (matching Phase 1)

    Returns:
        List of PageTextBlock objects for successfully extracted pages.
        Returns empty list if PDF cannot be opened or all pages fail.

    Never raises exceptions — logs warnings and returns empty list on failure.

    Example:
        >>> blocks = extract_page_texts(Path("datasheet.pdf"), [5, 6, 7])
        >>> [b.page_number for b in blocks]
        [5, 6, 7]
    """
    results: list[PageTextBlock] = []

    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available for text extraction")
        return results

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num in page_numbers:
                try:
                    # pdfplumber uses 0-indexed pages
                    page_idx = page_num - 1

                    if page_idx < 0 or page_idx >= len(pdf.pages):
                        logger.warning(
                            f"Page {page_num} out of range (PDF has {len(pdf.pages)} pages)"
                        )
                        continue

                    page = pdf.pages[page_idx]
                    raw_text = page.extract_text() or ""

                    if not raw_text.strip():
                        logger.debug(f"Page {page_num}: no text extracted")
                        continue

                    # Clean the extracted text
                    cleaned_text = _clean_page_text(raw_text)
                    char_count = len(cleaned_text)

                    # Skip pages with insufficient content
                    if char_count < MIN_PAGE_CHARS:
                        logger.warning(
                            f"Page {page_num}: only {char_count} chars extracted "
                            f"(minimum {MIN_PAGE_CHARS}), skipping"
                        )
                        continue

                    results.append(
                        PageTextBlock(
                            page_number=page_num,
                            text=cleaned_text,
                            char_count=char_count,
                        )
                    )

                    logger.debug(
                        f"Extracted {char_count} chars from page {page_num}"
                    )

                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num}: {e}")
                    continue

    except FileNotFoundError:
        logger.warning(f"PDF file not found: {pdf_path}")
    except Exception as e:
        logger.warning(f"Failed to open or process PDF {pdf_path}: {e}")

    return results
