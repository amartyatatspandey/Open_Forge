"""Component ID/type → KiCad symbol library mapping."""

from __future__ import annotations

from pydantic import BaseModel


class KiCadSymbolRef(BaseModel):
    library: str
    symbol: str


KICAD_SYMBOL_MAP: dict[str, KiCadSymbolRef] = {
    "TPS62933DRLR": KiCadSymbolRef(library="Device", symbol="TPS62933"),
}

KICAD_TYPE_MAP: dict[str, KiCadSymbolRef] = {
    "resistor": KiCadSymbolRef(library="Device", symbol="R"),
    "capacitor": KiCadSymbolRef(library="Device", symbol="C"),
    "inductor": KiCadSymbolRef(library="Device", symbol="L"),
    "diode": KiCadSymbolRef(library="Device", symbol="D"),
    "led": KiCadSymbolRef(library="Device", symbol="LED"),
    "transistor": KiCadSymbolRef(library="Device", symbol="Q_NPN_BCE"),
    "mosfet": KiCadSymbolRef(library="Device", symbol="Q_NMOS_GSD"),
    "crystal": KiCadSymbolRef(library="Device", symbol="Crystal"),
    "connector": KiCadSymbolRef(library="Connector", symbol="Conn_01x02"),
}


def resolve_kicad_symbol(
    component_id: str,
    component_type: str,
) -> KiCadSymbolRef:
    if component_id in KICAD_SYMBOL_MAP:
        return KICAD_SYMBOL_MAP[component_id]
    if component_type in KICAD_TYPE_MAP:
        return KICAD_TYPE_MAP[component_type]
    return KiCadSymbolRef(library="Device", symbol="IC")
