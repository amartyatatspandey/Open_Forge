"""Validate Phase 3 extracted datasheet data."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from src.config import Config, get_config
from src.schemas.datasheet import (
    AbsoluteMaxRating,
    ElectricalParameter,
    PinDefinition,
    ValidationError,
    ValidationResult,
)


def _compute_confidence(
    parameters: list[ElectricalParameter],
    abs_max_ratings: list[AbsoluteMaxRating],
) -> float:
    """Average confidence across extracted parameter and abs-max values."""
    confidences: list[float] = []
    for param in parameters:
        for value in (param.min_value, param.typ_value, param.max_value):
            if value:
                confidences.append(value.confidence)
    for rating in abs_max_ratings:
        confidences.append(rating.max_value.confidence)
    if not confidences:
        return 0.0
    return sum(confidences) / len(confidences)


def validate_extracted_data(
    component_id: str,
    parameters: list[ElectricalParameter],
    pins: list[PinDefinition],
    abs_max_ratings: list[AbsoluteMaxRating],
    config: Config | None = None,
) -> ValidationResult:
    """Validate extracted electrical data before Phase 4."""
    cfg = config or get_config()
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    param_names = [param.name for param in parameters]
    duplicates = [name for name, count in Counter(param_names).items() if count > 1]
    if duplicates:
        errors.append(
            ValidationError(
                level="CRITICAL",
                param_name=",".join(duplicates),
                message=f"Duplicate parameters: {duplicates}",
                remediation="Check extraction for repeated rows",
            )
        )

    if not parameters:
        warnings.append(
            ValidationError(
                level="WARNING",
                param_name="(none)",
                message="No electrical parameters extracted",
            )
        )

    low_conf = [
        param
        for param in parameters
        if param.avg_confidence() < cfg.thresholds.block_extraction
    ]
    if low_conf:
        warnings.append(
            ValidationError(
                level="WARNING",
                param_name=",".join(p.name for p in low_conf),
                message=f"{len(low_conf)} parameters have low confidence",
            )
        )

    if not pins:
        warnings.append(
            ValidationError(
                level="WARNING",
                param_name="(none)",
                message="No pins extracted (expected for some components)",
            )
        )
    else:
        pin_numbers = [pin.pin_number for pin in pins]
        if len(pin_numbers) != len(set(pin_numbers)):
            errors.append(
                ValidationError(
                    level="CRITICAL",
                    param_name="pinout",
                    message="Duplicate pin numbers",
                    remediation="Check pinout table extraction",
                )
            )

    if not abs_max_ratings:
        warnings.append(
            ValidationError(
                level="WARNING",
                param_name="(none)",
                message="No absolute maximum ratings extracted",
            )
        )

    passed = len(errors) == 0
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ValidationResult(
        component_id=component_id,
        passed=passed,
        errors=errors,
        warnings=warnings,
        review_required=len(warnings) > 0,
        confidence_score=_compute_confidence(parameters, abs_max_ratings),
        timestamp=timestamp,
    )
