"""IPC-7351 footprint name → tscircuit registry name mapping."""

from __future__ import annotations

TSCIRCUIT_FOOTPRINT_MAP: dict[str, str] = {
    "SOT-23-5": "SOT-23-5",
    "SOT-23-3": "SOT-23",
    "SOT-23": "SOT-23",
    "SOIC-8": "SOIC-8_3.9x4.9mm_P1.27mm",
    "SOIC-16": "SOIC-16_3.9x9.9mm_P1.27mm",
    "DIP-8": "DIP-8_W7.62mm",
    "DIP-14": "DIP-14_W7.62mm",
    "QFN-16": "QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm",
    "QFN-24": "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
    "QFN-32": "QFN-32-1EP_5x5mm_P0.5mm_EP3.4x3.4mm",
    "TSSOP-8": "TSSOP-8_3x3mm_P0.65mm",
    "TSSOP-16": "TSSOP-16_4.4x5mm_P0.65mm",
    "TO-220": "TO-220-3_Vertical",
    "TO-92": "TO-92_Inline",
    "0402": "R_0402_1005Metric",
    "0603": "R_0603_1608Metric",
    "0805": "R_0805_2012Metric",
    "1206": "R_1206_3216Metric",
    "0402_C": "C_0402_1005Metric",
    "0603_C": "C_0603_1608Metric",
    "0805_C": "C_0805_2012Metric",
}


def resolve_footprint(
    ipc_name: str,
    component_type: str,
) -> tuple[str, bool]:
    """
    Translate IPC-7351 footprint name to tscircuit registry name.
    Returns (resolved_name, needs_review).
    needs_review=True when no mapping found.

    For passive components (resistor/capacitor/inductor), appends
    type-specific suffix to distinguish pad sizes:
        resistor  + 0402 → R_0402_1005Metric
        capacitor + 0402 → C_0402_1005Metric
    """
    passive_prefix_map = {
        "resistor": "R",
        "capacitor": "C",
        "inductor": "L",
    }
    passive_size_map = {
        "0402": "_0402_1005Metric",
        "0603": "_0603_1608Metric",
        "0805": "_0805_2012Metric",
        "1206": "_1206_3216Metric",
    }

    prefix = passive_prefix_map.get(component_type)
    if prefix and ipc_name in passive_size_map:
        return f"{prefix}{passive_size_map[ipc_name]}", False

    if ipc_name in TSCIRCUIT_FOOTPRINT_MAP:
        return TSCIRCUIT_FOOTPRINT_MAP[ipc_name], False

    return ipc_name, True
