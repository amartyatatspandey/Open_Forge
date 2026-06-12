"""Unit tests for Path A vector extraction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.phase2_tsr.path_a_vector import bbox_to_pdf_points, extract_table_via_vector
from src.schemas.pipeline import BoundingBox


def test_bbox_to_pdf_points() -> None:
    bbox = BoundingBox(x1=100, y1=200, x2=400, y2=500)
    x0, top, x1, bottom = bbox_to_pdf_points(bbox, dpi=300)
    scale = 72.0 / 300
    assert x0 == bbox.x1 * scale
    assert top == bbox.y1 * scale


@patch.object(Path, "exists", return_value=True)
@patch("src.phase2_tsr.path_a_vector._rows_from_camelot")
@patch("src.phase2_tsr.path_a_vector.pdfplumber.open")
def test_extract_table_via_vector_success(
    mock_open: MagicMock, mock_camelot: MagicMock, _mock_exists: MagicMock
) -> None:
    mock_page = MagicMock()
    mock_page.crop.return_value.extract_tables.return_value = [
        [["Param", "Max"], ["V_CC", "6"]],
    ]
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_open.return_value.__enter__.return_value = mock_pdf
    mock_camelot.return_value = None

    grid = extract_table_via_vector(
        Path("test.pdf"),
        BoundingBox(x1=10, y1=20, x2=100, y2=200),
        page_number=1,
        section_type="absolute_maximum_ratings",
    )
    assert grid is not None
    assert grid.num_rows == 2
    assert grid.source == "vector_path_A"


@patch("src.phase2_tsr.path_a_vector.pdfplumber.open")
def test_extract_table_via_vector_missing_pdf(mock_open: MagicMock) -> None:
    mock_open.side_effect = FileNotFoundError("missing")
    grid = extract_table_via_vector(
        Path("nonexistent.pdf"),
        BoundingBox(x1=0, y1=0, x2=10, y2=10),
        page_number=1,
        section_type="pinout",
    )
    assert grid is None


@patch.object(Path, "exists", return_value=True)
@patch("src.phase2_tsr.path_a_vector._rows_from_camelot")
@patch("src.phase2_tsr.path_a_vector.pdfplumber.open")
def test_extract_borderless_returns_none(
    mock_open: MagicMock, mock_camelot: MagicMock, _mock_exists: MagicMock
) -> None:
    mock_page = MagicMock()
    mock_page.crop.return_value.extract_tables.return_value = []
    mock_page.extract_tables.return_value = []
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_open.return_value.__enter__.return_value = mock_pdf
    mock_camelot.return_value = None

    grid = extract_table_via_vector(
        Path("test.pdf"),
        BoundingBox(x1=10, y1=20, x2=100, y2=200),
        page_number=1,
        section_type="electrical_characteristics",
    )
    assert grid is None
