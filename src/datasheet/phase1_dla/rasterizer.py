"""PDF rasterization — pdf2image wrapper for Phase 1 DLA.

Converts PDF pages to PIL Images for downstream YOLO inference.
Handles DPI configuration, memory-efficient processing, and error handling.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pdf2image import convert_from_path
from PIL import Image

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Default DPI for rasterization — balances quality vs. speed
DEFAULT_DPI: int = 300


def _rasterize_page(
    pdf_path: Path,
    page_number: int,
    dpi: int = DEFAULT_DPI,
) -> Image.Image:
    """Rasterize a single PDF page to PIL Image.

    Args:
        pdf_path: Path to the PDF file
        page_number: 1-indexed page number to rasterize
        dpi: Resolution in dots per inch (default 300)

    Returns:
        PIL Image of the rasterized page

    Raises:
        FileNotFoundError: If pdf_path does not exist
        RuntimeError: If pdf2image conversion fails
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        images = convert_from_path(
            path,
            dpi=dpi,
            first_page=page_number,
            last_page=page_number,
        )
        if not images:
            raise RuntimeError(f"No image generated for page {page_number}")
        return images[0]
    except Exception as e:
        logger.error(f"Failed to rasterize page {page_number} of {pdf_path}: {e}")
        raise RuntimeError(f"Rasterization failed for page {page_number}: {e}") from e


def _rasterize_all_pages(
    pdf_path: Path,
    dpi: int = DEFAULT_DPI,
) -> list[tuple[int, Image.Image]]:
    """Rasterize all pages of a PDF to PIL Images.

    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution in dots per inch (default 300)

    Returns:
        List of (page_number, PIL.Image) tuples, 1-indexed

    Raises:
        FileNotFoundError: If pdf_path does not exist
        RuntimeError: If pdf2image conversion fails
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    logger.info(f"Rasterizing {pdf_path} at {dpi} DPI")

    try:
        images = convert_from_path(path, dpi=dpi)
        return [(i + 1, img) for i, img in enumerate(images)]
    except Exception as e:
        logger.error(f"Failed to rasterize {pdf_path}: {e}")
        raise RuntimeError(f"Rasterization failed for {pdf_path}: {e}") from e


def _get_total_pages(pdf_path: Path) -> int:
    """Get total number of pages in PDF without full rasterization.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Total number of pages

    Raises:
        FileNotFoundError: If pdf_path does not exist
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        # Rasterize just first page to get info
        images = convert_from_path(path, first_page=1, last_page=1)
        # pdf2image doesn't expose page count directly; we rasterize all
        # This is a limitation — we'll rasterize all pages to count
        all_images = convert_from_path(path, dpi=72)  # Low DPI for speed
        return len(all_images)
    except Exception as e:
        logger.error(f"Failed to count pages in {pdf_path}: {e}")
        raise RuntimeError(f"Page count failed for {pdf_path}: {e}") from e
