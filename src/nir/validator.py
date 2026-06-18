"""Structural validation for NIR documents."""

from __future__ import annotations

import logging

from src.schemas.nir import NIR, ReviewFlag

logger = logging.getLogger(__name__)

NIR_VALIDATION_RULES = [
    "every_netlist_ref_in_components",
    "every_placement_ref_in_components",
    "every_net_has_min_two_connections",
    "every_power_net_has_exactly_one_source",
    "no_component_with_zero_confidence",
    "critical_flags_set_review_required",
]

_POWER_SOURCE_PIN_NAMES = frozenset({"POWER_INPUT", "SWITCH_NODE", "VIN"})


def _validation_flag(
    item_ref: str,
    reason: str,
    severity: str,
) -> ReviewFlag:
    return ReviewFlag(
        item_ref=item_ref,
        reason=reason,
        severity=severity,  # type: ignore[arg-type]
        stage="nir_validation",
    )


def validate_nir(nir: NIR) -> NIR:
    """
    Run all structural validation rules against the NIR.
    Returns a new NIR with additional review_flags for any violations found.
    Never mutates input. Never raises.
    """
    new_flags: list[ReviewFlag] = []

    try:
        component_refs = {component.ref for component in nir.components}

        for net in nir.netlist:
            for pin in net.connections:
                if pin.ref not in component_refs:
                    new_flags.append(
                        _validation_flag(
                            pin.ref,
                            f"Net {net.net_name} references unknown ref {pin.ref}",
                            "CRITICAL",
                        )
                    )

        for constraint in nir.placement_constraints:
            if constraint.ref not in component_refs:
                new_flags.append(
                    _validation_flag(
                        constraint.ref,
                        f"Placement constraint references unknown ref {constraint.ref}",
                        "CRITICAL",
                    )
                )

        for net in nir.netlist:
            if net.net_type == "power":
                continue
            if len(net.connections) < 2:
                new_flags.append(
                    _validation_flag(
                        net.net_name,
                        f"Net {net.net_name} has only {len(net.connections)} connection",
                        "WARNING",
                    )
                )

        for net in nir.netlist:
            if net.net_type != "power":
                continue

            source_count = sum(
                1
                for pin in net.connections
                if pin.pin_name in _POWER_SOURCE_PIN_NAMES
            )
            if source_count == 0:
                new_flags.append(
                    _validation_flag(
                        net.net_name,
                        f"Power net {net.net_name} has no identified source pin",
                        "CRITICAL",
                    )
                )
            elif source_count > 1:
                new_flags.append(
                    _validation_flag(
                        net.net_name,
                        f"Power net {net.net_name} has {source_count} source pins",
                        "WARNING",
                    )
                )

        for component in nir.components:
            if component.datasheet_confidence == 0.0:
                new_flags.append(
                    _validation_flag(
                        component.ref,
                        f"Component {component.ref} has zero datasheet confidence",
                        "WARNING",
                    )
                )

        merged_flags = list(nir.review_flags) + new_flags
        validated = nir.model_copy(update={"review_flags": merged_flags})

        _ = validated.is_review_required()

    except Exception as exc:
        logger.error("NIR validation failed: %s", exc, exc_info=True)
        return nir.model_copy(
            update={
                "review_flags": nir.review_flags
                + [
                    _validation_flag(
                        nir.design_id,
                        f"NIR validation error: {exc}",
                        "CRITICAL",
                    )
                ]
            }
        )

    return validated
