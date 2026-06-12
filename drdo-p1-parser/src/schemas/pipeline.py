"""Inter-phase transport schemas for the parsing pipeline."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.datasheet import ComponentDatasheet, ValidationResult

if TYPE_CHECKING:
    from src.phase4_validate.kicad_exporter import KiCadExport


SectionType = Literal[
    "electrical_characteristics",
    "absolute_maximum_ratings",
    "timing",
    "pinout",
    "ordering",
    "other",
]


class FootnoteLink(BaseModel):
    """Mapping of superscript marker to footnote text."""

    marker: str
    text: str
    page_number: int


class BoundingBox(BaseModel):
    """Pixel bounding box in rasterized page coordinates."""

    x1: int
    y1: int
    x2: int
    y2: int


class DetectedTable(BaseModel):
    """A detected and classified table region from Phase 1 DLA."""

    crop_bytes: bytes
    bbox: BoundingBox
    page_number: int
    page_range: tuple[int, int]
    confidence: float
    section_type: SectionType
    heading_text: str | None = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        """Ensure confidence is within [0.0, 1.0]."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"confidence must be [0, 1], got {value}")
        return value


class Phase1Output(BaseModel):
    """Output from Phase 1: Document Layout Analysis."""

    pdf_path: str
    detected_tables: list[DetectedTable] = Field(default_factory=list)
    footnotes: list[FootnoteLink] = Field(default_factory=list)
    footnote_map: dict[str, str] = Field(default_factory=dict)
    tables: list[bytes] = Field(default_factory=list)
    section_type: SectionType = "other"

    @model_validator(mode="after")
    def sync_legacy_fields(self) -> "Phase1Output":
        """Populate legacy tables list and dominant section_type from detections."""
        if self.detected_tables:
            self.tables = [table.crop_bytes for table in self.detected_tables]
            type_counts: dict[str, int] = {}
            for table in self.detected_tables:
                if table.section_type != "other":
                    type_counts[table.section_type] = type_counts.get(table.section_type, 0) + 1
            if type_counts:
                self.section_type = max(type_counts, key=type_counts.get)  # type: ignore[arg-type]
        return self


GridSource = Literal["vector_path_A", "vlm_path_B", "mock_for_testing"]


class GridMatrix(BaseModel):
    """Structured grid of cell text with confidence."""

    rows: list[list[str]]
    num_rows: int = 0
    num_cols: int = 0
    section_type: SectionType = "other"
    page_number: int = 0
    confidence: float
    source: GridSource
    heading_text: str | None = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        """Ensure confidence is within [0.0, 1.0]."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"confidence must be [0, 1], got {value}")
        return value

    @model_validator(mode="before")
    @classmethod
    def compute_dimensions(cls, data: Any) -> Any:
        """Auto-compute row and column counts from grid rows."""
        if isinstance(data, dict) and "rows" in data:
            rows = data["rows"]
            data.setdefault("num_rows", len(rows))
            data.setdefault("num_cols", len(rows[0]) if rows else 0)
        return data


class Phase2Output(BaseModel):
    """Output from Phase 2: Table Structure Recognition."""

    pdf_path: str = ""
    grids: list[GridMatrix] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    num_tables: int = 0

    @model_validator(mode="after")
    def set_num_tables(self) -> "Phase2Output":
        """Set table count from grid list length."""
        self.num_tables = len(self.grids)
        return self


class PipelineOutput(BaseModel):
    """Final deliverable from full pipeline."""

    datasheet: ComponentDatasheet
    validation: ValidationResult
    kicad_export: KiCadExport | None = None

    def to_json_file(self, path: str) -> None:
        """Serialize pipeline output to a JSON file."""
        with open(path, "w", encoding="utf-8") as file_handle:
            json.dump(self.model_dump(), file_handle, indent=2)

    @classmethod
    def from_json_file(cls, path: str) -> "PipelineOutput":
        """Deserialize pipeline output from a JSON file."""
        with open(path, encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        return cls(**data)
