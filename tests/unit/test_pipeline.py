"""Unit tests for src/datasheet/pipeline.py.

Tests the parse_datasheet orchestrator including:
- Phase ordering (1→2→3→4→5)
- Phase 5 conditional execution
- Verdict application
- Error handling with DatasheetPipelineError
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.datasheet.pipeline import DatasheetPipelineError, parse_datasheet
from src.datasheet.phase1_dla._schemas import Phase1Output, TableCrop
from src.datasheet.phase2_tsr._schemas import GridMatrix, Phase2Output
from src.datasheet.phase4_validate import ValidationResult
from src.schemas.datasheet import (
    ComponentDatasheet,
    ExtractionMethod,
    PlacementConstraint,
    TableSectionType,
)


class TestParseDatasheet:
    """Tests for parse_datasheet orchestrator."""

    @pytest.fixture
    def mock_config(self, tmp_path) -> Config:
        """Create mock Config."""
        config = MagicMock(spec=Config)
        config.output_dir = tmp_path / "output"
        config.review_queue_path = tmp_path / "review.db"
        return config

    @pytest.fixture
    def sample_pdf(self, tmp_path) -> Path:
        """Create a sample PDF file."""
        pdf_path = tmp_path / "test_datasheet.pdf"
        # Minimal valid PDF header
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n")
        return pdf_path

    @pytest.fixture
    def phase1_output_no_layout(self) -> Phase1Output:
        """Phase1Output with no layout sections."""
        crops = [
            TableCrop(
                image_bytes=b"dummy",
                page_number=1,
                bounding_box=(100, 100, 500, 500),
                section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
                detection_confidence=0.95,
            ),
        ]
        return Phase1Output(
            pdf_path="test.pdf",
            source_pdf_hash="abc123",
            total_pages=5,
            table_crops=crops,
            footnote_maps=[],
            processing_time_ms=1000.0,
        )

    @pytest.fixture
    def phase1_output_with_layout(self) -> Phase1Output:
        """Phase1Output with layout recommendation sections."""
        crops = [
            TableCrop(
                image_bytes=b"dummy",
                page_number=1,
                bounding_box=(100, 100, 500, 500),
                section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
                detection_confidence=0.95,
            ),
            TableCrop(
                image_bytes=b"dummy",
                page_number=2,
                bounding_box=(100, 100, 900, 500),
                section_type=TableSectionType.LAYOUT_RECOMMENDATIONS,
                detection_confidence=0.93,
            ),
        ]
        return Phase1Output(
            pdf_path="test.pdf",
            source_pdf_hash="abc123",
            total_pages=5,
            table_crops=crops,
            footnote_maps=[],
            processing_time_ms=1000.0,
        )

    @pytest.fixture
    def phase2_output(self) -> Phase2Output:
        """Sample Phase2Output."""
        return Phase2Output(
            source_pdf_hash="abc123",
            grids=[],
            footnote_maps=[],
            processing_time_ms=500.0,
        )

    @pytest.fixture
    def component_datasheet(self) -> ComponentDatasheet:
        """Sample ComponentDatasheet."""
        return ComponentDatasheet(
            component_id="",
            manufacturer="Test Corp",
            description="Test component",
            package="SOT-23-5",
            source_pdf_hash="abc123",
            extraction_method=ExtractionMethod.P1_VECTOR,
            extraction_confidence=0.85,
            created_at="2024-01-01T00:00:00Z",
        )

    def test_parse_datasheet_calls_all_phases_in_order(
        self,
        sample_pdf,
        mock_config,
        phase1_output_no_layout,
        phase2_output,
        component_datasheet,
    ) -> None:
        """Mock all 5 phases — verify they are called in correct order."""
        with patch("src.datasheet.pipeline.phase1_dla") as mock_p1:
            with patch("src.datasheet.pipeline.phase2_tsr") as mock_p2:
                with patch("src.datasheet.pipeline.phase3_extract") as mock_p3:
                    with patch("src.datasheet.phase4_validate.apply_verdict") as mock_p4:
                        with patch("src.datasheet.phase4_validate.validate") as mock_validate:
                            with patch("src.datasheet.pipeline.enqueue") as mock_queue:
                                # Setup mocks
                                mock_p1.return_value = phase1_output_no_layout
                                mock_p2.return_value = phase2_output
                                mock_p3.return_value = component_datasheet

                                # Phase 4 mocks
                                validation_result = ValidationResult(
                                    verdict="PASS",
                                    severity="WARNING",
                                    confidence=0.85,
                                    flags=[],
                                )
                                mock_validate.return_value = validation_result
                                mock_p4.return_value = component_datasheet.model_copy(
                                    update={"review_required": False}
                                )

                                result = parse_datasheet("TEST123", sample_pdf, mock_config)

                                # Verify phases called in order
                                mock_p1.assert_called_once()
                                mock_p2.assert_called_once()
                                mock_p3.assert_called_once()
                                mock_p4.assert_called_once()

                                # Verify Phase 1 called with correct args
                                assert mock_p1.call_args[0][0] == sample_pdf

                                # Verify Phase 2 called with Phase 1 output
                                assert mock_p2.call_args[0][0] == phase1_output_no_layout

                                # Verify Phase 3 called with Phase 2 output
                                assert mock_p3.call_args[0][0] == phase2_output

    def test_phase_5_skipped_when_no_layout_sections(
        self,
        sample_pdf,
        mock_config,
        phase1_output_no_layout,
        phase2_output,
        component_datasheet,
    ) -> None:
        """Test Phase 5 is skipped when no LAYOUT_RECOMMENDATIONS in Phase1Output."""
        with patch("src.datasheet.pipeline.phase1_dla") as mock_p1:
            with patch("src.datasheet.pipeline.phase2_tsr") as mock_p2:
                with patch("src.datasheet.pipeline.phase3_extract") as mock_p3:
                    with patch("src.datasheet.phase4_validate.apply_verdict") as mock_p4:
                        with patch("src.datasheet.phase4_validate.validate") as mock_validate:
                            with patch("src.datasheet.pipeline.extract_layout_constraints") as mock_p5:
                                with patch("src.datasheet.pipeline.enqueue"):
                                    mock_p1.return_value = phase1_output_no_layout
                                    mock_p2.return_value = phase2_output
                                    mock_p3.return_value = component_datasheet

                                    validation_result = ValidationResult(
                                        verdict="PASS",
                                        severity="WARNING",
                                        confidence=0.85,
                                        flags=[],
                                    )
                                    mock_validate.return_value = validation_result
                                    mock_p4.return_value = component_datasheet.model_copy(
                                        update={"review_required": False}
                                    )

                                    result = parse_datasheet("TEST123", sample_pdf, mock_config)

                                    # Phase 5 should NOT be called
                                    mock_p5.assert_not_called()

    def test_phase_5_called_when_layout_sections_present(
        self,
        sample_pdf,
        mock_config,
        phase1_output_with_layout,
        phase2_output,
        component_datasheet,
    ) -> None:
        """Test Phase 5 is called when LAYOUT_RECOMMENDATIONS present."""
        with patch("src.datasheet.pipeline.phase1_dla") as mock_p1:
            with patch("src.datasheet.pipeline.phase2_tsr") as mock_p2:
                with patch("src.datasheet.pipeline.phase3_extract") as mock_p3:
                    with patch("src.datasheet.phase4_validate.apply_verdict") as mock_p4:
                        with patch("src.datasheet.phase4_validate.validate") as mock_validate:
                            with patch("src.datasheet.pipeline.extract_layout_constraints") as mock_p5:
                                with patch("src.datasheet.pipeline.enqueue"):
                                    mock_p1.return_value = phase1_output_with_layout
                                    mock_p2.return_value = phase2_output
                                    mock_p3.return_value = component_datasheet

                                    layout_constraints = [
                                        PlacementConstraint(
                                            constraint_type="proximity",
                                            subject="C1",
                                            relative_to="U1.VIN",
                                            relative_to_type="pin",
                                            max_distance_mm=5.0,
                                            source_sentence="Test",
                                            confidence=0.9,
                                        )
                                    ]
                                    mock_p5.return_value = layout_constraints

                                    validation_result = ValidationResult(
                                        verdict="PASS",
                                        severity="WARNING",
                                        confidence=0.85,
                                        flags=[],
                                    )
                                    mock_validate.return_value = validation_result
                                    mock_p4.return_value = component_datasheet.model_copy(
                                        update={"review_required": False}
                                    )

                                    result = parse_datasheet("TEST123", sample_pdf, mock_config)

                                    # Phase 5 SHOULD be called
                                    mock_p5.assert_called_once()

                                    # Verify correct args passed
                                    call_args = mock_p5.call_args
                                    assert call_args[0][0] == sample_pdf
                                    assert call_args[0][1] == phase1_output_with_layout

    def test_apply_verdict_return_value_captured(
        self,
        sample_pdf,
        mock_config,
        phase1_output_no_layout,
        phase2_output,
        component_datasheet,
    ) -> None:
        """Test apply_verdict return value is captured (use a mock that returns different object)."""
        # Create a modified version that apply_verdict will return
        modified_datasheet = component_datasheet.model_copy(
            update={
                "review_required": True,
                "review_flags": ["Test flag"],
            }
        )

        with patch("src.datasheet.pipeline.phase1_dla") as mock_p1:
            with patch("src.datasheet.pipeline.phase2_tsr") as mock_p2:
                with patch("src.datasheet.pipeline.phase3_extract") as mock_p3:
                    with patch("src.datasheet.phase4_validate.apply_verdict") as mock_p4:
                        with patch("src.datasheet.phase4_validate.validate") as mock_validate:
                            with patch("src.datasheet.pipeline.enqueue"):
                                mock_p1.return_value = phase1_output_no_layout
                                mock_p2.return_value = phase2_output
                                mock_p3.return_value = component_datasheet

                                validation_result = ValidationResult(
                                    verdict="WARN",
                                    severity="WARNING",
                                    confidence=0.85,
                                    flags=["Test flag"],
                                )
                                mock_validate.return_value = validation_result

                                # apply_verdict returns a DIFFERENT object
                                mock_p4.return_value = modified_datasheet

                                result = parse_datasheet("TEST123", sample_pdf, mock_config)

                                # Result should be the modified datasheet
                                assert result.review_required is True
                                assert result.review_flags == ["Test flag"]

                                # Verify apply_verdict was called
                                mock_p4.assert_called_once()

    def test_datasheet_pipeline_error_raised_on_phase_failure(
        self,
        sample_pdf,
        mock_config,
    ) -> None:
        """Test DatasheetPipelineError is raised with correct phase name when Phase 3 raises."""
        with patch("src.datasheet.pipeline.phase1_dla") as mock_p1:
            with patch("src.datasheet.pipeline.phase2_tsr") as mock_p2:
                with patch("src.datasheet.pipeline.phase3_extract") as mock_p3:
                    mock_p1.return_value = MagicMock()
                    mock_p1.return_value.table_crops = []
                    mock_p2.return_value = MagicMock()
                    mock_p2.return_value.grids = []
                    mock_p2.return_value.source_pdf_hash = "abc"
                    mock_p2.return_value.footnote_maps = []

                    # Phase 3 raises an exception
                    mock_p3.side_effect = RuntimeError("LLM extraction failed")

                    with pytest.raises(DatasheetPipelineError) as exc_info:
                        parse_datasheet("TEST123", sample_pdf, mock_config)

                    # Verify error properties
                    error = exc_info.value
                    assert "Phase 3" in error.phase
                    assert error.component_id == "TEST123"
                    assert isinstance(error.cause, RuntimeError)
                    assert "LLM extraction failed" in str(error.cause)

    def test_component_id_set_on_returned_datasheet(
        self,
        sample_pdf,
        mock_config,
        phase1_output_no_layout,
        phase2_output,
        component_datasheet,
    ) -> None:
        """Test component_id is set on returned ComponentDatasheet."""
        # Ensure component_id is empty in initial datasheet
        assert component_datasheet.component_id == ""

        with patch("src.datasheet.pipeline.phase1_dla") as mock_p1:
            with patch("src.datasheet.pipeline.phase2_tsr") as mock_p2:
                with patch("src.datasheet.pipeline.phase3_extract") as mock_p3:
                    with patch("src.datasheet.phase4_validate.apply_verdict") as mock_p4:
                        with patch("src.datasheet.phase4_validate.validate") as mock_validate:
                            with patch("src.datasheet.pipeline.enqueue"):
                                mock_p1.return_value = phase1_output_no_layout
                                mock_p2.return_value = phase2_output
                                mock_p3.return_value = component_datasheet

                                validation_result = ValidationResult(
                                    verdict="PASS",
                                    severity="WARNING",
                                    confidence=0.85,
                                    flags=[],
                                )
                                mock_validate.return_value = validation_result
                                mock_p4.return_value = component_datasheet.model_copy(
                                    update={"review_required": False}
                                )

                                result = parse_datasheet("MYCOMPONENT-123", sample_pdf, mock_config)

                                # Component ID should be set
                                assert result.component_id == "MYCOMPONENT-123"

    def test_file_not_found_raised_before_pipeline(self, mock_config) -> None:
        """Test FileNotFoundError raised before pipeline starts if PDF missing."""
        missing_pdf = Path("/nonexistent/path/to/datasheet.pdf")

        with pytest.raises(FileNotFoundError):
            parse_datasheet("TEST123", missing_pdf, mock_config)

    def test_datasheet_pipeline_error_has_correct_attributes(self) -> None:
        """Test DatasheetPipelineError attributes are accessible."""
        cause = ValueError("Original error")
        error = DatasheetPipelineError("Phase 2", "COMP-456", cause)

        assert error.phase == "Phase 2"
        assert error.component_id == "COMP-456"
        assert error.cause is cause
        assert "Phase 2" in str(error)
        assert "COMP-456" in str(error)
        assert "Original error" in str(error)
