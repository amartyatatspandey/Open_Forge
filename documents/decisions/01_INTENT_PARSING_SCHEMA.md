# Q1 — Improved Intent Parsing Schema

## What the Current Output Gets Right

The current parser correctly extracts the goal, methodology, board type, and explicit constraint strings. For Prompt 1, `goal=current_source` and `methodology=mixed_signal` are both correct. The explicit constraints list is complete.

## What Is Missing

The current schema treats all requirements as flat strings in `explicit_constraints`. This makes downstream processing difficult — the BOM generator has to re-parse "ultra low noise" to determine what that actually means numerically. The schema needs typed, structured fields per requirement category so that the rest of the pipeline can reason about specific numbers and conditions without re-invoking the LLM.

### Missing Categories

**Performance requirements** — The prompt implies numerical targets (100mA output, ultra-low noise) but the schema stores them as strings. A noise-aware component selector needs the noise target in pA/√Hz, not the string "ultra low noise."

**Electrical constraints** — Supply voltage range, power budget, output compliance voltage, load regulation target — none extracted.

**Thermal constraints** — Zero-drift op-amps imply temperature stability requirements. Operating temperature range, thermal matching, and tempco targets are all implied but not captured.

**Manufacturing constraints** — PCB layer count, assembly process, board dimensions, minimum feature sizes.

**Reliability requirements** — MTBF, environmental rating, operating environment (lab vs industrial vs military).

**Compliance requirements** — MIL-SPEC, RoHS, CE, REACH — especially relevant for DRDO use cases.

**Cost and availability** — Budget per board, COTS preference, obsolescence sensitivity.

**Implied requirements** — The most important missing category. Zero-drift op-amps imply low-noise LDOs. Libbrecht-Hall implies Kelvin sensing. Ultra-precision resistors imply low tempco. None of this is captured because the current schema has no field for inferred constraints.

---

## Improved Schema

```python
from __future__ import annotations
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field
from enum import Enum


# ── Sub-schemas for each requirement category ──────────────────────────────

class NoiseSpec(BaseModel):
    """Quantitative noise requirement."""
    target_value: Optional[float] = None
    unit: Optional[str] = None          # "pA/rtHz", "nV/rtHz", "ppm"
    bandwidth_hz: Optional[float] = None
    measurement_condition: Optional[str] = None
    raw_text: str                        # original string from prompt

class AccuracySpec(BaseModel):
    absolute_ppm: Optional[float] = None
    relative_percent: Optional[float] = None
    drift_ppm_per_C: Optional[float] = None
    raw_text: str

class StabilitySpec(BaseModel):
    short_term_ppm: Optional[float] = None
    long_term_ppm_per_year: Optional[float] = None
    thermal_stability_ppm_per_C: Optional[float] = None
    raw_text: str

class PerformanceRequirements(BaseModel):
    noise: Optional[NoiseSpec] = None
    accuracy: Optional[AccuracySpec] = None
    stability: Optional[StabilitySpec] = None
    output_current_ma: Optional[float] = None
    output_current_range: Optional[tuple[float, float]] = None
    adjustability: Optional[str] = None     # "potentiometer", "DAC", "fixed"
    settling_time_us: Optional[float] = None
    bandwidth_hz: Optional[float] = None


class VoltageSpec(BaseModel):
    min_v: Optional[float] = None
    typ_v: Optional[float] = None
    max_v: Optional[float] = None
    raw_text: str

class CurrentSpec(BaseModel):
    min_ma: Optional[float] = None
    typ_ma: Optional[float] = None
    max_ma: Optional[float] = None
    raw_text: str

class ElectricalConstraints(BaseModel):
    supply_voltage: Optional[VoltageSpec] = None
    supply_topology: Optional[str] = None    # "single_dc", "dual_rail", "battery"
    supply_current_budget: Optional[CurrentSpec] = None
    output_voltage_compliance: Optional[VoltageSpec] = None
    output_current: Optional[CurrentSpec] = None
    power_budget_mw: Optional[float] = None
    input_impedance_ohm: Optional[float] = None
    output_impedance_ohm: Optional[float] = None
    isolation_required: bool = False
    polarity_generation_required: bool = False  # "generate all required polarities"


class ThermalConstraints(BaseModel):
    operating_temp_min_c: Optional[float] = None
    operating_temp_max_c: Optional[float] = None
    storage_temp_min_c: Optional[float] = None
    storage_temp_max_c: Optional[float] = None
    thermal_matching_required: bool = False
    kelvin_sensing_required: bool = False
    max_self_heating_c: Optional[float] = None
    thermal_resistance_target_c_per_w: Optional[float] = None


class ManufacturingConstraints(BaseModel):
    assembly_process: Optional[str] = None   # "SMD_reflow", "hand_solder", "mixed"
    pcb_layers: Optional[int] = None
    board_dimensions_mm: Optional[tuple[float, float]] = None
    min_trace_width_mm: Optional[float] = None
    min_clearance_mm: Optional[float] = None
    surface_finish: Optional[str] = None
    ipc_class: Optional[str] = None          # "IPC-A-610 Class 2", "Class 3"


class ReliabilityRequirements(BaseModel):
    mtbf_hours: Optional[float] = None
    operating_environment: Optional[str] = None  # "lab", "industrial", "military", "space"
    vibration_spec: Optional[str] = None
    shock_spec: Optional[str] = None
    humidity_range_percent: Optional[tuple[float, float]] = None
    altitude_m: Optional[float] = None
    radiation_tolerance: Optional[str] = None


class ComplianceRequirements(BaseModel):
    standards: list[str] = Field(default_factory=list)
    # e.g. ["MIL-STD-461", "RoHS", "REACH", "CE", "DO-160", "MIL-PRF-38534"]
    emc_class: Optional[str] = None
    safety_class: Optional[str] = None
    export_control: Optional[str] = None    # "EAR99", "ECCN", "ITAR"
    country_of_origin_restriction: Optional[str] = None


class CostConstraints(BaseModel):
    bom_budget_usd: Optional[float] = None
    per_unit_target_usd: Optional[float] = None
    production_volume: Optional[str] = None  # "prototype", "small_batch", "production"
    prefer_cots: bool = True
    avoid_obsolete: bool = True
    preferred_suppliers: list[str] = Field(default_factory=list)
    blacklisted_suppliers: list[str] = Field(default_factory=list)


class ComponentPreference(BaseModel):
    component_type: str                      # "op_amp", "resistor", "ldo"
    preferred_series: Optional[str] = None  # "OPA189 series"
    preferred_manufacturer: Optional[str] = None
    required_attribute: Optional[str] = None # "zero_drift", "ultra_precision"
    exclusion: Optional[str] = None


class ImpliedRequirement(BaseModel):
    """
    Generated by the Requirement Completion Engine (Stage 2).
    Not extracted from the prompt — inferred from domain knowledge.
    """
    requirement: str
    component_implication: Optional[str] = None  # what component this maps to
    reasoning: str                               # why this is implied
    confidence: float = Field(ge=0.0, le=1.0)
    source_constraint: str                       # which explicit constraint implied this
    priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class DesignRequest(BaseModel):
    """
    A specific deliverable requested in the prompt beyond the PCB design.
    """
    request_type: Literal[
        "bom",
        "schematic",
        "pcb_layout",
        "noise_analysis",
        "simulation",
        "spice_netlist",
        "design_report",
        "python_gui",              # out of scope — flagged
        "firmware",                # out of scope — flagged
    ]
    in_scope: bool
    out_of_scope_reason: Optional[str] = None


# ── Improved IntentDict ────────────────────────────────────────────────────

class ImprovedIntentDict(BaseModel):
    """
    Version 2 intent schema. Replaces flat explicit_constraints list with
    typed, structured requirement categories.
    """

    # Core identification (v1 fields, enhanced)
    goal: str
    goal_confidence: float = Field(ge=0.0, le=1.0)
    goal_topology: Optional[str] = None     # e.g. "libbrecht_hall" for current_source
    application: str = "unspecified"
    design_methodology: str
    board_type: str

    # Typed requirement categories (new in v2)
    performance: Optional[PerformanceRequirements] = None
    electrical: Optional[ElectricalConstraints] = None
    thermal: Optional[ThermalConstraints] = None
    manufacturing: Optional[ManufacturingConstraints] = None
    reliability: Optional[ReliabilityRequirements] = None
    compliance: Optional[ComplianceRequirements] = None
    cost: Optional[CostConstraints] = None
    component_preferences: list[ComponentPreference] = Field(default_factory=list)

    # Explicit constraint strings (kept for backward compatibility)
    explicit_constraints: list[str] = Field(default_factory=list)

    # Completion engine outputs (populated in Stage 2)
    inferred_constraints: list[str] = Field(default_factory=list)
    implied_requirements: list[ImpliedRequirement] = Field(default_factory=list)
    missing_critical_specs: list[str] = Field(default_factory=list)
    contradictions_detected: list[str] = Field(default_factory=list)

    # Requested deliverables
    design_requests: list[DesignRequest] = Field(default_factory=list)

    # Ambiguity tracking
    ambiguities: list[dict] = Field(default_factory=list)
    clarification_required: bool = False

    # Metadata
    raw_prompt: str
    parsed_at: str
    parser_version: str = "2.0"
    schema_version: str = "2.0"
```

---

## What Version 2 Produces for Prompt 1

```json
{
  "goal": "current_source",
  "goal_confidence": 0.97,
  "goal_topology": "libbrecht_hall",
  "application": "precision_measurement",
  "design_methodology": "mixed_signal",
  "board_type": "double_sided_SMD",

  "performance": {
    "noise": {
      "target_value": null,
      "unit": "pA/rtHz",
      "raw_text": "ultra low noise"
    },
    "output_current_ma": 100.0,
    "output_current_range": [0.0, 100.0],
    "adjustability": "potentiometer",
    "stability": {
      "raw_text": "highly stable"
    }
  },

  "electrical": {
    "supply_topology": "single_dc",
    "polarity_generation_required": true,
    "isolation_required": false
  },

  "thermal": {
    "thermal_matching_required": true,
    "kelvin_sensing_required": true
  },

  "component_preferences": [
    {"component_type": "op_amp", "required_attribute": "zero_drift"},
    {"component_type": "resistor", "required_attribute": "ultra_precision"},
    {"component_type": "ldo", "required_attribute": "low_noise"}
  ],

  "design_requests": [
    {"request_type": "bom", "in_scope": true},
    {"request_type": "noise_analysis", "in_scope": true}
  ],

  "missing_critical_specs": [
    "Output current noise target not quantified (pA/rtHz)",
    "Supply voltage not specified",
    "Operating temperature range not specified",
    "Load compliance voltage not specified",
    "Current adjustment range and resolution not specified"
  ],

  "ambiguities": [
    {
      "field": "application",
      "description": "Application not stated — inferred precision_measurement from Libbrecht-Hall reference",
      "severity": "WARNING"
    }
  ]
}
```

---

## Migration Path from v1 to v2

The v1 `explicit_constraints` list is preserved in v2 for backward compatibility. Downstream modules that read v1 format continue to work. New modules read the typed fields. The intent parser produces both simultaneously during the transition period.

The parser system prompt must be updated to extract typed values wherever possible:
- "100mA current range" → `performance.output_current_ma = 100.0`
- "single dc input" → `electrical.supply_topology = "single_dc"`
- "ultra low noise" → `performance.noise.raw_text = "ultra low noise"` (quantification deferred to Stage 2)
- "potentiometer" → `performance.adjustability = "potentiometer"`
