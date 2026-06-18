"""Intent and BOM schemas — Team C owns writes, Team D owns reads.

This module defines the schemas for design intent capture and Bill of Materials (BOM)
generation. It bridges the gap between natural language design goals and structured
component selections.

The IntentDict captures the user's design requirements including frequency specifications,
application context, and any ambiguities that require clarification.

The ValidatedBOM represents the output of the component selection process, where each
BOMEntry may have a specific part number (resolved) or None (requiring human selection).

Version History:
- Initial schema for intent-to-BOM pipeline
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class FrequencySpec(BaseModel):
    """Frequency specification with value and unit.

    Used in IntentDict to specify operating frequencies for RF, power,
    and mixed-signal designs.

    Attributes:
        value: Numeric frequency value
        unit: Frequency unit (Hz, kHz, MHz, GHz)
    """

    value: float = Field(gt=0.0, description="Numeric frequency value")
    unit: Literal["Hz", "kHz", "MHz", "GHz"] = Field(description="Frequency unit")


class AmbiguityFlag(BaseModel):
    """Flag indicating ambiguity in design intent requiring resolution.

    Captures fields where the intent parser detected uncertainty or
    multiple valid interpretations. Severity indicates whether the
    ambiguity blocks progress (CRITICAL) or is advisory (WARNING).

    Attributes:
        field: The intent field with ambiguity
        description: Human-readable explanation of the ambiguity
        severity: Impact level (CRITICAL blocks progress, WARNING is advisory)
        options: List of possible valid interpretations
    """

    field: str = Field(description="The intent field with ambiguity")
    description: str = Field(description="Human-readable explanation of the ambiguity")
    severity: Literal["CRITICAL", "WARNING"] = Field(
        description="Impact level: CRITICAL blocks progress, WARNING is advisory"
    )
    options: list[str] = Field(
        default_factory=list,
        description="List of possible valid interpretations",
    )


class DesignMethodology(str, Enum):
    """Classification of design methodology based on application requirements.

    Determines the design rules, component selection criteria, and
    layout constraints applied during the design process.
    """

    RF_HIGHFREQ = "RF_highfreq"  # High-frequency RF designs (>100 MHz)
    POWER_MANAGEMENT = "power_management"  # Power supplies, regulators, converters
    MIXED_SIGNAL = "mixed_signal"  # Analog/digital mixed designs
    STANDARD_SMD = "standard_SMD"  # Standard surface-mount digital/analog
    THROUGH_HOLE = "through_hole"  # Through-hole designs (prototyping, high power)


class IntentDict(BaseModel):
    """Structured design intent extracted from user prompt.

    Represents the parsed and interpreted design requirements from
    natural language input. Includes frequency requirements, application
    context, constraints, and any detected ambiguities.

    Attributes:
        goal: High-level design objective (e.g., "5V to 3.3V buck regulator")
        frequency: Operating frequency for RF/power designs, None if N/A
        application: Target application domain (e.g., "IoT sensor", "automotive")
        explicit_constraints: User-specified constraints from prompt
        inferred_constraints: System-derived constraints from domain knowledge
        design_methodology: Selected methodology guiding design rules
        board_type: PCB classification (e.g., "2-layer FR4", "4-layer HDI")
        ambiguities: Detected ambiguities requiring clarification
        clarification_required: True if CRITICAL ambiguities exist
        raw_prompt: Original user input for provenance
    """

    goal: str = Field(description="High-level design objective")
    frequency: Optional[FrequencySpec] = Field(
        default=None, description="Operating frequency for RF/power designs, None if N/A"
    )
    application: str = Field(description="Target application domain")
    explicit_constraints: list[str] = Field(
        default_factory=list,
        description="User-specified constraints from prompt",
    )
    inferred_constraints: list[str] = Field(
        default_factory=list,
        description="System-derived constraints from domain knowledge",
    )
    design_methodology: DesignMethodology = Field(
        description="Selected methodology guiding design rules"
    )
    board_type: str = Field(description="PCB classification (e.g., '2-layer FR4')")
    ambiguities: list[AmbiguityFlag] = Field(
        default_factory=list, description="Detected ambiguities requiring clarification"
    )
    clarification_required: bool = Field(
        default=False,
        description="True if CRITICAL ambiguities exist requiring user input",
    )
    raw_prompt: str = Field(description="Original user input for provenance")


class BOMEntry(BaseModel):
    """Single entry in the Bill of Materials.

    Represents one component position in the design with selection
    status, constraints, and provenance. specific_part=None indicates
    the component requires human selection.

    Attributes:
        ref: Reference designator (e.g., "U1", "C3", "R12")
        component_type: Normalized component category (e.g., "regulator", "capacitor")
        specific_part: Selected part number or None if unresolved
        value_constraints: Electrical/physical constraints for selection
        justification: Design rationale for this component position
        source: Origin of this entry (rule, KG lookup, human)
        confidence: Confidence in component selection [0.0, 1.0]
        alternatives: Alternative part numbers if specific_part is set
        review_flag: True if human review recommended
    """

    ref: str = Field(description="Reference designator (e.g., 'U1', 'C3')")
    component_type: str = Field(
        description="Normalized component category (e.g., 'regulator', 'capacitor')"
    )
    specific_part: Optional[str] = Field(
        default=None, description="Selected part number or None if unresolved"
    )
    value_constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Electrical/physical constraints for selection",
    )
    justification: str = Field(description="Design rationale for this component position")
    source: str = Field(description="Origin of this entry (rule, KG lookup, human)")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in component selection [0.0, 1.0]"
    )
    alternatives: list[str] = Field(
        default_factory=list, description="Alternative part numbers if specific_part is set"
    )
    review_flag: bool = Field(
        default=False, description="True if human review recommended"
    )


class ValidatedBOM(BaseModel):
    """Complete Bill of Materials with validation status.

    Root container for the component selection output. Includes the
    design intent, all component entries, cross-component validation
    rules, and aggregated confidence metrics.

    Attributes:
        design_id: Unique identifier for this design
        intent: Parsed design intent that generated this BOM
        components: All component entries in the design
        cross_component_rules: Validation rules spanning multiple components
        total_confidence: Aggregate confidence across all selections
        review_flags: List of validation warning/info messages
        review_required: True if any component or rule needs review
        created_at: ISO 8601 timestamp of BOM creation
    """

    design_id: str = Field(description="Unique identifier for this design")
    intent: IntentDict = Field(
        description="Parsed design intent that generated this BOM"
    )
    components: list[BOMEntry] = Field(
        description="All component entries in the design"
    )
    cross_component_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Validation rules spanning multiple components",
    )
    total_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Aggregate confidence across all selections [0.0, 1.0]",
    )
    review_flags: list[str] = Field(
        default_factory=list,
        description="Validation warning/info messages for human review",
    )
    review_required: bool = Field(
        default=False,
        description="True if any component or rule needs human review",
    )
    created_at: str = Field(description="ISO 8601 timestamp of BOM creation")

    def unresolved_components(self) -> list[BOMEntry]:
        """Return list of components requiring human part selection.

        Filters the components list to return only entries where
        specific_part is None, indicating unresolved selection.

        Returns:
            List of BOMEntry objects with specific_part=None.
        """
        return [c for c in self.components if c.specific_part is None]


__all__ = [
    "FrequencySpec",
    "AmbiguityFlag",
    "DesignMethodology",
    "IntentDict",
    "BOMEntry",
    "ValidatedBOM",
]
