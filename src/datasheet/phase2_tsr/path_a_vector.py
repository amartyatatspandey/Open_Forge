"""Phase 2 Path A: Vector-based table extraction using pdfplumber + Camelot.

Implements deterministic table structure recognition using:
- pdfplumber: Text position extraction from PDF
- Camelot lattice: Line-based table detection for bordered tables

Returns None for borderless tables where Camelot cannot detect lattice lines.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import pdfplumber
from PIL import Image

from src.datasheet.phase1_dla._schemas import TableCrop
from src.datasheet.phase2_tsr._schemas import CellValue, GridMatrix
from src.schemas.datasheet import TableSectionType

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Vector path success confidence when Camelot succeeds
VECTOR_CONFIDENCE_SUCCESS: float = 0.97


def _extract_text_with_pdfplumber(
    pdf_path: Path,
    page_number: int,
) -> list[dict[str, Any]]:
    """Extract text blocks with positions using pdfplumber.

    Args:
        pdf_path: Path to source PDF
        page_number: 1-indexed page number

    Returns:
        List of text block dicts with 'text', 'x0', 'y0', 'x1', 'y1', 'top', 'bottom'

    Raises:
        FileNotFoundError: If PDF not found
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with pdfplumber.open(pdf_path) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise ValueError(f"Invalid page number {page_number}, PDF has {len(pdf.pages)} pages")

        page = pdf.pages[page_number - 1]  # pdfplumber uses 0-index
        chars = page.chars

        # Group characters into words/lines
        blocks = []
        if chars:
            # Simple grouping by vertical position
            current_line: list[dict[str, Any]] = []
            current_y = chars[0]["top"] if chars else 0
            y_threshold = 3  # pixels

            for char in chars:
                if abs(char["top"] - current_y) > y_threshold:
                    # New line
                    if current_line:
                        text = "".join(c["text"] for c in current_line)
                        x0 = min(c["x0"] for c in current_line)
                        x1 = max(c["x1"] for c in current_line)
                        y0 = min(c["top"] for c in current_line)
                        y1 = max(c["bottom"] for c in current_line)
                        blocks.append({
                            "text": text,
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "y1": y1,
                            "top": y0,
                            "bottom": y1,
                        })
                    current_line = [char]
                    current_y = char["top"]
                else:
                    current_line.append(char)

            # Don't forget last line
            if current_line:
                text = "".join(c["text"] for c in current_line)
                x0 = min(c["x0"] for c in current_line)
                x1 = max(c["x1"] for c in current_line)
                y0 = min(c["top"] for c in current_line)
                y1 = max(c["bottom"] for c in current_line)
                blocks.append({
                    "text": text,
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "top": y0,
                    "bottom": y1,
                })

        logger.debug(f"pdfplumber extracted {len(blocks)} text blocks from page {page_number}")
        return blocks


def _has_lattice_lines(
    pdf_path: Path,
    page_number: int,
) -> bool:
    """Check if page has visible table lattice lines using Camelot.

    Args:
        pdf_path: Path to source PDF
        page_number: 1-indexed page number

    Returns:
        True if Camelot detects lattice lines, False otherwise

    Notes:
        Camelot lattice mode requires visible lines to detect table structure.
        Borderless tables will return False.
    """
    try:
        import camelot

        tables = camelot.read_pdf(  # type: ignore[attr-defined]
            str(pdf_path),
            pages=str(page_number),
            flavor="lattice",
        )

        # If Camelot found tables with lattice, lines exist
        return len(tables) > 0

    except Exception as e:
        logger.warning(f"Camelot lattice detection failed: {e}")
        return False


def _camelot_to_grid_matrix(
    pdf_path: Path,
    page_number: int,
    crop_bbox: tuple[int, int, int, int],
    section_type: TableSectionType,
    table_index: int,
) -> Optional[GridMatrix]:
    """Convert Camelot table extraction to GridMatrix.

    Args:
        pdf_path: Path to source PDF
        page_number: 1-indexed page number
        crop_bbox: Table crop bounding box (x1, y1, x2, y2) in pixels
        section_type: TableSectionType from Phase 1
        table_index: Table index within page

    Returns:
        GridMatrix if Camelot succeeds, None if no tables found
    """
    try:
        import camelot

        tables = camelot.read_pdf(  # type: ignore[attr-defined]
            str(pdf_path),
            pages=str(page_number),
            flavor="lattice",
        )

        if not tables:
            logger.debug(f"Camelot found no tables on page {page_number}")
            return None

        # Take first table (should match our crop)
        table = tables[0]
        df = table.df

        num_rows = len(df)
        num_cols = len(df.columns)

        cells: list[CellValue] = []
        for row_idx in range(num_rows):
            for col_idx in range(num_cols):
                text = str(df.iloc[row_idx, col_idx])
                is_header = row_idx == 0  # Assume first row is header

                cells.append(
                    CellValue(
                        text=text,
                        row=row_idx,
                        col=col_idx,
                        rowspan=1,
                        colspan=1,
                        is_header=is_header,
                    )
                )

        logger.info(
            f"Camelot extracted {num_rows}x{num_cols} grid from page {page_number}"
        )

        from src.datasheet.phase2_tsr._schemas import GridMatrix

        return GridMatrix(
            cells=cells,
            num_rows=num_rows,
            num_cols=num_cols,
            section_type=section_type,
            source_page=page_number,
            source_table_index=table_index,
            extraction_path="vector",
            confidence=VECTOR_CONFIDENCE_SUCCESS,
            has_merged_cells=False,  # Will be updated by merged_cell_handler
        )

    except Exception as e:
        logger.warning(f"Camelot extraction failed: {e}")
        return None


def extract_table_vector_path(
    pdf_path: Path,
    table_crop: TableCrop,
    table_index: int,
    config: Config,
) -> Optional[GridMatrix]:
    """Extract table structure using vector path (pdfplumber + Camelot).

    Path A is the deterministic, line-based extraction. It uses Camelot's
    lattice mode for bordered tables. Returns None for borderless tables
    where Camelot cannot find lines.

    Args:
        pdf_path: Path to source PDF
        table_crop: TableCrop from Phase 1 with image_bytes and metadata
        table_index: Index of table within page
        config: Application configuration

    Returns:
        GridMatrix with extraction_path="vector" and confidence=0.97 on success,
        None if table is borderless or Camelot fails to find lattice lines
    """
    page_number = table_crop.page_number
    section_type = table_crop.section_type

    logger.info(f"Path A: Processing table {table_index} on page {page_number}")

    # Check if table has lattice lines using Camelot
    if not _has_lattice_lines(pdf_path, page_number):
        logger.info(
            f"Path A: No lattice lines detected on page {page_number}, "
            "table likely borderless — returning None"
        )
        return None

    # Extract using Camelot lattice mode
    crop_bbox = table_crop.bounding_box
    grid = _camelot_to_grid_matrix(
        pdf_path,
        page_number,
        crop_bbox,
        section_type,
        table_index,
    )

    if grid is None:
        logger.warning(f"Path A: Camelot extraction failed for table {table_index}")
        return None

    logger.info(
        f"Path A: Successfully extracted {grid.num_rows}x{grid.num_cols} grid "
        f"with confidence {grid.confidence}"
    )

    return grid
