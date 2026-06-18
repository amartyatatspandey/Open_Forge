"""Cross-parameter electrical relationship rules."""

from __future__ import annotations

from typing import Any, Callable

from src.schemas.datasheet import ElectricalParameter, ValidationError

RuleCheck = Callable[[ElectricalParameter, ElectricalParameter], bool]

ELECTRICAL_RULES: list[dict[str, Any]] = [
    {
        "rule": "V_CC > V_IL_max",
        "params": ["V_CC", "V_IL"],
        "check": lambda vcc, vil: vcc.typ_value.value > vil.max_value.value,
        "severity": "CRITICAL",
        "message": "Supply voltage must exceed logic-low threshold",
    },
    {
        "rule": "V_IH_min < V_CC_min",
        "params": ["V_IH", "V_CC"],
        "check": lambda vih, vcc: vih.max_value.value < vcc.min_value.value,
        "severity": "CRITICAL",
        "message": "Logic-high threshold must be less than supply voltage",
    },
    {
        "rule": "V_IL_max < V_IH_min",
        "params": ["V_IL", "V_IH"],
        "check": lambda vil, vih: vil.max_value.value < vih.min_value.value,
        "severity": "CRITICAL",
        "message": "Logic-low max must be less than logic-high min",
    },
    {
        "rule": "V_OL_max < V_IL_max",
        "params": ["V_OL", "V_IL"],
        "check": lambda vol, vil: vol.max_value.value < vil.max_value.value,
        "severity": "WARNING",
        "message": (
            "Output-low voltage should be less than input-low threshold "
            "(noise margin)"
        ),
    },
    {
        "rule": "V_OH_min > V_IH_min",
        "params": ["V_OH", "V_IH"],
        "check": lambda voh, vih: voh.min_value.value > vih.min_value.value,
        "severity": "WARNING",
        "message": (
            "Output-high voltage should exceed input-high threshold "
            "(noise margin)"
        ),
    },
]


def validate_cross_parameter_rules(
    parameters: list[ElectricalParameter],
) -> list[ValidationError]:
    """Check electrical relationships between parameters."""
    errors: list[ValidationError] = []
    param_lookup = {param.name: param for param in parameters}

    for rule in ELECTRICAL_RULES:
        param_names: list[str] = rule["params"]
        params_found = [param_lookup.get(name) for name in param_names]

        if any(param is None for param in params_found):
            continue

        try:
            rule_passes = rule["check"](*params_found)
        except (AttributeError, TypeError):
            continue

        if not rule_passes:
            errors.append(
                ValidationError(
                    level=rule["severity"],
                    param_name=f"{param_names[0]} vs {param_names[1]}",
                    message=f"Rule '{rule['rule']}' failed: {rule['message']}",
                    remediation="Check parameter extraction and datasheet structure",
                )
            )

    return errors
