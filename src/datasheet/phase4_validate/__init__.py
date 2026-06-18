"""Phase 4: Validation and verdict application.

Validates extracted ComponentDatasheet objects and applies validation verdicts.
Determines if a component passes validation, requires review, or is blocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.schemas.datasheet import ComponentDatasheet

if TYPE_CHECKING:
    from src.config import Config


@dataclass
class ValidationResult:
    """Result of validating a ComponentDatasheet."""

    verdict: str  # "PASS", "WARN", "BLOCK"
    severity: str  # "CRITICAL", "WARNING"
    confidence: float
    flags: list[str]


def validate(
    datasheet: ComponentDatasheet,
    config: Config,
) -> ValidationResult:
    """Validate a ComponentDatasheet.

    Performs validation checks and returns a ValidationResult with verdict.

    Args:
        datasheet: ComponentDatasheet to validate
        config: Application configuration

    Returns:
        ValidationResult with verdict and severity
    """
    flags = []

    # Check for empty critical fields
    if not datasheet.component_id and not getattr(datasheet, '_component_id', None):
        flags.append("Missing component_id")

    if not datasheet.manufacturer:
        flags.append("Missing manufacturer")

    if not datasheet.package:
        flags.append("Missing package")

    # Check extraction confidence
    confidence = datasheet.extraction_confidence
    if confidence < 0.5:
        flags.append(f"Low extraction confidence: {confidence:.2f}")

    # Determine verdict based on flags and confidence
    if confidence < 0.3:
        verdict = "BLOCK"
        severity = "CRITICAL"
    elif confidence < 0.7 or flags:
        verdict = "WARN"
        severity = "WARNING" if flags else "WARNING"
    else:
        verdict = "PASS"
        severity = "WARNING"  # Default severity

    return ValidationResult(
        verdict=verdict,
        severity=severity,
        confidence=confidence,
        flags=flags,
    )


def apply_verdict(
    datasheet: ComponentDatasheet,
    validation_result: ValidationResult,
) -> ComponentDatasheet:
    """Apply validation verdict to a ComponentDatasheet.

    Creates a new ComponentDatasheet with review_required set based on
the validation verdict. Never mutates the original object.

    Args:
        datasheet: Original ComponentDatasheet
        validation_result: Validation result with verdict

    Returns:
        New ComponentDatasheet with review_required flag set
    """
    # Determine if review is required
    review_required = validation_result.verdict in ("BLOCK", "WARN")

    # Create new datasheet with updated fields
    updated_datasheet = datasheet.model_copy(
        update={
            "review_required": review_required,
            "review_flags": list(set(datasheet.review_flags + validation_result.flags)),
        }
    )

    return updated_datasheet

check = validate
