"""IPC-7351 footprint name → KiCad footprint library mapping."""

from __future__ import annotations

KICAD_FOOTPRINT_MAP: dict[str, str] = {
    "SOT-23-5": "Package_TO_SOT_SMD:SOT-23-5",
    "SOT-23-3": "Package_TO_SOT_SMD:SOT-23",
    "SOIC-8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "SOIC-16": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
    "DIP-8": "Package_DIP:DIP-8_W7.62mm",
    "QFN-16": "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm",
    "0402": "Resistor_SMD:R_0402_1005Metric",
    "0603": "Resistor_SMD:R_0603_1608Metric",
    "0805": "Resistor_SMD:R_0805_2012Metric",
    "TO-220": "Package_TO_SOT_THT:TO-220-3_Vertical",
}


def resolve_kicad_footprint(ipc_name: str) -> str:
    return KICAD_FOOTPRINT_MAP.get(ipc_name, f"Package_SO:{ipc_name}")
