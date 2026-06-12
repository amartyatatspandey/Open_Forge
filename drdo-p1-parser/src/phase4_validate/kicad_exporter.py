"""Export validated datasheet data to KiCad-compatible JSON."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from src.schemas.datasheet import ComponentDatasheet, PinDefinition, ValidationResult


class KiCadPin(BaseModel):
    """Pin for KiCad symbol generation."""

    pin_number: str
    pin_name: str
    pin_type: str
    net_name: Optional[str] = None


class KiCadExport(BaseModel):
    """KiCad-compatible component export."""

    component_id: str
    manufacturer: str
    package: Optional[str] = None
    pins: list[KiCadPin]
    electrical_specs: dict
    validation_status: Literal["PASS", "WARN", "BLOCKED"]
    validation_message: Optional[str] = None


def infer_net_name(pin: PinDefinition) -> str:
    """Auto-assign net names based on pin type and name."""
    if pin.pin_type == "power":
        if "3.3" in pin.pin_name or "V33" in pin.pin_name:
            return "V_3V3"
        if "5" in pin.pin_name:
            return "V_5V"
        return "V_CC"
    if pin.pin_type == "ground":
        return "GND"
    if pin.pin_type == "clock":
        return "CLK"
    if pin.pin_type == "reset":
        return "RST"
    return pin.pin_name.upper()


def export_to_kicad(
    datasheet: ComponentDatasheet,
    validation_result: ValidationResult,
) -> KiCadExport:
    """Convert ComponentDatasheet to KiCad export format."""
    kicad_pins = [
        KiCadPin(
            pin_number=pin.pin_number,
            pin_name=pin.pin_name,
            pin_type=pin.pin_type,
            net_name=infer_net_name(pin),
        )
        for pin in datasheet.all_pins
    ]

    electrical_specs: dict = {}
    for param in datasheet.all_parameters:
        unit = "—"
        if param.min_value:
            unit = param.min_value.unit
        elif param.typ_value:
            unit = param.typ_value.unit
        elif param.max_value:
            unit = param.max_value.unit

        electrical_specs[param.name] = {
            "parameter_type": param.parameter_type,
            "min": param.min_value.value if param.min_value else None,
            "typ": param.typ_value.value if param.typ_value else None,
            "max": param.max_value.value if param.max_value else None,
            "unit": unit,
            "confidence": param.avg_confidence(),
        }

    if not validation_result.passed:
        status: Literal["PASS", "WARN", "BLOCKED"] = "BLOCKED"
        msg = f"{len(validation_result.errors)} critical errors"
    elif validation_result.review_required:
        status = "WARN"
        msg = f"{len(validation_result.warnings)} warnings; see review queue"
    else:
        status = "PASS"
        msg = None

    return KiCadExport(
        component_id=datasheet.component_id,
        manufacturer=datasheet.manufacturer or "Unknown",
        package=datasheet.package,
        pins=kicad_pins,
        electrical_specs=electrical_specs,
        validation_status=status,
        validation_message=msg,
    )
