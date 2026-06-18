"""Output contract schemas for extracted datasheet data."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator


class ExtractedValue(BaseModel):
    """Atomic value with full provenance."""

    raw_text: str
    value: float
    unit: str
    confidence: float
    source: Literal["vector_path_A", "vlm_path_B", "manual_review"]
    footnote: Optional[str] = None

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, value: float) -> float:
        """Ensure confidence is within [0.0, 1.0]."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Confidence must be 0–1, got {value}")
        return value


class ElectricalParameter(BaseModel):
    """Electrical characteristic row from a datasheet table."""

    name: str
    parameter_type: str
    min_value: Optional[ExtractedValue] = None
    typ_value: Optional[ExtractedValue] = None
    max_value: Optional[ExtractedValue] = None
    conditions: Optional[str] = None
    test_condition: Optional[str] = None

    def avg_confidence(self) -> float:
        """Average confidence across min/typ/max values."""
        values = [v for v in [self.min_value, self.typ_value, self.max_value] if v]
        if not values:
            return 0.0
        return sum(v.confidence for v in values) / len(values)


class AbsoluteMaxRating(BaseModel):
    """Absolute maximum rating entry."""

    name: str
    max_value: ExtractedValue
    unit: str
    conditions: Optional[str] = None
    note: Optional[str] = None


class PinDefinition(BaseModel):
    """Pinout table entry."""

    pin_number: str
    pin_name: str
    pin_type: Literal[
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
    ]
    alternate_functions: list[str] = []
    description: Optional[str] = None
    bank: Optional[str] = None


class DatasheetSection(BaseModel):
    """Logical section container within a datasheet."""

    section_type: Literal[
        "electrical_characteristics",
        "absolute_maximum_ratings",
        "pinout",
        "timing",
        "ordering",
        "other",
    ]
    section_heading: Optional[str] = None
    page_range: tuple[int, int]
    table_confidence: float
    parameters: list[ElectricalParameter] = []
    abs_max_ratings: list[AbsoluteMaxRating] = []
    pins: list[PinDefinition] = []


class ValidationError(BaseModel):
    """Structured validation issue from Phase 4 rule engine."""

    level: Literal["CRITICAL", "WARNING"]
    param_name: str
    message: str
    remediation: Optional[str] = None


class ValidationResult(BaseModel):
    """Phase 4 validation verdict."""

    component_id: str
    passed: bool
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []
    review_required: bool = False
    confidence_score: float = 0.0
    timestamp: str


class ComponentDatasheet(BaseModel):
    """Top-level extracted datasheet document."""

    component_id: str
    manufacturer: str
    package: Optional[str] = None
    datasheet_version: Optional[str] = None
    extraction_timestamp: str
    sections: list[DatasheetSection] = []
    validation: Optional[ValidationResult] = None

    @property
    def all_parameters(self) -> list[ElectricalParameter]:
        """All electrical parameters across sections."""
        return [param for section in self.sections for param in section.parameters]

    @property
    def all_pins(self) -> list[PinDefinition]:
        """All pin definitions across sections."""
        return [pin for section in self.sections for pin in section.pins]

    @property
    def all_abs_max(self) -> list[AbsoluteMaxRating]:
        """All absolute maximum ratings across sections."""
        return [rating for section in self.sections for rating in section.abs_max_ratings]

    @model_validator(mode="after")
    def at_least_one_section(self) -> "ComponentDatasheet":
        """Require at least one section in the document."""
        if not self.sections:
            raise ValueError("ComponentDatasheet must have at least one section")
        return self
