"""Routing hint generation from netlist and board specification."""

from __future__ import annotations

from src.schemas.nir import BoardSpec, NetlistEntry, RoutingHint

NET_TYPE_HINTS: dict[str, list[RoutingHint]] = {
    "RF": [
        RoutingHint(
            nets=[],
            hint_type="impedance_controlled",
            value=50.0,
            unit="ohm",
            note="50Ω RF trace",
        ),
    ],
    "clock": [
        RoutingHint(
            nets=[],
            hint_type="isolation",
            note="Isolate clock traces from analog signals",
        ),
    ],
    "differential": [
        RoutingHint(
            nets=[],
            hint_type="length_matched",
            note="Length-match differential pair",
        ),
    ],
}

_RF_TRACE_WIDTH_MM: dict[str, float] = {
    "FR4": 2.0,
    "Rogers_4003C": 0.35,
}


def _rf_trace_width(board_spec: BoardSpec) -> float:
    material = board_spec.material
    for key, width in _RF_TRACE_WIDTH_MM.items():
        if key in material:
            return width
    return _RF_TRACE_WIDTH_MM["FR4"]


def generate_routing_hints(
    netlist: list[NetlistEntry],
    board_spec: BoardSpec,
) -> list[RoutingHint]:
    """Generate routing hints based on net_type and board material."""
    hints: list[RoutingHint] = []

    for net in netlist:
        templates = NET_TYPE_HINTS.get(net.net_type, [])
        for template in templates:
            hint = template.model_copy(deep=True)
            hint.nets = [net.net_name]

            if net.net_type == "RF":
                trace_width = _rf_trace_width(board_spec)
                hint.note = (
                    f"{hint.note}; microstrip width ≈ {trace_width:.2f}mm "
                    f"for 50Ω on {board_spec.material}"
                )

            hints.append(hint)

    return hints
