"""Functional block classification."""

from __future__ import annotations

from src.schemas.intent import ValidatedBOM
from src.schemas.nir import NetlistEntry

from src.schematic._schemas import FunctionalBlock

_BLOCK_KEYWORDS: dict[str, list[str]] = {
    "power": ["regulator", "ldo", "buck", "boost", "converter", "charger"],
    "RF": ["antenna", "rf", "bluetooth", "wifi", "lora", "wireless"],
    "digital": ["microcontroller", "mcu", "processor", "fpga", "gate", "flip"],
    "analog": ["op_amp", "opamp", "adc", "dac", "comparator", "amplifier"],
    "passive": ["capacitor", "resistor", "inductor", "crystal", "fuse"],
}

_PROTOCOL_PREFIXES = ("SPI_", "I2C_", "UART_")


def _classify_component(component_type: str) -> str | None:
    lowered = component_type.lower()
    for block_type, keywords in _BLOCK_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return block_type
    return None


def classify_blocks(
    bom: ValidatedBOM,
    netlist: list[NetlistEntry],
) -> list[FunctionalBlock]:
    """Group components into functional blocks."""
    ref_to_type: dict[str, str] = {entry.ref: entry.component_type for entry in bom.components}
    ref_blocks: dict[str, str] = {}

    for entry in bom.components:
        block_type = _classify_component(entry.component_type)
        if block_type is None:
            block_type = "mixed"
        ref_blocks[entry.ref] = block_type

    protocol_refs: set[str] = set()
    for net in netlist:
        if any(net.net_name.startswith(prefix) for prefix in _PROTOCOL_PREFIXES):
            for conn in net.connections:
                protocol_refs.add(conn.ref)

    if protocol_refs:
        dominant = "digital"
        for ref in protocol_refs:
            if ref in ref_blocks and ref_blocks[ref] == "mixed":
                ref_blocks[ref] = dominant

    grouped: dict[str, list[str]] = {}
    for ref, block_type in ref_blocks.items():
        grouped.setdefault(block_type, []).append(ref)

    blocks: list[FunctionalBlock] = []
    for block_type, refs in grouped.items():
        isolation = block_type in ("RF", "analog")
        blocks.append(
            FunctionalBlock(
                name=f"{block_type}_block",
                refs=sorted(refs),
                block_type=block_type,  # type: ignore[arg-type]
                isolation_required=isolation,
            )
        )

    return blocks
