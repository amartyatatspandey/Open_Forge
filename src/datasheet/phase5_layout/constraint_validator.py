"""Post-LLM validation for extracted placement constraints.

Validates and finalizes PlacementConstraint objects from LLM output,
including type resolution and confidence thresholding.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.datasheet.phase5_layout._schemas import LayoutExtractionResult
from src.datasheet.phase5_layout.type_resolver import resolve_relative_to_type
from src.schemas.datasheet import PlacementConstraint

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Minimum confidence threshold for accepting a constraint
MIN_CONFIDENCE_THRESHOLD = 0.65


def validate_and_finalize(result: LayoutExtractionResult) -> list[PlacementConstraint]:
    """Validate and finalize extracted constraints from LLM output.

    Performs the following validations on each constraint:
    1. Resolves relative_to_type using type_resolver
    2. Skips constraints with confidence < 0.65 (logs DEBUG)
    3. Skips constraints with empty subject (logs WARNING)

    Args:
        result: LayoutExtractionResult from spatial_parser LLM call

    Returns:
        List of validated PlacementConstraint objects.
        Returns empty list if no constraints pass validation.

    Example:
        >>> result = LayoutExtractionResult(constraints=[c1, c2, c3])
        >>> valid = validate_and_finalize(result)
        >>> len(valid) <= len(result.constraints)
        True
    """
    validated: list[PlacementConstraint] = []
    skipped_low_confidence = 0
    skipped_empty_subject = 0

    for i, constraint in enumerate(result.constraints):
        try:
            # Check 1: Empty subject validation
            if not constraint.subject or not constraint.subject.strip():
                logger.warning(
                    f"Constraint {i}: empty subject, skipping"
                )
                skipped_empty_subject += 1
                continue

            # Check 2: Confidence threshold
            confidence = getattr(constraint, 'confidence', 1.0)
            if confidence < MIN_CONFIDENCE_THRESHOLD:
                logger.debug(
                    f"Constraint {i}: confidence {confidence:.2f} < "
                    f"{MIN_CONFIDENCE_THRESHOLD}, skipping"
                )
                skipped_low_confidence += 1
                continue

            # Check 3: Resolve relative_to_type
            resolved_type, needs_review = resolve_relative_to_type(
                constraint.relative_to
            )

            # Create updated constraint with resolved type
            # Note: We need to create a new constraint since relative_to_type
            # is set during creation (it's a Literal type)
            try:
                updated_constraint = PlacementConstraint(
                    constraint_type=constraint.constraint_type,
                    subject=constraint.subject,
                    relative_to=constraint.relative_to,
                    relative_to_type=resolved_type,
                    max_distance_mm=constraint.max_distance_mm,
                    min_distance_mm=constraint.min_distance_mm,
                    layer=constraint.layer,
                    hard=constraint.hard,
                    source_sentence=constraint.source_sentence,
                    confidence=confidence,
                )
                validated.append(updated_constraint)

                if needs_review:
                    logger.debug(
                        f"Constraint {i}: relative_to_type resolved to "
                        f"'{resolved_type}' with needs_review flag"
                    )

            except Exception as e:
                logger.warning(
                    f"Constraint {i}: failed to create updated constraint: {e}"
                )
                continue

        except Exception as e:
            logger.warning(f"Constraint {i}: validation failed with error: {e}")
            continue

    # Log summary
    total = len(result.constraints)
    kept = len(validated)
    if total > 0:
        logger.info(
            f"Validation complete: {kept}/{total} constraints kept "
            f"({skipped_low_confidence} low confidence, "
            f"{skipped_empty_subject} empty subject)"
        )

    return validated
