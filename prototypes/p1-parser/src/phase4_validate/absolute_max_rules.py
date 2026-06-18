"""Absolute maximum rating validation rules."""

from __future__ import annotations

from src.phase3_extract.parameter_extractor import infer_param_type
from src.schemas.datasheet import AbsoluteMaxRating, ElectricalParameter, ValidationError

ABS_MAX_BOUNDS: dict[str, tuple[float, float]] = {
    "voltage": (0.0, 200.0),
    "current": (0.0, 100_000.0),
    "temperature": (-65.0, 300.0),
}


def _strip_suffix(name: str) -> str:
    """Strip abs-max suffixes for name matching."""
    for suffix in ("_ABS", "_MAX"):
        name = name.replace(suffix, "")
    return name


def validate_abs_max_vs_operating(
    abs_max_ratings: list[AbsoluteMaxRating],
    parameters: list[ElectricalParameter],
) -> list[ValidationError]:
    """Ensure abs-max ceiling exceeds recommended operating maximum."""
    errors: list[ValidationError] = []

    operating_max: dict[str, float] = {}
    for param in parameters:
        base_name = _strip_suffix(param.name)
        if param.max_value:
            operating_max[base_name] = param.max_value.value

    for rating in abs_max_ratings:
        base_name = _strip_suffix(rating.name)
        if base_name not in operating_max:
            continue

        op_max = operating_max[base_name]
        abs_val = rating.max_value.value

        if abs_val <= op_max:
            errors.append(
                ValidationError(
                    level="CRITICAL",
                    param_name=rating.name,
                    message=(
                        f"abs-max ({abs_val}) <= operating_max ({op_max}) — "
                        "tables may be swapped"
                    ),
                    remediation=(
                        "Verify absolute maximum ratings table is not confused "
                        "with operating range"
                    ),
                )
            )

    return errors


def validate_abs_max_sanity(
    abs_max_ratings: list[AbsoluteMaxRating],
) -> list[ValidationError]:
    """Basic sanity: abs-max values within physical bounds."""
    errors: list[ValidationError] = []

    for rating in abs_max_ratings:
        param_type = infer_param_type(rating.name)
        if param_type not in ABS_MAX_BOUNDS:
            continue

        lo, hi = ABS_MAX_BOUNDS[param_type]
        val = rating.max_value.value

        if not (lo <= val <= hi):
            errors.append(
                ValidationError(
                    level="WARNING",
                    param_name=rating.name,
                    message=(
                        f"abs-max {val} {rating.max_value.unit} outside plausible "
                        f"range [{lo}, {hi}]"
                    ),
                    remediation="Check extraction; possible OCR error",
                )
            )

    return errors
