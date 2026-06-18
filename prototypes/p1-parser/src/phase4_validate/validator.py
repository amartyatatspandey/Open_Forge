"""Master validator orchestrating all Phase 4 rules."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.config import Config, get_config
from src.phase4_validate.absolute_max_rules import (
    validate_abs_max_sanity,
    validate_abs_max_vs_operating,
)
from src.phase4_validate.cross_parameter_rules import validate_cross_parameter_rules
from src.phase4_validate.ordering_rules import validate_min_typ_max_ordering
from src.phase4_validate.sanity_ranges import validate_sanity_ranges
from src.schemas.datasheet import (
    AbsoluteMaxRating,
    ComponentDatasheet,
    ElectricalParameter,
    PinDefinition,
    ValidationError,
    ValidationResult,
)

logger = logging.getLogger(__name__)


def compute_aggregate_confidence(
    parameters: list[ElectricalParameter],
    pins: list[PinDefinition],
    abs_max_ratings: list[AbsoluteMaxRating],
) -> float:
    """Weighted average confidence across all extracted values."""
    _ = pins
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


def run_full_validation(
    datasheet: ComponentDatasheet,
    config: Config | None = None,
) -> ValidationResult:
    """Run all validation rules and produce a ValidationResult."""
    cfg = config or get_config()

    parameters = datasheet.all_parameters
    pins = datasheet.all_pins
    abs_max_ratings = datasheet.all_abs_max

    logger.info("Phase 4: Validating %s", datasheet.component_id)
    logger.debug(
        "  %d parameters, %d pins, %d abs-max",
        len(parameters),
        len(pins),
        len(abs_max_ratings),
    )

    all_errors: list[ValidationError] = []
    all_warnings: list[ValidationError] = []

    all_errors.extend(validate_min_typ_max_ordering(parameters))
    all_warnings.extend(
        validate_sanity_ranges(parameters, abs_max_ratings, cfg)
    )

    cross_errors = validate_cross_parameter_rules(parameters)
    for err in cross_errors:
        if err.level == "CRITICAL":
            all_errors.append(err)
        else:
            all_warnings.append(err)

    all_errors.extend(validate_abs_max_vs_operating(abs_max_ratings, parameters))
    all_warnings.extend(validate_abs_max_sanity(abs_max_ratings))

    confidence_score = compute_aggregate_confidence(parameters, pins, abs_max_ratings)
    passed = len(all_errors) == 0
    review_required = (
        len(all_warnings) > 0
        or confidence_score < cfg.thresholds.warn_downstream
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = ValidationResult(
        component_id=datasheet.component_id,
        passed=passed,
        errors=all_errors,
        warnings=all_warnings,
        review_required=review_required,
        confidence_score=confidence_score,
        timestamp=timestamp,
    )

    logger.info(
        "Validation: passed=%s, errors=%d, warnings=%d, confidence=%.2f",
        passed,
        len(all_errors),
        len(all_warnings),
        confidence_score,
    )

    return result
