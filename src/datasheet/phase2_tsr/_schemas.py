"""Internal schemas for Phase 2 TSR — not exported publicly.

These Pydantic models define the intermediate output of Phase 2 Table Structure
Recognition. They are pipeline-internal types and not part of the public API.

Phase 2 Output Contract (with Phase 3):
- CellValue: Individual cell with position and span information
- GridMatrix: Complete reconstructed table grid
- Phase2Output: Aggregate TSR results for one PDF
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.datasheet.phase1_dla._schemas import FootnoteMap
from src.schemas.datasheet import TableSectionType


class CellValue(BaseModel):
    """A single cell value within a reconstructed table grid.

    Represents one cell with its text content, position (row/col),
    and span information (rowspan/colspan for merged cells).

    Attributes:
        text: Cell text content
        row: Row index (0-indexed)
        col: Column index (0-indexed)
        rowspan: Number of rows this cell spans (default 1)
        colspan: Number of columns this cell spans (default 1)
        is_header: True if this is a header cell
    """

    text: str = Field(description="Cell text content")
    row: int = Field(ge=0, description="Row index (0-indexed)")
    col: int = Field(ge=0, description="Column index (0-indexed)")
    rowspan: int = Field(
        default=1, ge=1, description="Number of rows this cell spans"
    )
    colspan: int = Field(
        default=1, ge=1, description="Number of columns this cell spans"
    )
    is_header: bool = Field(
        default=False, description="True if this is a header cell"
    )


class GridMatrix(BaseModel):
    """Reconstructed table grid matrix from TSR.

    Represents the complete table structure as a grid of cells with
    provenance metadata including source page, confidence, and extraction path.

    Attributes:
        cells: List of all cells in the grid
        num_rows: Total number of rows in grid
        num_cols: Total number of columns in grid
        section_type: Classification carried from Phase 1 crop label
        source_page: Page number where table was found
        source_table_index: Index of table within page
        extraction_path: Which TSR path produced this grid ("vector" or "vlm")
        confidence: Confidence score in [0.0, 1.0]
        has_merged_cells: True if any cell has rowspan>1 or colspan>1
    """

    cells: list[CellValue] = Field(description="List of all cells in the grid")
    num_rows: int = Field(ge=1, description="Total number of rows in grid")
    num_cols: int = Field(ge=1, description="Total number of columns in grid")
    section_type: TableSectionType = Field(
        description="Classification carried from Phase 1 crop label"
    )
    source_page: int = Field(
        ge=1, description="Page number where table was found"
    )
    source_table_index: int = Field(
        ge=0, description="Index of table within page"
    )
    extraction_path: Literal["vector", "vlm"] = Field(
        description='Which TSR path produced this grid ("vector" or "vlm")'
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score in [0.0, 1.0]"
    )
    has_merged_cells: bool = Field(
        default=False,
        description="True if any cell has rowspan>1 or colspan>1",
    )

    def get_cell(self, row: int, col: int) -> Optional[CellValue]:
        """Get cell at specific row, col position.

        Args:
            row: Row index
            col: Column index

        Returns:
            CellValue at position, or None if not found
        """
        return next(
            (c for c in self.cells if c.row == row and c.col == col), None
        )

    def header_row(self) -> list[CellValue]:
        """Get all header cells in the grid.

        Returns:
            List of cells where is_header=True
        """
        return [c for c in self.cells if c.is_header]

    def get_row(self, row_idx: int) -> list[CellValue]:
        """Get all cells in a specific row, sorted by column.

        Args:
            row_idx: Row index

        Returns:
            List of cells in row, sorted by column index
        """
        return sorted(
            [c for c in self.cells if c.row == row_idx],
            key=lambda c: c.col,
        )

    def get_col(self, col_idx: int) -> list[CellValue]:
        """Get all cells in a specific column, sorted by row.

        Args:
            col_idx: Column index

        Returns:
            List of cells in column, sorted by row index
        """
        return sorted(
            [c for c in self.cells if c.col == col_idx],
            key=lambda c: c.row,
        )


class Phase2Output(BaseModel):
    """Complete output of Phase 2 TSR. Input to Phase 3.

    Aggregate result of table structure recognition containing all
    reconstructed grids and footnote mappings for downstream extraction.

    Attributes:
        source_pdf_hash: SHA-256 hash of source PDF for provenance
        grids: List of reconstructed table grids
        footnote_maps: Passed through unchanged from Phase 1
        processing_time_ms: Total Phase 2 processing time in milliseconds
    """

    source_pdf_hash: str = Field(
        description="SHA-256 hash of source PDF for provenance"
    )
    grids: list[GridMatrix] = Field(
        description="List of reconstructed table grids"
    )
    footnote_maps: list[FootnoteMap] = Field(
        description="Passed through unchanged from Phase 1"
    )
    processing_time_ms: float = Field(
        ge=0.0,
        description="Total Phase 2 processing time in milliseconds",
    )

    def get_grid(self, page: int, table_index: int) -> Optional[GridMatrix]:
        """Get grid for specific page and table index.

        Args:
            page: Page number
            table_index: Table index within page

        Returns:
            GridMatrix if found, None otherwise
        """
        return next(
            (
                g
                for g in self.grids
                if g.source_page == page and g.source_table_index == table_index
            ),
            None,
        )
