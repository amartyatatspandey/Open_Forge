"""Physical plausibility range checks."""

from __future__ import annotations

from src.config import Config, get_config
from src.schemas.datasheet import AbsoluteMaxRating, ElectricalParameter, ValidationError


def _find_range_spec(
    param_name: str,
    ranges: dict[str, tuple[str, float, float]],
) -> tuple[str, float, float] | None:
    """Match parameter name against configured sanity range keys."""
    name_lower = param_name.lower()
    for pattern, spec in ranges.items():
        if pattern.lower() in name_lower:
            return spec
    return None


def validate_sanity_ranges(
    parameters: list[ElectricalParameter],
    abs_max_ratings: list[AbsoluteMaxRating] | None = None,
    config: Config | None = None,
) -> list[ValidationError]:
    """Check if values fall within physically plausible ranges."""
    _ = abs_max_ratings
    cfg = config or get_config()
    errors: list[ValidationError] = []

    for param in parameters:
        range_spec = _find_range_spec(param.name, cfg.sanity_ranges.ranges)
        if not range_spec:
            continue

        _param_type, min_sane, max_sane = range_spec

        for value_field, value_obj in [
            ("min", param.min_value),
            ("typ", param.typ_value),
            ("max", param.max_value),
        ]:
            if value_obj is None:
                continue

            if not (min_sane <= value_obj.value <= max_sane):
                errors.append(
                    ValidationError(
                        level="WARNING",
                        param_name=param.name,
                        message=(
                            f"{value_field} value {value_obj.value} {value_obj.unit} "
                            f"outside expected range [{min_sane}, {max_sane}]"
                        ),
                        remediation=(
                            "Check datasheet; possible OCR/extraction error or "
                            "unusual component spec"
                        ),
                    )
                )

    return errors
