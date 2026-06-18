"""Test Pydantic schemas."""

import pytest

from src.schemas import (
    AbsoluteMaxRating,
    BoundingBox,
    ComponentDatasheet,
    DatasheetSection,
    DetectedTable,
    ElectricalParameter,
    ExtractedValue,
    GridMatrix,
    Phase1Output,
    Phase2Output,
    PinDefinition,
    ValidationError,
    ValidationResult,
)


class TestExtractedValue:
    """Test ExtractedValue schema validation."""

    def test_create_valid_value(self) -> None:
        """Create a valid ExtractedValue."""
        val = ExtractedValue(
            raw_text="3.3V",
            value=3.3,
            unit="V",
            confidence=0.95,
            source="vlm_path_B",
        )
        assert val.value == 3.3
        assert val.confidence == 0.95

    def test_confidence_out_of_range_fails(self) -> None:
        """Confidence must be [0.0, 1.0]."""
        with pytest.raises(ValueError, match="Confidence must be"):
            ExtractedValue(
                raw_text="3.3V",
                value=3.3,
                unit="V",
                confidence=1.5,
                source="vlm_path_B",
            )


class TestAbsoluteMaxRating:
    """Test AbsoluteMaxRating schema."""

    def test_create_valid_rating(self) -> None:
        """Create a valid absolute maximum rating."""
        rating = AbsoluteMaxRating(
            name="V_CC_ABS",
            max_value=ExtractedValue(
                raw_text="6",
                value=6.0,
                unit="V",
                confidence=0.98,
                source="vector_path_A",
            ),
            unit="V",
            note="Stresses beyond these ratings may cause permanent damage.",
        )
        assert rating.name == "V_CC_ABS"
        assert rating.max_value.value == 6.0


class TestPinDefinition:
    """Test PinDefinition pin_type literals."""

    @pytest.mark.parametrize(
        "pin_type",
        [
            "power",
            "ground",
            "digital_input",
            "digital_output",
            "digital_io",
            "analog_input",
            "analog_output",
            "clock",
            "reset",
            "no_connect",
            "other",
        ],
    )
    def test_all_pin_types_accepted(self, pin_type: str) -> None:
        """All 12 pin_type literals are valid."""
        pin = PinDefinition(
            pin_number="1",
            pin_name="TEST",
            pin_type=pin_type,
        )
        assert pin.pin_type == pin_type


class TestDatasheetSection:
    """Test DatasheetSection defaults and literals."""

    def test_empty_lists_default(self) -> None:
        """Optional lists default to empty."""
        section = DatasheetSection(
            section_type="electrical_characteristics",
            page_range=(1, 1),
            table_confidence=0.95,
        )
        assert section.parameters == []
        assert section.abs_max_ratings == []
        assert section.pins == []

    def test_ordering_section_type(self) -> None:
        """Ordering is a valid section type."""
        section = DatasheetSection(
            section_type="ordering",
            page_range=(10, 10),
            table_confidence=0.90,
        )
        assert section.section_type == "ordering"


class TestComponentDatasheet:
    """Test ComponentDatasheet validators and accessors."""

    def test_at_least_one_section_required(self) -> None:
        """Empty sections list raises validation error."""
        with pytest.raises(ValueError, match="at least one section"):
            ComponentDatasheet(
                component_id="TEST",
                manufacturer="Texas Instruments",
                extraction_timestamp="2025-07-15T10:00:00Z",
                sections=[],
            )

    def test_convenience_properties(self) -> None:
        """Convenience accessors aggregate section data."""
        value = ExtractedValue(
            raw_text="3.3",
            value=3.3,
            unit="V",
            confidence=0.95,
            source="vector_path_A",
        )
        datasheet = ComponentDatasheet(
            component_id="TEST",
            manufacturer="Texas Instruments",
            extraction_timestamp="2025-07-15T10:00:00Z",
            sections=[
                DatasheetSection(
                    section_type="electrical_characteristics",
                    page_range=(5, 5),
                    table_confidence=0.94,
                    parameters=[
                        ElectricalParameter(
                            name="V_CC",
                            parameter_type="voltage",
                            max_value=value,
                        )
                    ],
                ),
                DatasheetSection(
                    section_type="pinout",
                    page_range=(3, 3),
                    table_confidence=0.99,
                    pins=[
                        PinDefinition(
                            pin_number="1",
                            pin_name="V_CC",
                            pin_type="power",
                        )
                    ],
                ),
            ],
        )
        assert len(datasheet.all_parameters) == 1
        assert len(datasheet.all_pins) == 1


class TestGridMatrix:
    """Test GridMatrix dimension computation and confidence bounds."""

    def test_dimensions_auto_computed(self) -> None:
        """Row and column counts are derived from rows."""
        grid = GridMatrix(
            rows=[["A", "B"], ["C", "D"]],
            section_type="electrical_characteristics",
            page_number=5,
            confidence=0.91,
            source="vector_path_A",
        )
        assert grid.num_rows == 2
        assert grid.num_cols == 2
        assert grid.section_type == "electrical_characteristics"
        assert grid.page_number == 5

    def test_mock_source_allowed(self) -> None:
        """Mock source literal is valid for test fixtures."""
        grid = GridMatrix(
            rows=[["A"]],
            confidence=0.9,
            source="mock_for_testing",
        )
        assert grid.source == "mock_for_testing"

    def test_confidence_out_of_range_fails(self) -> None:
        """Confidence must be [0.0, 1.0]."""
        with pytest.raises(ValueError, match="confidence must be"):
            GridMatrix(
                rows=[["A"]],
                confidence=2.0,
                source="vlm_path_B",
            )


class TestValidationResult:
    """Test ValidationResult states."""

    def test_passed_state(self) -> None:
        """Valid passed validation result."""
        result = ValidationResult(
            component_id="TEST",
            passed=True,
            errors=[],
            warnings=[],
            review_required=False,
            confidence_score=0.95,
            timestamp="2026-06-12T00:00:00Z",
        )
        assert result.passed is True

    def test_failed_state_with_errors(self) -> None:
        """Failed validation with critical errors."""
        result = ValidationResult(
            component_id="TEST",
            passed=False,
            errors=[
                ValidationError(
                    level="CRITICAL",
                    param_name="V_CC",
                    message="min (5.0) > typ (3.3)",
                )
            ],
            warnings=[],
            review_required=True,
            confidence_score=0.50,
            timestamp="2026-06-12T00:00:00Z",
        )
        assert result.passed is False
        assert len(result.errors) == 1


class TestDetectedTable:
    """Test DetectedTable and Phase1Output schemas."""

    def test_detected_table_valid(self) -> None:
        """Create a valid DetectedTable."""
        table = DetectedTable(
            crop_bytes=b"\x89PNG\r\n\x1a\n",
            bbox=BoundingBox(x1=0, y1=0, x2=100, y2=100),
            page_number=5,
            page_range=(5, 5),
            confidence=0.95,
            section_type="electrical_characteristics",
            heading_text="6.5 Electrical Characteristics",
        )
        assert table.page_range == (5, 5)

    def test_phase1_output_syncs_legacy_tables(self) -> None:
        """Phase1Output populates legacy tables list from detected_tables."""
        table = DetectedTable(
            crop_bytes=b"\x89PNG\r\n\x1a\n",
            bbox=BoundingBox(x1=0, y1=0, x2=100, y2=100),
            page_number=4,
            page_range=(4, 4),
            confidence=0.9,
            section_type="absolute_maximum_ratings",
        )
        output = Phase1Output(
            pdf_path="test.pdf",
            detected_tables=[table],
        )
        assert len(output.tables) == 1
        assert output.section_type == "absolute_maximum_ratings"


class TestPhase2Output:
    """Test Phase2Output schema."""

    def test_phase2_output_metadata(self) -> None:
        """Phase2Output stores pdf_path, grids, and metadata."""
        grid = GridMatrix(
            rows=[["A", "B"]],
            section_type="pinout",
            page_number=3,
            confidence=0.95,
            source="vector_path_A",
        )
        output = Phase2Output(
            pdf_path="corpus/golden/TI_TLV7021_v1.pdf",
            grids=[grid],
            metadata={"path_a_wins": 1, "path_b_wins": 0},
        )
        assert output.num_tables == 1
        assert output.metadata["path_a_wins"] == 1


class TestElectricalParameter:
    """Test ElectricalParameter schema."""

    def test_avg_confidence_with_all_values(self) -> None:
        """Average confidence across min/typ/max."""
        param = ElectricalParameter(
            name="V_CC",
            parameter_type="voltage",
            min_value=ExtractedValue(
                raw_text="1.5V",
                value=1.5,
                unit="V",
                confidence=0.90,
                source="vector_path_A",
            ),
            typ_value=ExtractedValue(
                raw_text="3.3V",
                value=3.3,
                unit="V",
                confidence=0.95,
                source="vector_path_A",
            ),
            max_value=ExtractedValue(
                raw_text="5.5V",
                value=5.5,
                unit="V",
                confidence=0.92,
                source="vector_path_A",
            ),
        )
        assert param.avg_confidence() == pytest.approx(0.9233, rel=1e-3)
