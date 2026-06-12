"""Phase 1: Rasterize PDF pages to PNG images."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError

from src.config import Config, get_config
from src.utils.exceptions import DLAError

logger = logging.getLogger(__name__)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def rasterize_pdf(pdf_path: str | Path, config: Config | None = None) -> list[bytes]:
    """Convert PDF pages to PNG bytes at configured DPI.

    Args:
        pdf_path: Path to input PDF file.
        config: Optional config override; uses global config when omitted.

    Returns:
        List of PNG bytes, one per page.

    Raises:
        FileNotFoundError: If PDF file doesn't exist.
        DLAError: If rasterization fails or Poppler is missing.
    """
    cfg = config or get_config()
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        logger.info("Rasterizing %s at %s DPI", pdf_file.name, cfg.pipeline.pdf_dpi)
        images = convert_from_path(
            str(pdf_file),
            dpi=cfg.pipeline.pdf_dpi,
            fmt=cfg.pipeline.pdf_fmt,
        )
    except PDFInfoNotInstalledError as exc:
        logger.error("Poppler not installed: %s", exc)
        raise DLAError(
            "Poppler (pdfinfo/pdftoppm) not installed. "
            "Install poppler-utils (Linux) or brew install poppler (macOS)."
        ) from exc
    except DLAError:
        raise
    except Exception as exc:
        logger.error("Rasterization failed for %s: %s", pdf_path, exc)
        raise DLAError(f"Cannot rasterize {pdf_path}: {exc}") from exc

    if not images:
        raise DLAError(f"Rasterization produced 0 pages for {pdf_path}")

    png_bytes: list[bytes] = []
    for index, image in enumerate(images):
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        page_bytes = buffer.getvalue()
        png_bytes.append(page_bytes)
        logger.debug("  Page %d: %d bytes", index + 1, len(page_bytes))

    logger.info("Rasterized %d pages from %s", len(png_bytes), pdf_file.name)
    return png_bytes
