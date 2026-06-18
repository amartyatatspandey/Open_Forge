"""Unit tests for src/datasheet/phase2_tsr/.

Tests Phase 2 Table Structure Recognition including:
- Dual-path extraction (vector + VLM)
- Confidence scoring
- Grid selection
- Merged cell detection
- Full process() orchestration
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.config import Config
from src.datasheet.phase1_dla._schemas import FootnoteMap, Phase1Output, TableCrop
from src.datasheet.phase2_tsr import process
from src.datasheet.phase2_tsr._schemas import CellValue, GridMatrix, Phase2Output
from src.datasheet.phase2_tsr.confidence_scorer import (
    pick_best_grid,
    score_grid,
)
from src.datasheet.phase2_tsr.merged_cell_handler import detect_merged_cells
from src.schemas.datasheet import TableSectionType


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_cell() -> CellValue:
    """Sample CellValue for testing."""
    return CellValue(
        text="3.3V",
        row=1,
        col=1,
        is_header=False,
    )


@pytest.fixture
def sample_grid() -> GridMatrix:
    """Sample GridMatrix for testing."""
    cells = [
        CellValue(text="Parameter", row=0, col=0, is_header=True),
        CellValue(text="Min", row=0, col=1, is_header=True),
        CellValue(text="Max", row=0, col=2, is_header=True),
        CellValue(text="VCC", row=1, col=0),
        CellValue(text="2.7V", row=1, col=1),
        CellValue(text="5.5V", row=1, col=2),
    ]
    return GridMatrix(
        cells=cells,
        num_rows=2,
        num_cols=3,
        section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
        source_page=1,
        source_table_index=0,
        extraction_path="vector",
        confidence=0.97,
    )


@pytest.fixture
def mock_config(tmp_path) -> Config:
    """Create mock Config with temporary paths."""
    config = MagicMock(spec=Config)
    
    def get_model_path(name: str) -> Path:
        model_path = tmp_path / "models" / f"{name}.pt"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_bytes(b"dummy")
        return model_path
    
    config.get_model_path = get_model_path
    return config


@pytest.fixture
def mock_phase1_output() -> Phase1Output:
    """Create mock Phase1Output with 3 TableCrops."""
    # Create dummy image bytes
    img = Image.new("RGB", (100, 100), color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    image_bytes = buffer.getvalue()
    
    table_crops = [
        TableCrop(
            page_number=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=image_bytes,
            bounding_box=(100, 100, 700, 400),
            heading_text="ELECTRICAL CHARACTERISTICS",
            is_multipage_continuation=False,
            detection_confidence=0.95,
        ),
        TableCrop(
            page_number=2,
            section_type=TableSectionType.ABSOLUTE_MAXIMUM_RATINGS,
            image_bytes=image_bytes,
            bounding_box=(100, 100, 700, 400),
            heading_text="ABSOLUTE MAXIMUM RATINGS",
            is_multipage_continuation=False,
            detection_confidence=0.92,
        ),
        TableCrop(
            page_number=3,
            section_type=TableSectionType.PINOUT,
            image_bytes=image_bytes,
            bounding_box=(100, 100, 700, 400),
            heading_text="PIN CONFIGURATION",
            is_multipage_continuation=False,
            detection_confidence=0.88,
        ),
    ]
    
    footnote_maps = [
        FootnoteMap(
            page_number=1,
            entries={"1": "Valid for T_A = 25°C"},
        ),
    ]
    
    return Phase1Output(
        pdf_path="/tmp/test.pdf",
        source_pdf_hash="a1b2c3d4",
        total_pages=3,
        table_crops=table_crops,
        footnote_maps=footnote_maps,
        processing_time_ms=1500.0,
    )


# =============================================================================
# GridMatrix and CellValue Schema Tests
# =============================================================================


class TestGridMatrixSchema:
    """Tests for GridMatrix and CellValue schemas."""

    def test_cell_value_creation(self, sample_cell: CellValue) -> None:
        """Test CellValue creation."""
        assert sample_cell.text == "3.3V"
        assert sample_cell.row == 1
        assert sample_cell.col == 1
        assert sample_cell.rowspan == 1
        assert sample_cell.colspan == 1
        assert sample_cell.is_header is False

    def test_grid_matrix_creation(self, sample_grid: GridMatrix) -> None:
        """Test GridMatrix creation."""
        assert sample_grid.num_rows == 2
        assert sample_grid.num_cols == 3
        assert len(sample_grid.cells) == 6
        assert sample_grid.extraction_path == "vector"
        assert sample_grid.section_type == TableSectionType.ELECTRICAL_CHARACTERISTICS

    def test_grid_matrix_get_cell(self, sample_grid: GridMatrix) -> None:
        """Test GridMatrix.get_cell() method."""
        cell = sample_grid.get_cell(1, 1)
        assert cell is not None
        assert cell.text == "2.7V"

    def test_grid_matrix_get_cell_not_found(self, sample_grid: GridMatrix) -> None:
        """Test GridMatrix.get_cell() returns None for invalid position."""
        cell = sample_grid.get_cell(99, 99)
        assert cell is None

    def test_grid_matrix_header_row(self, sample_grid: GridMatrix) -> None:
        """Test GridMatrix.header_row() method."""
        headers = sample_grid.header_row()
        assert len(headers) == 3
        assert all(h.is_header for h in headers)

    def test_grid_matrix_get_row(self, sample_grid: GridMatrix) -> None:
        """Test GridMatrix.get_row() method."""
        row = sample_grid.get_row(1)
        assert len(row) == 3
        assert row[0].text == "VCC"

    def test_grid_matrix_get_col(self, sample_grid: GridMatrix) -> None:
        """Test GridMatrix.get_col() method."""
        col = sample_grid.get_col(0)
        assert len(col) == 2
        assert col[0].text == "Parameter"
        assert col[1].text == "VCC"

    def test_phase2_output_creation(self, sample_grid: GridMatrix) -> None:
        """Test Phase2Output creation."""
        output = Phase2Output(
            source_pdf_hash="abc123",
            grids=[sample_grid],
            footnote_maps=[],
            processing_time_ms=500.0,
        )
        assert output.source_pdf_hash == "abc123"
        assert len(output.grids) == 1
        assert output.processing_time_ms == 500.0

    def test_phase2_output_get_grid(self, sample_grid: GridMatrix) -> None:
        """Test Phase2Output.get_grid() method."""
        output = Phase2Output(
            source_pdf_hash="abc123",
            grids=[sample_grid],
            footnote_maps=[],
            processing_time_ms=500.0,
        )
        grid = output.get_grid(1, 0)
        assert grid is not None
        assert grid.source_page == 1


# =============================================================================
# Confidence Scorer Tests
# =============================================================================


class TestConfidenceScorer:
    """Tests for confidence scoring functions."""

    def test_score_grid_returns_0_for_none(self) -> None:
        """Test score_grid returns 0 for None input."""
        score = score_grid(None)
        assert score == 0.0

    def test_score_grid_perfect_grid(self) -> None:
        """Test score_grid for a perfect grid."""
        cells = [
            CellValue(text="Header", row=0, col=0, is_header=True),
            CellValue(text="Val1", row=1, col=0),
            CellValue(text="Val2", row=2, col=0),
            CellValue(text="Val3", row=3, col=0),
            CellValue(text="Val4", row=4, col=0),
        ]
        grid = GridMatrix(
            cells=cells,
            num_rows=5,
            num_cols=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vector",
            confidence=0.97,
        )
        score = score_grid(grid)
        # Should be high (has cells > 4, no empty, has header, valid parse)
        assert score > 0.75

    def test_score_grid_empty_cells_penalty(self) -> None:
        """Test score_grid penalizes many empty cells."""
        cells = [
            CellValue(text="Header", row=0, col=0, is_header=True),
            CellValue(text="", row=1, col=0),
            CellValue(text="", row=2, col=0),
            CellValue(text="", row=3, col=0),
            CellValue(text="", row=4, col=0),
        ]
        grid = GridMatrix(
            cells=cells,
            num_rows=5,
            num_cols=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vector",
            confidence=0.97,
        )
        score = score_grid(grid)
        # Should be lower due to many empty cells
        assert score < 0.8

    def test_score_grid_no_header_penalty(self) -> None:
        """Test score_grid penalizes no header."""
        cells = [
            CellValue(text="Val1", row=0, col=0, is_header=False),
            CellValue(text="Val2", row=1, col=0, is_header=False),
            CellValue(text="Val3", row=2, col=0, is_header=False),
            CellValue(text="Val4", row=3, col=0, is_header=False),
            CellValue(text="Val5", row=4, col=0, is_header=False),
        ]
        grid = GridMatrix(
            cells=cells,
            num_rows=5,
            num_cols=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vector",
            confidence=0.97,
        )
        score = score_grid(grid)
        # Should be at most 0.75 (missing header criterion)
        assert score <= 0.75

    def test_pick_best_grid_returns_vector_when_only_valid(self, sample_grid: GridMatrix) -> None:
        """Test pick_best_grid prefers vector over VLM when both succeed."""
        vlm_grid = GridMatrix(
            cells=sample_grid.cells,
            num_rows=2,
            num_cols=3,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vlm",
            confidence=0.82,
        )
        
        # Vector has higher score, should be selected
        result = pick_best_grid(sample_grid, vlm_grid)
        assert result.extraction_path == "vector"

    def test_pick_best_grid_returns_vlm_when_only_valid(self, sample_grid: GridMatrix) -> None:
        """Test pick_best_grid returns VLM when only valid path."""
        vlm_grid = GridMatrix(
            cells=sample_grid.cells,
            num_rows=2,
            num_cols=3,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vlm",
            confidence=0.82,
        )
        
        result = pick_best_grid(None, vlm_grid)
        assert result.extraction_path == "vlm"

    def test_pick_best_grid_raises_when_both_none(self) -> None:
        """Test pick_best_grid raises ValueError when both paths fail."""
        with pytest.raises(ValueError) as exc_info:
            pick_best_grid(None, None)
        assert "Both TSR paths failed" in str(exc_info.value)

    def test_pick_best_grid_attaches_confidence(self, sample_grid: GridMatrix) -> None:
        """Test pick_best_grid attaches score_grid as confidence."""
        result = pick_best_grid(sample_grid, None)
        # Confidence should be updated to score_grid result
        assert result.confidence == score_grid(sample_grid)


# =============================================================================
# Merged Cell Handler Tests
# =============================================================================


class TestMergedCellHandler:
    """Tests for merged cell detection."""

    def test_detect_merged_cells_vector_path_no_merges(self, sample_grid: GridMatrix) -> None:
        """Test detect_merged_cells on grid without merged cells."""
        result = detect_merged_cells(sample_grid)
        assert result.has_merged_cells is False

    def test_detect_merged_cells_detects_colspan(self) -> None:
        """Test detect_merged_cells detects colspan from duplicate text."""
        # Create grid with merged cells (same text in adjacent positions)
        cells = [
            CellValue(text="Header", row=0, col=0, is_header=True),
            CellValue(text="Header", row=0, col=1, is_header=True),  # Same text = merged
            CellValue(text="Value1", row=1, col=0),
            CellValue(text="Value2", row=1, col=1),
        ]
        grid = GridMatrix(
            cells=cells,
            num_rows=2,
            num_cols=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vector",
            confidence=0.97,
        )
        
        result = detect_merged_cells(grid)
        assert result.has_merged_cells is True
        
        # Check that colspan was set on first "Header" cell
        header_cells = [c for c in result.cells if c.text == "Header"]
        assert any(c.colspan > 1 for c in header_cells)

    def test_detect_merged_cells_vlm_path(self) -> None:
        """Test detect_merged_cells handles VLM path."""
        cells = [
            CellValue(text="A", row=0, col=0),
            CellValue(text="A", row=0, col=1),  # Same = merged
            CellValue(text="B", row=1, col=0),
            CellValue(text="C", row=1, col=1),
        ]
        grid = GridMatrix(
            cells=cells,
            num_rows=2,
            num_cols=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vlm",
            confidence=0.82,
        )
        
        result = detect_merged_cells(grid)
        # Should detect merged cells
        assert result.has_merged_cells is True


# =============================================================================
# Path A (Vector) Tests
# =============================================================================


class TestPathAVector:
    """Tests for vector path extraction."""

    @patch("src.datasheet.phase2_tsr.path_a_vector._has_lattice_lines")
    @patch("src.datasheet.phase2_tsr.path_a_vector._camelot_to_grid_matrix")
    def test_path_a_returns_none_for_borderless_table(
        self,
        mock_camelot,
        mock_has_lattice,
    ) -> None:
        """Test Path A returns None for borderless table (no Camelot lines)."""
        mock_has_lattice.return_value = False
        
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        
        table_crop = TableCrop(
            page_number=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=buffer.getvalue(),
            bounding_box=(100, 100, 700, 400),
            detection_confidence=0.95,
        )
        
        from src.datasheet.phase2_tsr.path_a_vector import extract_table_vector_path
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf")
            pdf_path = Path(tmp.name)
        
        try:
            config = MagicMock()
            result = extract_table_vector_path(pdf_path, table_crop, 0, config)
            
            assert result is None
            mock_has_lattice.assert_called_once()
        finally:
            pdf_path.unlink()


# =============================================================================
# Path B (VLM) Tests
# =============================================================================


class TestPathBVLM:
    """Tests for VLM path extraction."""

    def test_parse_markdown_table_3x4(self) -> None:
        """Test parsing a 3x4 markdown table into GridMatrix."""
        from src.datasheet.phase2_tsr.path_b_vlm import _parse_markdown_to_grid_matrix
        
        markdown = """| Parameter | Min | Typ | Max |
| --------- | --- | --- | --- |
| VCC | 2.7V | 3.3V | 5.5V |
| VOUT | 3.2V | 3.3V | 3.4V |"""
        
        grid, confidence = _parse_markdown_to_grid_matrix(
            markdown,
            TableSectionType.ELECTRICAL_CHARACTERISTICS,
            1,
            0,
        )
        
        assert grid is not None
        assert grid.num_rows == 3
        assert grid.num_cols == 4
        assert grid.extraction_path == "vlm"
        assert confidence == 0.82
        
        # Check header cells
        header_cells = [c for c in grid.cells if c.is_header]
        assert len(header_cells) == 4
        
        # Check content cells
        vcc_cell = next((c for c in grid.cells if c.text == "VCC"), None)
        assert vcc_cell is not None
        assert vcc_cell.row == 1

    def test_parse_markdown_with_empty_cells(self) -> None:
        """Test parsing markdown with empty cells."""
        from src.datasheet.phase2_tsr.path_b_vlm import _parse_markdown_to_grid_matrix
        
        markdown = """| A | B |
| - | - |
| 1 | |"""
        
        grid, _ = _parse_markdown_to_grid_matrix(
            markdown,
            TableSectionType.ELECTRICAL_CHARACTERISTICS,
            1,
            0,
        )
        
        assert grid is not None
        empty_cells = [c for c in grid.cells if c.text == ""]
        assert len(empty_cells) > 0

    def test_parse_markdown_failure_returns_none(self) -> None:
        """Test parsing invalid markdown returns None."""
        from src.datasheet.phase2_tsr.path_b_vlm import _parse_markdown_to_grid_matrix
        
        invalid_markdown = "This is not a table"
        
        grid, confidence = _parse_markdown_to_grid_matrix(
            invalid_markdown,
            TableSectionType.ELECTRICAL_CHARACTERISTICS,
            1,
            0,
        )
        
        assert grid is None
        assert confidence == 0.50  # Parse failure confidence


# =============================================================================
# Process Integration Tests
# =============================================================================


class TestProcess:
    """Integration tests for process() function."""

    @patch("src.datasheet.phase2_tsr.extract_table_vector_path")
    @patch("src.datasheet.phase2_tsr.extract_table_vlm_path")
    def test_process_returns_phase2_output(
        self,
        mock_vlm,
        mock_vector,
        mock_phase1_output,
        mock_config,
        sample_grid,
    ) -> None:
        """Test process() returns a Phase2Output with correct grid count."""
        # Setup mocks to return sample grid
        mock_vector.return_value = sample_grid
        mock_vlm.return_value = None  # VLM fails
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            pdf_path = Path(tmp.name)
        
        try:
            # Update phase1 output with temp path
            mock_phase1_output.pdf_path = str(pdf_path)
            
            result = process(mock_phase1_output, mock_config)
            
            assert isinstance(result, Phase2Output)
            assert len(result.grids) == 3  # 3 table crops in fixture
            assert result.source_pdf_hash == mock_phase1_output.source_pdf_hash
            assert result.processing_time_ms > 0
        finally:
            pdf_path.unlink()

    @patch("src.datasheet.phase2_tsr.extract_table_vector_path")
    @patch("src.datasheet.phase2_tsr.extract_table_vlm_path")
    def test_process_passes_footnote_maps_unchanged(
        self,
        mock_vlm,
        mock_vector,
        mock_phase1_output,
        mock_config,
        sample_grid,
    ) -> None:
        """Test process() passes footnote_maps through unchanged."""
        mock_vector.return_value = sample_grid
        mock_vlm.return_value = None
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            pdf_path = Path(tmp.name)
        
        try:
            mock_phase1_output.pdf_path = str(pdf_path)
            
            result = process(mock_phase1_output, mock_config)
            
            # Footnote maps should be passed through unchanged
            assert len(result.footnote_maps) == len(mock_phase1_output.footnote_maps)
            assert result.footnote_maps[0].page_number == 1
            assert result.footnote_maps[0].entries["1"] == "Valid for T_A = 25°C"
        finally:
            pdf_path.unlink()

    def test_process_raises_file_not_found_for_missing_pdf(
        self,
        mock_phase1_output,
        mock_config,
    ) -> None:
        """Test process() raises FileNotFoundError for missing PDF."""
        mock_phase1_output.pdf_path = "/nonexistent/path.pdf"
        
        with pytest.raises(FileNotFoundError):
            process(mock_phase1_output, mock_config)

    @patch("src.datasheet.phase2_tsr.extract_table_vector_path")
    @patch("src.datasheet.phase2_tsr.extract_table_vlm_path")
    def test_process_continues_when_table_fails(
        self,
        mock_vlm,
        mock_vector,
        mock_phase1_output,
        mock_config,
    ) -> None:
        """Test process() continues when one table fails extraction."""
        # Create a sample grid for success cases
        success_grid = GridMatrix(
            cells=[
                CellValue(text="H", row=0, col=0, is_header=True),
                CellValue(text="V", row=1, col=0),
            ],
            num_rows=2,
            num_cols=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vector",
            confidence=0.97,
        )
        
        # Make first table succeed, others fail
        mock_vector.side_effect = [
            success_grid,  # First succeeds
            None,  # Second - vector fails
            None,  # Third - vector fails
        ]
        mock_vlm.return_value = None  # VLM always fails
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            pdf_path = Path(tmp.name)
        
        try:
            mock_phase1_output.pdf_path = str(pdf_path)
            
            # Mock pick_best_grid to fail on None,None
            with patch("src.datasheet.phase2_tsr.pick_best_grid") as mock_pick:
                mock_pick.side_effect = [
                    success_grid,  # First table succeeds
                    ValueError("Both paths failed"),  # Second fails
                    ValueError("Both paths failed"),  # Third fails
                ]
                
                result = process(mock_phase1_output, mock_config)
                
                # Should have 1 successful grid (first table)
                assert len(result.grids) == 1
        finally:
            pdf_path.unlink()


# =============================================================================
# End-to-End Workflow Tests
# =============================================================================


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    def test_full_workflow_vector_path_wins(self) -> None:
        """Test full workflow where vector path produces better grid."""
        # Create grids with different scores
        vector_cells = [
            CellValue(text="H1", row=0, col=0, is_header=True),
            CellValue(text="H2", row=0, col=1, is_header=True),
            CellValue(text="V1", row=1, col=0),
            CellValue(text="V2", row=1, col=1),
            CellValue(text="V3", row=2, col=0),
            CellValue(text="V4", row=2, col=1),
        ]
        vector_grid = GridMatrix(
            cells=vector_cells,
            num_rows=3,
            num_cols=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vector",
            confidence=0.97,
        )
        
        # VLM grid with fewer cells (worse score)
        vlm_cells = [
            CellValue(text="H1", row=0, col=0, is_header=True),
            CellValue(text="V1", row=1, col=0),
        ]
        vlm_grid = GridMatrix(
            cells=vlm_cells,
            num_rows=2,
            num_cols=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vlm",
            confidence=0.82,
        )
        
        # Vector should win (more cells, better score)
        winner = pick_best_grid(vector_grid, vlm_grid)
        assert winner.extraction_path == "vector"

    def test_full_workflow_vlm_path_wins(self) -> None:
        """Test full workflow where VLM path produces better grid."""
        # Vector grid with many empty cells
        vector_cells = [
            CellValue(text="H1", row=0, col=0, is_header=True),
            CellValue(text="", row=1, col=0),
            CellValue(text="", row=2, col=0),
        ]
        vector_grid = GridMatrix(
            cells=vector_cells,
            num_rows=3,
            num_cols=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vector",
            confidence=0.97,
        )
        
        # VLM grid with good content
        vlm_cells = [
            CellValue(text="H1", row=0, col=0, is_header=True),
            CellValue(text="H2", row=0, col=1, is_header=True),
            CellValue(text="V1", row=1, col=0),
            CellValue(text="V2", row=1, col=1),
            CellValue(text="V3", row=2, col=0),
            CellValue(text="V4", row=2, col=1),
        ]
        vlm_grid = GridMatrix(
            cells=vlm_cells,
            num_rows=3,
            num_cols=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
            extraction_path="vlm",
            confidence=0.82,
        )
        
        # VLM should win (better cell distribution)
        winner = pick_best_grid(vector_grid, vlm_grid)
        assert winner.extraction_path == "vlm"
