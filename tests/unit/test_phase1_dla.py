"""Unit tests for src/datasheet/phase1_dla/.

Tests the Phase 1 Document Layout Analysis pipeline including:
- YOLO model detection (mocked)
- Section classification
- Footnote linking
- Table cropping
- Multipage detection
"""

from __future__ import annotations

import hashlib
import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.config import Config
from src.datasheet.phase1_dla import process
from src.datasheet.phase1_dla._schemas import FootnoteMap, Phase1Output, TableCrop
from src.datasheet.phase1_dla.detector import (
    CLASS_CAPTION,
    CLASS_FOOTNOTE,
    CLASS_TABLE,
    _crop_region,
    _detect_tables,
)
from src.datasheet.phase1_dla.footnote_linker import (
    _find_footnote_markers,
    _link_page_footnotes,
    find_marker_in_cell,
    link_footnotes,
)
from src.datasheet.phase1_dla.multipage_merger import (
    _calculate_vertical_distance,
    _headers_similar,
    _is_continuation,
    detect_multipage_tables,
)
from src.datasheet.phase1_dla.rasterizer import (
    _rasterize_all_pages,
    _rasterize_page,
)
from src.datasheet.phase1_dla.section_classifier import (
    _classify_by_position,
    _classify_heading,
    classify_section,
)
from src.schemas.datasheet import TableSectionType


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_config(tmp_path) -> Config:
    """Create a mock Config with temporary model paths."""
    config = MagicMock(spec=Config)
    model_path = tmp_path / "models" / "yolov8_doclaynets.pt"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    # Create a dummy file for the model path
    model_path.write_bytes(b"dummy model weights")

    def get_model_path(name: str) -> Path:
        return model_path

    config.get_model_path = get_model_path
    return config


@pytest.fixture
def sample_pil_image() -> Image.Image:
    """Create a sample PIL Image for testing."""
    return Image.new("RGB", (800, 600), color="white")


@pytest.fixture
def mock_yolo_detections() -> list[dict]:
    """Create mock YOLO detection output."""
    return [
        {
            "bounding_box": (100, 100, 700, 400),
            "confidence": 0.95,
            "class_id": CLASS_TABLE,
        },
        {
            "bounding_box": (100, 50, 400, 90),
            "confidence": 0.88,
            "class_id": CLASS_CAPTION,
        },
    ]


# =============================================================================
# Phase1Output Schema Tests
# =============================================================================


class TestPhase1OutputSchema:
    """Tests for Phase 1 internal schemas."""

    def test_table_crop_creation(self) -> None:
        """Test TableCrop model creation."""
        crop = TableCrop(
            page_number=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"fake png data",
            bounding_box=(100, 100, 700, 400),
            heading_text="ELECTRICAL CHARACTERISTICS",
            is_multipage_continuation=False,
            detection_confidence=0.95,
        )
        assert crop.page_number == 1
        assert crop.section_type == TableSectionType.ELECTRICAL_CHARACTERISTICS
        assert crop.bounding_box == (100, 100, 700, 400)
        assert crop.detection_confidence == 0.95

    def test_table_crop_confidence_bounds(self) -> None:
        """Test TableCrop detection_confidence bounds."""
        import pydantic

        # Valid bounds
        TableCrop(
            page_number=1,
            section_type=TableSectionType.OTHER,
            image_bytes=b"test",
            bounding_box=(0, 0, 100, 100),
            detection_confidence=0.0,
        )
        TableCrop(
            page_number=1,
            section_type=TableSectionType.OTHER,
            image_bytes=b"test",
            bounding_box=(0, 0, 100, 100),
            detection_confidence=1.0,
        )

        # Invalid: negative
        with pytest.raises(Exception):
            TableCrop(
                page_number=1,
                section_type=TableSectionType.OTHER,
                image_bytes=b"test",
                bounding_box=(0, 0, 100, 100),
                detection_confidence=-0.1,
            )

    def test_footnote_map_creation(self) -> None:
        """Test FootnoteMap model creation."""
        fm = FootnoteMap(
            page_number=1,
            entries={
                "1": "Valid for T_A = 25°C",
                "2": "Guaranteed by design",
            },
        )
        assert fm.page_number == 1
        assert len(fm.entries) == 2
        assert fm.entries["1"] == "Valid for T_A = 25°C"

    def test_phase1_output_creation(self) -> None:
        """Test Phase1Output model creation."""
        output = Phase1Output(
            pdf_path="/path/to/datasheet.pdf",
            source_pdf_hash="a1b2c3d4",
            total_pages=5,
            table_crops=[],
            footnote_maps=[],
            processing_time_ms=1500.0,
        )
        assert output.pdf_path == "/path/to/datasheet.pdf"
        assert output.total_pages == 5
        assert output.processing_time_ms == 1500.0


# =============================================================================
# Rasterizer Tests
# =============================================================================


class TestRasterizer:
    """Tests for PDF rasterization (with mocked pdf2image)."""

    @patch("src.datasheet.phase1_dla.rasterizer.convert_from_path")
    def test_rasterize_all_pages(self, mock_convert, sample_pil_image) -> None:
        """Test rasterizing all pages returns correct page numbers."""
        mock_convert.return_value = [sample_pil_image, sample_pil_image]

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            pdf_path = Path(tmp.name)

        try:
            pages = _rasterize_all_pages(pdf_path)
            assert len(pages) == 2
            assert pages[0][0] == 1  # Page 1
            assert pages[1][0] == 2  # Page 2
        finally:
            pdf_path.unlink()

    @patch("src.datasheet.phase1_dla.rasterizer.convert_from_path")
    def test_rasterize_page_single(self, mock_convert, sample_pil_image) -> None:
        """Test rasterizing a single page."""
        mock_convert.return_value = [sample_pil_image]

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            pdf_path = Path(tmp.name)

        try:
            image = _rasterize_page(pdf_path, page_number=2)
            assert image is sample_pil_image
            # Verify first_page and last_page were set correctly
            call_kwargs = mock_convert.call_args[1]
            assert call_kwargs["first_page"] == 2
            assert call_kwargs["last_page"] == 2
        finally:
            pdf_path.unlink()

    def test_rasterize_file_not_found(self) -> None:
        """Test rasterizer raises FileNotFoundError for missing PDF."""
        with pytest.raises(FileNotFoundError):
            _rasterize_all_pages(Path("/nonexistent/path.pdf"))


# =============================================================================
# Detector Tests (Mocked YOLO)
# =============================================================================


class TestDetector:
    """Tests for YOLO detection (with mocked model)."""

    def test_crop_region(self, sample_pil_image) -> None:
        """Test cropping a region from an image."""
        bbox = (100, 100, 300, 300)
        cropped_bytes = _crop_region(sample_pil_image, bbox)

        # Verify it's valid PNG bytes
        assert len(cropped_bytes) > 0
        # Should be able to reload as image
        reloaded = Image.open(io.BytesIO(cropped_bytes))
        assert reloaded.size == (200, 200)

    @patch("src.datasheet.phase1_dla.detector.YOLO")
    def test_load_yolo_model_raises_if_missing(self, mock_yolo_class, mock_config) -> None:
        """Test that detector raises FileNotFoundError if YOLO model missing."""
        from src.datasheet.phase1_dla.detector import _load_yolo_model

        # Make model path not exist
        model_path = mock_config.get_model_path("yolov8n_doclaynet")
        model_path.unlink()  # Delete the dummy file

        with pytest.raises(FileNotFoundError) as exc_info:
            _load_yolo_model(mock_config)

        assert "YOLOv8 model not found" in str(exc_info.value)
        assert str(model_path) in str(exc_info.value)


# =============================================================================
# Section Classifier Tests
# =============================================================================


class TestSectionClassifier:
    """Tests for section type classification."""

    def test_classify_electrical_characteristics_heading(self) -> None:
        """Test section_classifier classifies 'ELECTRICAL CHARACTERISTICS' heading → ELECTRICAL_CHARACTERISTICS."""
        result = classify_section("ELECTRICAL CHARACTERISTICS")
        assert result == TableSectionType.ELECTRICAL_CHARACTERISTICS

    def test_classify_electrical_characteristics_variant(self) -> None:
        """Test classification with heading variants."""
        variants = [
            "Electrical Characteristics",
            "ELECTRICAL SPECIFICATIONS",
            "DC Characteristics",
            "Recommended Operating Conditions",
        ]
        for heading in variants:
            result = classify_section(heading)
            assert result == TableSectionType.ELECTRICAL_CHARACTERISTICS, f"Failed for: {heading}"

    def test_classify_absolute_maximum_ratings(self) -> None:
        """Test classification of absolute maximum ratings headings."""
        variants = [
            "ABSOLUTE MAXIMUM RATINGS",
            "Absolute Max Ratings",
            "Maximum Ratings",
            "Stress Ratings",
        ]
        for heading in variants:
            result = classify_section(heading)
            assert result == TableSectionType.ABSOLUTE_MAXIMUM_RATINGS, f"Failed for: {heading}"

    def test_classify_layout_recommendations_heading(self) -> None:
        """Test section_classifier classifies 'PCB Layout Recommendations' heading → LAYOUT_RECOMMENDATIONS."""
        result = classify_section("PCB Layout Recommendations")
        assert result == TableSectionType.LAYOUT_RECOMMENDATIONS

    def test_classify_layout_recommendations_variants(self) -> None:
        """Test classification of layout recommendations heading variants."""
        variants = [
            "Layout Recommendations",
            "PCB Layout",
            "Layout Guidelines",
            "Layout Example",
            "Recommended Layout",
            "Application Layout",
        ]
        for heading in variants:
            result = classify_section(heading)
            assert result == TableSectionType.LAYOUT_RECOMMENDATIONS, f"Failed for: {heading}"

    def test_classify_pinout(self) -> None:
        """Test classification of pinout section headings."""
        variants = [
            "Pin Configuration",
            "Pin Assignments",
            "Pin Functions",
            "Pin Description",
            "Terminal Functions",
        ]
        for heading in variants:
            result = classify_section(heading)
            assert result == TableSectionType.PINOUT, f"Failed for: {heading}"

    def test_classify_timing(self) -> None:
        """Test classification of timing section headings."""
        variants = [
            "Timing Requirements",
            "Switching Characteristics",
            "Timing Diagram",
        ]
        for heading in variants:
            result = classify_section(heading)
            assert result == TableSectionType.TIMING, f"Failed for: {heading}"

    def test_classify_ordering(self) -> None:
        """Test classification of ordering section headings."""
        variants = [
            "Ordering Information",
            "Order Information",
            "Package Options",
        ]
        for heading in variants:
            result = classify_section(heading)
            assert result == TableSectionType.ORDERING, f"Failed for: {heading}"

    def test_classify_unknown_heading_defaults_other(self) -> None:
        """Test unknown headings default to OTHER."""
        result = classify_section("Some Random Heading")
        assert result == TableSectionType.OTHER

    def test_classify_none_heading_defaults_other(self) -> None:
        """Test None heading defaults to OTHER."""
        result = classify_section(None)
        assert result == TableSectionType.OTHER

    def test_classify_all_7_section_types(self) -> None:
        """Test that all 7 TableSectionType values can be classified."""
        # Test the 6 recognizable section types directly
        test_cases = [
            ("ELECTRICAL CHARACTERISTICS", TableSectionType.ELECTRICAL_CHARACTERISTICS),
            ("ABSOLUTE MAXIMUM RATINGS", TableSectionType.ABSOLUTE_MAXIMUM_RATINGS),
            ("Pin Configuration", TableSectionType.PINOUT),
            ("Timing Requirements", TableSectionType.TIMING),
            ("Ordering Information", TableSectionType.ORDERING),
            ("Layout Recommendations", TableSectionType.LAYOUT_RECOMMENDATIONS),
        ]
        for heading, expected in test_cases:
            result = classify_section(heading)
            assert result == expected, f"Expected {expected.value} for '{heading}'"

        # Unknown section should default to OTHER (not position fallback)
        result = classify_section("Unknown Section", fallback_to_position=False)
        assert result == TableSectionType.OTHER

    def test_classify_heading_internal_function(self) -> None:
        """Test internal _classify_heading function."""
        result = _classify_heading("Electrical Characteristics")
        assert result == TableSectionType.ELECTRICAL_CHARACTERISTICS

    def test_classify_heading_returns_other_for_no_match(self) -> None:
        """Test _classify_heading returns OTHER for no match."""
        result = _classify_heading("Completely Unknown")
        assert result == TableSectionType.OTHER

    def test_classify_by_position_early_page(self) -> None:
        """Test positional classification for early page tables."""
        result = _classify_by_position(page_number=1, table_index=0)
        # Early pages, first table should be abs-max or pinout
        assert result in (TableSectionType.ABSOLUTE_MAXIMUM_RATINGS, TableSectionType.PINOUT)

    def test_classify_by_position_later_table(self) -> None:
        """Test positional classification for later tables."""
        result = _classify_by_position(page_number=3, table_index=1)
        # Later tables should be electrical characteristics
        assert result == TableSectionType.ELECTRICAL_CHARACTERISTICS

    def test_classify_with_fallback_enabled(self) -> None:
        """Test classification with position fallback enabled for missing heading."""
        # When fallback_to_position=True and heading is None/empty,
        # positional heuristics should be used
        result = classify_section(
            heading_text=None,
            page_number=1,
            table_index=0,
            fallback_to_position=True,
        )
        # Early page, first table should be abs-max per position heuristic
        assert result == TableSectionType.ABSOLUTE_MAXIMUM_RATINGS

    def test_classify_with_fallback_disabled(self) -> None:
        """Test classification with position fallback disabled (default)."""
        result = classify_section(
            heading_text=None,
            page_number=1,
            table_index=0,
            fallback_to_position=False,
        )
        # Should return OTHER, not use position
        assert result == TableSectionType.OTHER


# =============================================================================
# Footnote Linker Tests
# =============================================================================


class TestFootnoteLinker:
    """Tests for footnote linking functionality."""

    def test_find_footnote_markers_numbered(self) -> None:
        """Test finding numbered footnote markers."""
        text = "Parameter (1) value is 3.3V. Note (2) refers to temperature."
        markers = _find_footnote_markers(text)

        assert len(markers) == 2
        assert markers[0][0] == "1"
        assert markers[1][0] == "2"

    def test_find_footnote_markers_symbols(self) -> None:
        """Test finding symbol footnote markers."""
        text = "Value is 5V*. See note † for details."
        markers = _find_footnote_markers(text)

        # Should find * and †
        marker_values = [m[0] for m in markers]
        assert "*" in marker_values
        assert "†" in marker_values

    def test_find_footnote_markers_letters(self) -> None:
        """Test finding letter footnote markers."""
        text = "Parameter (a) and (b) are related."
        markers = _find_footnote_markers(text)

        assert len(markers) == 2
        assert markers[0][0] == "a"
        assert markers[1][0] == "b"

    def test_link_page_footnotes(self) -> None:
        """Test linking footnotes on a single page."""
        text = """
        Electrical Characteristics (1)
        VCC 3.3V (2)

        Notes:
        (1) Valid for T_A = 25°C
        (2) Guaranteed by design
        """
        footnote_map = _link_page_footnotes(text, page_number=1)

        assert footnote_map.page_number == 1
        assert "1" in footnote_map.entries
        assert "2" in footnote_map.entries
        assert "T_A = 25°C" in footnote_map.entries["1"]
        assert "Guaranteed by design" in footnote_map.entries["2"]

    def test_footnote_linker_links_marker_to_correct_text(self) -> None:
        """Test footnote_linker links '(1)' marker to the correct footnote text."""
        page_texts = {
            1: """
            Parameter Value (1)
            (1) This footnote applies to parameter values above.
            """,
        }
        footnote_maps = link_footnotes(page_texts)

        assert len(footnote_maps) == 1
        assert footnote_maps[0].page_number == 1
        assert "1" in footnote_maps[0].entries
        assert "applies to parameter values" in footnote_maps[0].entries["1"]

    def test_find_marker_in_cell_found(self) -> None:
        """Test finding footnote marker in table cell."""
        footnote_maps = [
            FootnoteMap(
                page_number=1,
                entries={"1": "Valid for 25°C"},
            )
        ]
        result = find_marker_in_cell("3.3V (1)", footnote_maps, page_number=1)
        assert result == "Valid for 25°C"

    def test_find_marker_in_cell_not_found(self) -> None:
        """Test finding footnote marker when not present."""
        footnote_maps = [
            FootnoteMap(
                page_number=1,
                entries={"1": "Valid for 25°C"},
            )
        ]
        result = find_marker_in_cell("3.3V", footnote_maps, page_number=1)
        assert result is None

    def test_find_marker_wrong_page(self) -> None:
        """Test finding footnote marker on wrong page."""
        footnote_maps = [
            FootnoteMap(
                page_number=1,
                entries={"1": "Valid for 25°C"},
            )
        ]
        result = find_marker_in_cell("3.3V (1)", footnote_maps, page_number=2)
        assert result is None

    def test_link_footnotes_multiple_pages(self) -> None:
        """Test linking footnotes across multiple pages."""
        page_texts = {
            1: "(1) Note on page 1",
            2: "(2) Note on page 2",
        }
        footnote_maps = link_footnotes(page_texts)

        assert len(footnote_maps) == 2
        page_numbers = [fm.page_number for fm in footnote_maps]
        assert 1 in page_numbers
        assert 2 in page_numbers

    def test_link_footnotes_empty_input(self) -> None:
        """Test linking footnotes with empty input."""
        footnote_maps = link_footnotes({})
        assert footnote_maps == []


# =============================================================================
# Multipage Merger Tests
# =============================================================================


class TestMultipageMerger:
    """Tests for multipage table detection."""

    def test_calculate_vertical_distance(self) -> None:
        """Test vertical distance calculation between tables."""
        table1 = TableCrop(
            page_number=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 400, 700, 580),  # Near bottom (page height 600)
            detection_confidence=0.9,
        )
        table2 = TableCrop(
            page_number=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 20, 700, 200),  # Near top
            detection_confidence=0.9,
        )

        distance = _calculate_vertical_distance(table1, table2, page_height=600)
        assert distance > 0  # Should be positive
        assert distance < 1.0  # Should be normalized

    def test_headers_similar_same_heading(self) -> None:
        """Test header similarity with same heading text."""
        table1 = TableCrop(
            page_number=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 100, 700, 400),
            heading_text="ELECTRICAL CHARACTERISTICS",
            detection_confidence=0.9,
        )
        table2 = TableCrop(
            page_number=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 20, 700, 320),
            heading_text="ELECTRICAL CHARACTERISTICS",
            detection_confidence=0.9,
        )

        similar = _headers_similar(table1, table2)
        assert similar is True

    def test_headers_similar_spatial_alignment(self) -> None:
        """Test header similarity with spatial alignment."""
        # Same bounding box positions = aligned
        table1 = TableCrop(
            page_number=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 100, 700, 400),
            detection_confidence=0.9,
        )
        table2 = TableCrop(
            page_number=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 20, 700, 320),  # Same width, aligned
            detection_confidence=0.9,
        )

        similar = _headers_similar(table1, table2)
        assert similar is True

    def test_is_continuation_same_section(self) -> None:
        """Test continuation detection with same section type."""
        table1 = TableCrop(
            page_number=1,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 450, 700, 580),  # Near bottom
            heading_text="ELECTRICAL CHARACTERISTICS",
            detection_confidence=0.9,
        )
        table2 = TableCrop(
            page_number=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 20, 700, 200),  # Near top
            heading_text="ELECTRICAL CHARACTERISTICS",
            detection_confidence=0.9,
        )

        is_cont = _is_continuation(table1, table2, page_height=600)
        assert is_cont is True

    def test_is_continuation_different_section(self) -> None:
        """Test continuation detection with different section types."""
        table1 = TableCrop(
            page_number=1,
            section_type=TableSectionType.ABSOLUTE_MAXIMUM_RATINGS,
            image_bytes=b"test",
            bounding_box=(100, 450, 700, 580),
            detection_confidence=0.9,
        )
        table2 = TableCrop(
            page_number=2,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            image_bytes=b"test",
            bounding_box=(100, 20, 700, 200),
            detection_confidence=0.9,
        )

        is_cont = _is_continuation(table1, table2, page_height=600)
        assert is_cont is False

    def test_detect_multipage_tables(self) -> None:
        """Test multipage table detection."""
        tables = [
            TableCrop(
                page_number=1,
                section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
                image_bytes=b"test1",
                bounding_box=(100, 450, 700, 580),  # Near bottom
                heading_text="ELECTRICAL CHARACTERISTICS",
                detection_confidence=0.9,
            ),
            TableCrop(
                page_number=2,
                section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
                image_bytes=b"test2",
                bounding_box=(100, 20, 700, 200),  # Near top
                heading_text="ELECTRICAL CHARACTERISTICS",
                detection_confidence=0.9,
            ),
        ]

        result = detect_multipage_tables(tables, page_height=600)

        assert len(result) == 2
        assert result[0].is_multipage_continuation is False  # First table
        assert result[1].is_multipage_continuation is True  # Continuation

    def test_detect_multipage_no_continuations(self) -> None:
        """Test multipage detection with no continuations."""
        tables = [
            TableCrop(
                page_number=1,
                section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
                image_bytes=b"test1",
                bounding_box=(100, 100, 700, 300),
                detection_confidence=0.9,
            ),
            TableCrop(
                page_number=2,
                section_type=TableSectionType.TIMING,
                image_bytes=b"test2",
                bounding_box=(100, 100, 700, 300),
                detection_confidence=0.9,
            ),
        ]

        result = detect_multipage_tables(tables, page_height=600)

        assert all(not t.is_multipage_continuation for t in result)


# =============================================================================
# Integration Tests
# =============================================================================


class TestProcessIntegration:
    """Integration tests for the process() function with mocked dependencies."""

    @patch("src.datasheet.phase1_dla._load_yolo_model")
    @patch("src.datasheet.phase1_dla.rasterizer.convert_from_path")
    @patch("src.datasheet.phase1_dla.compute_pdf_sha256")
    def test_process_returns_phase1_output(
        self,
        mock_hash,
        mock_convert,
        mock_load_model,
        mock_config,
        sample_pil_image,
    ) -> None:
        """Test that process() returns a Phase1Output."""
        # Setup mocks
        mock_hash.return_value = "a1b2c3d4e5f67890"
        mock_convert.return_value = [sample_pil_image, sample_pil_image]

        # Mock YOLO model and detection results using numpy arrays
        import numpy as np

        mock_model = MagicMock()
        mock_result = MagicMock()

        # Create a mock box that mimics YOLO output (numpy array-like)
        class MockBox:
            def __init__(self):
                self.cls = np.array([3])  # CLASS_TABLE
                self.conf = np.array([0.95])
                self.xyxy = np.array([[100.0, 100.0, 700.0, 400.0]])

        mock_box = MockBox()
        mock_result.boxes = MagicMock()
        mock_result.boxes.cpu.return_value.numpy.return_value = [mock_box]
        mock_model.return_value = [mock_result]
        mock_load_model.return_value = mock_model

        # Create a temporary PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            pdf_path = Path(tmp.name)

        try:
            result = process(pdf_path, mock_config)

            assert isinstance(result, Phase1Output)
            assert result.pdf_path == str(pdf_path)
            assert result.source_pdf_hash == "a1b2c3d4e5f67890"
            assert result.total_pages == 2
            assert result.processing_time_ms > 0

        finally:
            pdf_path.unlink()

    @patch("src.datasheet.phase1_dla.rasterizer.convert_from_path")
    @patch("src.datasheet.phase1_dla.compute_pdf_sha256")
    def test_process_raises_file_not_found_for_missing_pdf(
        self,
        mock_hash,
        mock_convert,
        mock_config,
    ) -> None:
        """Test that process() raises FileNotFoundError for missing PDF."""
        with pytest.raises(FileNotFoundError):
            process(Path("/nonexistent/path.pdf"), mock_config)

    @patch("src.datasheet.phase1_dla._load_yolo_model")
    @patch("src.datasheet.phase1_dla.rasterizer.convert_from_path")
    @patch("src.datasheet.phase1_dla.compute_pdf_sha256")
    def test_process_raises_file_not_found_for_missing_model(
        self,
        mock_hash,
        mock_convert,
        mock_load_model,
        mock_config,
        sample_pil_image,
    ) -> None:
        """Test that process() raises clear FileNotFoundError if YOLO model missing."""
        mock_hash.return_value = "test_hash"
        mock_convert.return_value = [sample_pil_image]

        # Make model loading raise FileNotFoundError
        model_path = mock_config.get_model_path("yolov8n_doclaynet")
        mock_load_model.side_effect = FileNotFoundError(
            f"YOLOv8 model not found at: {model_path}"
        )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            pdf_path = Path(tmp.name)

        try:
            with pytest.raises(FileNotFoundError) as exc_info:
                process(pdf_path, mock_config)

            assert "YOLOv8 model not found" in str(exc_info.value)
            assert str(model_path) in str(exc_info.value)

        finally:
            pdf_path.unlink()
