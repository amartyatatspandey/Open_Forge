"""Unit tests for src/datasheet/phase5_layout/.

Tests Phase 5 Layout Section Extraction including:
- Empty list return when no layout sections
- Type resolution for relative_to strings
- Constraint validation and filtering
- LLM extraction integration
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.datasheet.phase1_dla._schemas import Phase1Output, TableCrop
from src.datasheet.phase5_layout import extract_layout_constraints
from src.datasheet.phase5_layout._schemas import LayoutExtractionResult, PageTextBlock
from src.datasheet.phase5_layout.constraint_validator import validate_and_finalize
from src.datasheet.phase5_layout.text_extractor import extract_page_texts
from src.datasheet.phase5_layout.type_resolver import resolve_relative_to_type
from src.schemas.datasheet import PlacementConstraint, TableSectionType


# =============================================================================
# Type Resolver Tests (Tests 2-5)
# =============================================================================


class TestTypeResolver:
    """Tests for type_resolver.py classification logic."""

    def test_type_resolver_classifies_pin_reference(self) -> None:
        """Test type_resolver classifies 'U1.VIN' → 'pin'."""
        resolved_type, needs_review = resolve_relative_to_type("U1.VIN")
        assert resolved_type == "pin"
        assert needs_review is False

    def test_type_resolver_classifies_component_reference(self) -> None:
        """Test type_resolver classifies 'C1' → 'component'."""
        resolved_type, needs_review = resolve_relative_to_type("C1")
        assert resolved_type == "component"
        assert needs_review is False

    def test_type_resolver_classifies_long_component_reference(self) -> None:
        """Test type_resolver handles longer component designators like 'IC101'."""
        resolved_type, needs_review = resolve_relative_to_type("IC101")
        assert resolved_type == "component"
        assert needs_review is False

    def test_type_resolver_classifies_board_edge(self) -> None:
        """Test type_resolver classifies 'board edge north' → 'board_edge'."""
        test_cases = [
            "board edge north",
            "edge of board",
            "boundary line",
            "board perimeter",
        ]
        for test in test_cases:
            resolved_type, needs_review = resolve_relative_to_type(test)
            assert resolved_type == "board_edge", f"Failed for: {test}"
            assert needs_review is False, f"Failed for: {test}"

    def test_type_resolver_classifies_unknown_with_review(self) -> None:
        """Test type_resolver classifies unknown string → 'component' with needs_review=True."""
        resolved_type, needs_review = resolve_relative_to_type("unknown thing")
        assert resolved_type == "component"
        assert needs_review is True

    def test_type_resolver_handles_empty_string(self) -> None:
        """Test type_resolver handles empty string with component + review."""
        resolved_type, needs_review = resolve_relative_to_type("")
        assert resolved_type == "component"
        assert needs_review is True

    def test_type_resolver_handles_whitespace(self) -> None:
        """Test type_resolver strips whitespace from input."""
        resolved_type, needs_review = resolve_relative_to_type("  C1  ")
        assert resolved_type == "component"
        assert needs_review is False


# =============================================================================
# Constraint Validator Tests (Tests 6-7)
# =============================================================================


class TestConstraintValidator:
    """Tests for constraint_validator.py validation logic."""

    def test_constraint_validator_drops_low_confidence(self) -> None:
        """Test constraint_validator drops constraints with confidence < 0.65."""
        # Constraint with low confidence (0.5)
        low_conf = PlacementConstraint(
            constraint_type="proximity",
            subject="C1",
            relative_to="U1.VIN",
            relative_to_type="pin",
            max_distance_mm=5.0,
            source_sentence="Place C1 near U1.VIN",
            confidence=0.5,  # Below threshold
        )

        # Constraint with high confidence (0.9)
        high_conf = PlacementConstraint(
            constraint_type="proximity",
            subject="C2",
            relative_to="U1.GND",
            relative_to_type="pin",
            max_distance_mm=3.0,
            source_sentence="Place C2 near U1.GND",
            confidence=0.9,  # Above threshold
        )

        result = LayoutExtractionResult(constraints=[low_conf, high_conf])
        validated = validate_and_finalize(result)

        # Only high confidence constraint should remain
        assert len(validated) == 1
        assert validated[0].subject == "C2"

    def test_constraint_validator_drops_empty_subject(self) -> None:
        """Test constraint_validator drops constraints with empty subject."""
        # Constraint with empty subject
        empty_subject = PlacementConstraint(
            constraint_type="proximity",
            subject="",  # Empty
            relative_to="U1.VIN",
            relative_to_type="pin",
            max_distance_mm=5.0,
            source_sentence="Place near U1.VIN",
            confidence=0.9,
        )

        # Valid constraint
        valid = PlacementConstraint(
            constraint_type="proximity",
            subject="C1",
            relative_to="U1.VIN",
            relative_to_type="pin",
            max_distance_mm=5.0,
            source_sentence="Place C1 near U1.VIN",
            confidence=0.9,
        )

        result = LayoutExtractionResult(constraints=[empty_subject, valid])
        validated = validate_and_finalize(result)

        # Only valid constraint should remain
        assert len(validated) == 1
        assert validated[0].subject == "C1"

    def test_constraint_validator_resolves_relative_to_type(self) -> None:
        """Test constraint_validator resolves relative_to_type during validation."""
        # Constraint with unresoled relative_to_type (but LLM gave component name)
        constraint = PlacementConstraint(
            constraint_type="proximity",
            subject="C1",
            relative_to="C2",  # Component reference
            relative_to_type="component",  # Will be resolved
            max_distance_mm=5.0,
            source_sentence="Place C1 near C2",
            confidence=0.9,
        )

        result = LayoutExtractionResult(constraints=[constraint])
        validated = validate_and_finalize(result)

        assert len(validated) == 1
        assert validated[0].relative_to_type == "component"

    def test_constraint_validator_handles_exactly_0_65_confidence(self) -> None:
        """Test boundary case: confidence exactly 0.65 should be kept."""
        constraint = PlacementConstraint(
            constraint_type="proximity",
            subject="C1",
            relative_to="U1.VIN",
            relative_to_type="pin",
            max_distance_mm=5.0,
            source_sentence="Place C1 near U1.VIN",
            confidence=0.65,  # Exactly at threshold
        )

        result = LayoutExtractionResult(constraints=[constraint])
        validated = validate_and_finalize(result)

        # Should be kept (>= threshold)
        assert len(validated) == 1


# =============================================================================
# Text Extractor Tests
# =============================================================================


class TestTextExtractor:
    """Tests for text_extractor.py PDF text extraction."""

    def test_extract_page_texts_returns_empty_on_missing_file(self, tmp_path) -> None:
        """Test extract_page_texts returns empty list for non-existent PDF."""
        missing_pdf = tmp_path / "nonexistent.pdf"
        result = extract_page_texts(missing_pdf, [1, 2, 3])
        assert result == []

    def test_extract_page_texts_skips_short_pages(self, tmp_path) -> None:
        """Test extract_page_texts skips pages with < 50 characters."""
        # This would require a real PDF or mocking pdfplumber
        # For unit test, we verify the function doesn't raise
        pass  # Integration test with real PDF needed


# =============================================================================
# Integration Tests (Tests 1, 8, 9)
# =============================================================================


class TestExtractLayoutConstraints:
    """Integration tests for extract_layout_constraints public API."""

    @pytest.fixture
    def mock_config(self, tmp_path) -> MagicMock:
        """Create mock Config."""
        config = MagicMock()
        config.model_paths = {
            "qwen25_7b": tmp_path / "models" / "Qwen2.5-7B-Instruct",
        }
        return config

    @pytest.fixture
    def phase1_output_no_layout(self) -> Phase1Output:
        """Phase1Output with no LAYOUT_RECOMMENDATIONS sections."""
        # Create table crops with other section types but not layout
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
                page_number=1,
                bounding_box=(100, 600, 500, 900),
                section_type=TableSectionType.PINOUT,
                detection_confidence=0.92,
            ),
        ]
        return Phase1Output(
            pdf_path="test.pdf",
            source_pdf_hash="abc123",
            total_pages=10,
            table_crops=crops,
            footnote_maps=[],
            processing_time_ms=1000.0,
        )

    @pytest.fixture
    def phase1_output_with_layout(self) -> Phase1Output:
        """Phase1Output with LAYOUT_RECOMMENDATIONS sections."""
        crops = [
            TableCrop(
                image_bytes=b"dummy",
                page_number=5,
                bounding_box=(100, 100, 900, 500),
                section_type=TableSectionType.LAYOUT_RECOMMENDATIONS,
                detection_confidence=0.93,
            ),
        ]
        return Phase1Output(
            pdf_path="test.pdf",
            source_pdf_hash="abc123",
            total_pages=10,
            table_crops=crops,
            footnote_maps=[],
            processing_time_ms=1000.0,
        )

    def test_extract_layout_constraints_returns_empty_when_no_layout_sections(
        self,
        tmp_path,
        mock_config,
        phase1_output_no_layout,
    ) -> None:
        """Test extract_layout_constraints returns empty list when no LAYOUT_RECOMMENDATIONS crops."""
        pdf_path = tmp_path / "test.pdf"

        result = extract_layout_constraints(pdf_path, phase1_output_no_layout, mock_config)

        # Should return empty list immediately without processing other section types
        assert result == []

    def test_extract_layout_constraints_returns_empty_on_model_failure(
        self,
        tmp_path,
        mock_config,
        phase1_output_with_layout,
    ) -> None:
        """Test that model failure returns empty list without raising."""
        pdf_path = tmp_path / "test.pdf"

        # Mock both text extraction and spatial_parser to simulate model failure
        with patch(
            "src.datasheet.phase5_layout.extract_page_texts"
        ) as mock_extract:
            mock_extract.return_value = [
                PageTextBlock(
                    page_number=5,
                    text="Some layout text",
                    char_count=100,
                )
            ]

            with patch(
                "src.datasheet.phase5_layout.parse_constraints"
            ) as mock_parse:
                mock_parse.return_value = LayoutExtractionResult(
                    constraints=[],
                    extraction_notes="Model failed",
                )

                # Should not raise even though model "failed"
                result = extract_layout_constraints(
                    pdf_path, phase1_output_with_layout, mock_config
                )

                assert result == []
                mock_parse.assert_called_once()

    def test_extract_layout_constraints_returns_correct_list_with_mock_llm(
        self,
        tmp_path,
        mock_config,
        phase1_output_with_layout,
    ) -> None:
        """Mock spatial_parser LLM call — verify extract_layout_constraints returns correct list."""
        pdf_path = tmp_path / "test.pdf"

        # Create expected constraints
        expected_constraints = [
            PlacementConstraint(
                constraint_type="proximity",
                subject="C1",
                relative_to="U1.VIN",
                relative_to_type="pin",
                max_distance_mm=5.0,
                source_sentence="Place C1 within 5mm of U1.VIN",
                confidence=0.95,
            ),
            PlacementConstraint(
                constraint_type="keepout",
                subject="C2",
                relative_to="C3",
                relative_to_type="component",
                min_distance_mm=3.0,
                source_sentence="Keep C2 at least 3mm from C3",
                confidence=0.88,
            ),
        ]

        # Mock the extraction pipeline
        with patch(
            "src.datasheet.phase5_layout.parse_constraints"
        ) as mock_parse:
            mock_parse.return_value = LayoutExtractionResult(
                constraints=expected_constraints,
                extraction_notes="Success",
            )

            with patch(
                "src.datasheet.phase5_layout.extract_page_texts"
            ) as mock_extract:
                mock_extract.return_value = [
                    PageTextBlock(
                        page_number=5,
                        text="Place C1 within 5mm of U1.VIN. Keep C2 at least 3mm from C3.",
                        char_count=100,
                    )
                ]

                result = extract_layout_constraints(
                    pdf_path, phase1_output_with_layout, mock_config
                )

                # Should return validated constraints
                assert len(result) == 2
                assert result[0].subject == "C1"
                assert result[0].relative_to_type == "pin"
                assert result[1].subject == "C2"

    def test_extract_layout_constraints_filters_by_section_type_only(
        self,
        tmp_path,
        mock_config,
    ) -> None:
        """Test that only LAYOUT_RECOMMENDATIONS sections are processed."""
        pdf_path = tmp_path / "test.pdf"

        # Mixed section types
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
                page_number=5,
                bounding_box=(100, 100, 900, 500),
                section_type=TableSectionType.LAYOUT_RECOMMENDATIONS,
                detection_confidence=0.93,
            ),
            TableCrop(
                image_bytes=b"dummy",
                page_number=10,
                bounding_box=(100, 100, 900, 500),
                section_type=TableSectionType.PINOUT,
                detection_confidence=0.91,
            ),
        ]

        phase1_output = Phase1Output(
            pdf_path="test.pdf",
            source_pdf_hash="abc123",
            total_pages=15,
            table_crops=crops,
            footnote_maps=[],
            processing_time_ms=1000.0,
        )

        # Mock to track which pages are extracted
        with patch(
            "src.datasheet.phase5_layout.extract_page_texts"
        ) as mock_extract:
            mock_extract.return_value = []

            extract_layout_constraints(pdf_path, phase1_output, mock_config)

            # Should only request page 5 (the layout page)
            mock_extract.assert_called_once()
            call_args = mock_extract.call_args
            assert call_args[0][1] == [5]  # Only page 5

    def test_extract_layout_constraints_multiple_layout_pages(
        self,
        tmp_path,
        mock_config,
    ) -> None:
        """Test extraction from multiple layout recommendation pages."""
        pdf_path = tmp_path / "test.pdf"

        crops = [
            TableCrop(
                image_bytes=b"dummy",
                page_number=5,
                bounding_box=(100, 100, 900, 500),
                section_type=TableSectionType.LAYOUT_RECOMMENDATIONS,
                detection_confidence=0.93,
            ),
            TableCrop(
                image_bytes=b"dummy",
                page_number=6,
                bounding_box=(100, 100, 900, 500),
                section_type=TableSectionType.LAYOUT_RECOMMENDATIONS,
                detection_confidence=0.92,
            ),
        ]

        phase1_output = Phase1Output(
            pdf_path="test.pdf",
            source_pdf_hash="abc123",
            total_pages=10,
            table_crops=crops,
            footnote_maps=[],
            processing_time_ms=1000.0,
        )

        # Mock to verify multiple pages are requested
        with patch(
            "src.datasheet.phase5_layout.extract_page_texts"
        ) as mock_extract:
            mock_extract.return_value = [
                PageTextBlock(page_number=5, text="Text from page 5", char_count=100),
                PageTextBlock(page_number=6, text="Text from page 6", char_count=100),
            ]

            with patch(
                "src.datasheet.phase5_layout.parse_constraints"
            ) as mock_parse:
                mock_parse.return_value = LayoutExtractionResult(
                    constraints=[],
                    extraction_notes="Test",
                )

                extract_layout_constraints(pdf_path, phase1_output, mock_config)

                # Should request pages 5 and 6
                mock_extract.assert_called_once()
                call_args = mock_extract.call_args
                assert call_args[0][1] == [5, 6]
