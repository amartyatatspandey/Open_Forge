"""Path A: deterministic table extraction via pdfplumber and Camelot."""

from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber

from src.config import Config, get_config
from src.schemas.pipeline import BoundingBox, GridMatrix, SectionType

logger = logging.getLogger(__name__)


def bbox_to_pdf_points(bbox: BoundingBox, dpi: int) -> tuple[float, float, float, float]:
    """Convert rasterized pixel bbox to PDF point coordinates (x0, top, x1, bottom)."""
    scale = 72.0 / dpi
    x0 = bbox.x1 * scale
    top = bbox.y1 * scale
    x1 = bbox.x2 * scale
    bottom = bbox.y2 * scale
    return x0, top, x1, bottom


def _rows_from_pdfplumber(page, crop_box: tuple[float, float, float, float]) -> list[list[str]] | None:
    """Extract table rows from a cropped pdfplumber page region."""
    cropped = page.crop(crop_box)
    tables = cropped.extract_tables() or []
    if not tables:
        tables = page.extract_tables() or []
    if not tables:
        return None
    best = max(tables, key=len)
    rows = [[(cell or "").strip() for cell in row] for row in best]
    return rows if rows else None


def _rows_from_camelot(
    pdf_path: Path,
    page_number: int,
    crop_box: tuple[float, float, float, float],
    flavor: str,
) -> list[list[str]] | None:
    """Extract table rows via Camelot lattice/stream mode."""
    try:
        import camelot
    except ImportError:
        logger.debug("Camelot not available, skipping")
        return None

    x0, top, x1, bottom = crop_box
    page_height = 792.0  # fallback; Camelot uses bottom-left origin
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if 1 <= page_number <= len(pdf.pages):
                page_height = pdf.pages[page_number - 1].height
    except Exception:
        pass

    y0 = page_height - bottom
    y1 = page_height - top
    table_area = f"{x0},{y0},{x1},{y1}"
    try:
        tables = camelot.read_pdf(
            str(pdf_path),
            pages=str(page_number),
            flavor=flavor,
            table_areas=[table_area],
        )
    except Exception as exc:
        logger.debug("Camelot extraction failed: %s", exc)
        return None

    if not tables:
        return None
    df = tables[0].df
    rows = df.values.tolist()
    return [[str(cell).strip() for cell in row] for row in rows]


def _build_grid(
    rows: list[list[str]],
    section_type: SectionType,
    page_number: int,
) -> GridMatrix | None:
    """Validate and build GridMatrix from raw rows."""
    if not rows:
        return None
    num_cols = max(len(row) for row in rows)
    if len(rows) < 2 or num_cols < 2:
        return None
    normalized = [row + [""] * (num_cols - len(row)) for row in rows]
    return GridMatrix(
        rows=normalized,
        num_rows=len(normalized),
        num_cols=num_cols,
        section_type=section_type,
        page_number=page_number,
        confidence=0.9,
        source="vector_path_A",
    )


def extract_table_via_vector(
    pdf_path: Path | str,
    bbox: BoundingBox,
    page_number: int,
    section_type: SectionType,
    config: Config | None = None,
) -> GridMatrix | None:
    """Extract table structure using pdfplumber and Camelot.

    Args:
        pdf_path: Path to source PDF.
        bbox: Table region in rasterized pixel coordinates.
        page_number: 1-indexed page number.
        section_type: Section type from Phase 1.
        config: Optional config override.

    Returns:
        GridMatrix if extraction succeeded, else None.
    """
    cfg = config or get_config()
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        logger.warning("PDF not found for vector extraction: %s", pdf_path)
        return None

    crop_box = bbox_to_pdf_points(bbox, cfg.pipeline.pdf_dpi)
    rows: list[list[str]] | None = None

    try:
        with pdfplumber.open(pdf_file) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                logger.warning("Page %d out of range for %s", page_number, pdf_file.name)
                return None
            page = pdf.pages[page_number - 1]
            rows = _rows_from_pdfplumber(page, crop_box)
    except Exception as exc:
        logger.warning("pdfplumber extraction failed: %s", exc)

    if rows is None:
        rows = _rows_from_camelot(
            pdf_file,
            page_number,
            crop_box,
            cfg.phase2_tsr.camelot_flavor,
        )

    grid = _build_grid(rows, section_type, page_number) if rows else None
    if grid is None:
        logger.info(
            "Vector path failed for %s page %d (%s)",
            pdf_file.name,
            page_number,
            section_type,
        )
    else:
        logger.info(
            "Vector path extracted %dx%d grid on page %d",
            grid.num_rows,
            grid.num_cols,
            page_number,
        )
    return grid
