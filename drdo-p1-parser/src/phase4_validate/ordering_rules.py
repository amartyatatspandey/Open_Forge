"""Min/typ/max ordering validation rules."""

from __future__ import annotations

from src.schemas.datasheet import ElectricalParameter, ValidationError


def validate_min_typ_max_ordering(
    parameters: list[ElectricalParameter],
) -> list[ValidationError]:
    """Check min <= typ <= max for all parameters."""
    errors: list[ValidationError] = []

    for param in parameters:
        if param.min_value and param.typ_value:
            if param.min_value.value > param.typ_value.value:
                errors.append(
                    ValidationError(
                        level="CRITICAL",
                        param_name=param.name,
                        message=(
                            f"min ({param.min_value.value}) > typ "
                            f"({param.typ_value.value})"
                        ),
                        remediation=(
                            "Check datasheet table structure — may be inverted "
                            "or malformed"
                        ),
                    )
                )

        if param.typ_value and param.max_value:
            if param.typ_value.value > param.max_value.value:
                errors.append(
                    ValidationError(
                        level="CRITICAL",
                        param_name=param.name,
                        message=(
                            f"typ ({param.typ_value.value}) > max "
                            f"({param.max_value.value})"
                        ),
                        remediation="Check datasheet table structure",
                    )
                )

        if param.min_value and param.max_value and not param.typ_value:
            if param.min_value.value > param.max_value.value:
                errors.append(
                    ValidationError(
                        level="CRITICAL",
                        param_name=param.name,
                        message=(
                            f"min ({param.min_value.value}) > max "
                            f"({param.max_value.value})"
                        ),
                        remediation="Columns may be swapped",
                    )
                )

    return errors
