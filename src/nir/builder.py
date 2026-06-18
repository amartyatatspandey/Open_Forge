"""NIR assembly from upstream pipeline artifacts."""

from __future__ import annotations

from datetime import datetime, timezone

from src.layout._schemas import LayoutSpec
from src.schemas.datasheet import ComponentDatasheet
from src.schemas.intent import ValidatedBOM
from src.schemas.nir import ComponentRef, NIR, PinRef, ReviewFlag
from src.schematic._schemas import SchematicGraph

_POWER_PIN_NAMES = frozenset({
    "VCC",
    "GND",
    "VIN",
    "POWER_POSITIVE",
    "POWER_GROUND",
    "POWER_INPUT",
})


def _datasheet_lookup(
    datasheets: list[ComponentDatasheet],
) -> dict[str, ComponentDatasheet]:
    return {ds.component_id: ds for ds in datasheets}


def _bom_flag_to_review_flag(design_id: str, flag_str: str) -> ReviewFlag:
    return ReviewFlag(
        item_ref=design_id,
        reason=flag_str,
        severity="WARNING",
        stage="bom_generation",
    )


def _unresolved_pin_flag(pin: PinRef) -> ReviewFlag:
    is_power = pin.pin_name in _POWER_PIN_NAMES
    return ReviewFlag(
        item_ref=f"{pin.ref}.{pin.pin_number}",
        reason=f"Unresolved pin {pin.pin_name} on {pin.ref}",
        severity="CRITICAL" if is_power else "WARNING",
        stage="schematic_synthesis",
    )


def assemble_nir(
    bom: ValidatedBOM,
    datasheets: list[ComponentDatasheet],
    schematic: SchematicGraph,
    layout: LayoutSpec,
) -> NIR:
    """Map upstream artifacts to a NIR document."""
    datasheet_by_id = _datasheet_lookup(datasheets)

    components: list[ComponentRef] = []
    for entry in bom.components:
        matching = (
            datasheet_by_id.get(entry.specific_part)
            if entry.specific_part is not None
            else None
        )
        components.append(
            ComponentRef(
                ref=entry.ref,
                component_id=entry.specific_part or entry.component_type,
                component_type=entry.component_type,
                footprint=matching.package if matching is not None else "UNKNOWN",
                value=entry.value_constraints.get("value"),
                manufacturer=matching.manufacturer if matching is not None else "",
                datasheet_confidence=entry.confidence,
                justification=entry.justification,
            )
        )

    review_flags: list[ReviewFlag] = list(schematic.review_flags)
    review_flags.extend(
        _bom_flag_to_review_flag(bom.design_id, flag_str)
        for flag_str in bom.review_flags
    )
    review_flags.extend(
        _unresolved_pin_flag(pin) for pin in schematic.unresolved_pins
    )

    return NIR(
        design_id=bom.design_id,
        prompt=bom.intent.raw_prompt,
        design_methodology=bom.intent.design_methodology.value,
        components=components,
        netlist=list(schematic.netlist),
        placement_constraints=list(layout.placement_constraints),
        component_groups=list(layout.component_groups),
        routing_hints=list(layout.routing_hints),
        board_spec=layout.board_spec.model_copy(deep=True),
        confidence_scores={entry.ref: entry.confidence for entry in bom.components},
        net_confidence={
            net.net_name: net.net_confidence for net in schematic.netlist
        },
        justifications={entry.ref: entry.justification for entry in bom.components},
        source_citations={entry.ref: entry.source for entry in bom.components},
        review_flags=review_flags,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
