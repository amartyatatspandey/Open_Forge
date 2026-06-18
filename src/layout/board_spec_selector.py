"""Board specification selection by design methodology."""

from __future__ import annotations

from src.schemas.nir import BoardSpec

METHODOLOGY_BOARD_SPECS: dict[str, BoardSpec] = {
    "RF_highfreq": BoardSpec(
        layers=2,
        material="Rogers_4003C",
        thickness_mm=0.8,
        copper_weight_oz=1.0,
        min_trace_width_mm=0.1,
        min_clearance_mm=0.1,
        min_via_drill_mm=0.2,
        surface_finish="ENIG",
    ),
    "power_management": BoardSpec(
        layers=2,
        material="FR4",
        thickness_mm=1.6,
        copper_weight_oz=2.0,
        min_trace_width_mm=0.2,
        min_clearance_mm=0.2,
        min_via_drill_mm=0.3,
        surface_finish="HASL",
    ),
    "mixed_signal": BoardSpec(
        layers=4,
        material="FR4",
        thickness_mm=1.6,
        copper_weight_oz=1.0,
        min_trace_width_mm=0.1,
        min_clearance_mm=0.15,
        min_via_drill_mm=0.25,
        surface_finish="ENIG",
    ),
    "standard_SMD": BoardSpec(
        layers=2,
        material="FR4",
        thickness_mm=1.6,
        copper_weight_oz=1.0,
        min_trace_width_mm=0.15,
        min_clearance_mm=0.15,
        min_via_drill_mm=0.3,
        surface_finish="HASL",
    ),
    "through_hole": BoardSpec(
        layers=2,
        material="FR4",
        thickness_mm=1.6,
        copper_weight_oz=1.0,
        min_trace_width_mm=0.25,
        min_clearance_mm=0.25,
        min_via_drill_mm=0.8,
        surface_finish="HASL",
    ),
}


def select_board_spec(methodology: str) -> BoardSpec:
    """Select board specification for a design methodology."""
    spec = METHODOLOGY_BOARD_SPECS.get(methodology)
    if spec is None:
        return METHODOLOGY_BOARD_SPECS["standard_SMD"].model_copy(deep=True)
    return spec.model_copy(deep=True)
