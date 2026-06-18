"""NIR schema v1.0 — Team D owns writes, Team E owns reads.

Schema version must be bumped on any breaking change. Both KiCad and tscircuit
serializers depend on this.

This module defines the Native Intermediate Representation (NIR) schema for
PCB design intent. NIR serves as the canonical interchange format between:
- Design capture (schematic/ intent parsing)
- Layout automation (placement and routing)
- Export generators (KiCad, tscircuit, etc.)

NIR contains:
- Component references with provenance and confidence
- Netlist with typed connections and routing requirements
- Placement constraints (proximity, keepout, layer, orientation)
- Routing hints (impedance control, length matching, differential pairs)
- Component groups (for clustering and isolation)
- Board specifications (stackup, materials, design rules)
- Review flags for human-in-the-loop validation

Version History:
- 1.0: Initial schema with component groups, placement constraints, routing hints
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ComponentRef(BaseModel):
    """Reference to a component instance in the design.

    Represents a placed or to-be-placed component with its type,
    footprint, value, and provenance metadata from datasheet extraction.

    Attributes:
        ref: Reference designator (e.g., "U1", "C3", "R12")
        component_id: Manufacturer part number (e.g., "TPS62933DRLR")
        component_type: Normalized type (e.g., "regulator", "capacitor", "resistor")
        footprint: IPC-7351 normalized footprint name (same constraint as ComponentDatasheet.package)
        value: Component value for passives (e.g., "10uF", "1kΩ") or None for ICs
        manufacturer: Component manufacturer name (e.g., "Texas Instruments")
        datasheet_confidence: Confidence in component identification [0.0, 1.0]
        justification: Design rationale for component selection
    """

    ref: str = Field(description="Reference designator (e.g., 'U1', 'C3', 'R12')")
    component_id: str = Field(
        description="Manufacturer part number (e.g., 'TPS62933DRLR')"
    )
    component_type: str = Field(
        description="Normalized component type (e.g., 'regulator', 'capacitor')"
    )
    footprint: str = Field(
        description="IPC-7351 normalized footprint name. Must be one of: "
        "SOT-23-5, SOT-23-3, SOIC-8, SOIC-16, QFN-16, 0402, 0603, 0805, "
        "DIP-8, TO-220, TSSOP-8, etc."
    )
    value: Optional[str] = Field(
        default=None,
        description="Component value for passives (e.g., '10uF', '1kΩ') or None for ICs",
    )
    manufacturer: str = Field(
        default="", description="Component manufacturer name"
    )
    datasheet_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in component identification from datasheet extraction",
    )
    justification: str = Field(
        description="Design rationale for why this component was selected"
    )


class PinRef(BaseModel):
    """Reference to a specific pin on a component.

    Used in netlist connections to establish electrical connectivity
    between component pins.

    Attributes:
        ref: Component reference designator (matches ComponentRef.ref)
        pin_name: Normalized pin name (e.g., "VIN", "GND", "VOUT")
        pin_number: Physical pin number on the package (e.g., "1", "5", "EP")
    """

    ref: str = Field(
        description="Component reference designator (matches ComponentRef.ref)"
    )
    pin_name: str = Field(
        description="Normalized pin name (e.g., 'VIN', 'GND', 'VOUT')"
    )
    pin_number: str = Field(
        description="Physical pin number on the package (e.g., '1', '5', 'EP')"
    )


class NetlistEntry(BaseModel):
    """Single net entry in the design netlist.

    Represents an electrical network connecting multiple pins with
    a specific type classification and routing requirements.

    Attributes:
        net_name: Unique net identifier (e.g., "VCC_3V3", "GND", "USB_DP")
        net_type: Classification for routing rules (power, signal, RF, etc.)
        connections: List of pin references connected to this net
        source_rule: Reference to the design rule that created this net
        net_confidence: Aggregate confidence in net correctness [0.0, 1.0] — BS-3 fix
    """

    net_name: str = Field(description="Unique net identifier (e.g., 'VCC_3V3')")
    net_type: Literal[
        "power", "signal", "RF", "clock", "differential", "analog"
    ] = Field(description="Classification for routing rule selection")
    connections: list[PinRef] = Field(
        description="List of pin references connected to this net"
    )
    source_rule: str = Field(
        description="Reference to the design rule that created this net"
    )
    net_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Aggregate confidence in net correctness [0.0, 1.0] — BS-3 fix",
    )


class PlacementConstraint(BaseModel):
    """Physical placement constraint for a component.

    Defines geometric or topological constraints on component placement,
    such as proximity requirements, keepout zones, layer assignments,
    or orientation rules.

    Attributes:
        ref: Component reference designator this constraint applies to
        constraint_type: Type of constraint (proximity, keepout, layer, orientation, group)
        relative_to: Target reference for relative constraints
        relative_to_type: Type of the relative_to target — BS-2 fix
        max_distance_mm: Maximum allowed distance for proximity constraints
        min_distance_mm: Minimum required distance for keepout constraints
        layer: Layer restriction (top, bottom, any)
        hard: True if mandatory, False if recommendation
        source: Origin of this constraint (rule_id or document reference)
        confidence: Confidence in constraint validity [0.0, 1.0]
    """

    ref: str = Field(
        description="Component reference designator this constraint applies to"
    )
    constraint_type: Literal[
        "proximity", "keepout", "layer", "orientation", "group"
    ] = Field(description="Type of placement constraint")
    relative_to: str = Field(
        description="Target reference for relative constraints"
    )
    relative_to_type: Literal[
        "component", "pin", "board_edge"
    ] = Field(description="Type of the relative_to target: component, pin, or board_edge — BS-2 fix")
    max_distance_mm: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Maximum allowed distance for proximity constraints",
    )
    min_distance_mm: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Minimum required distance for keepout constraints",
    )
    layer: Optional[Literal["top", "bottom", "any"]] = Field(
        default=None, description="Layer restriction (top, bottom, any)"
    )
    hard: bool = Field(
        default=True, description="True if mandatory, False if recommendation"
    )
    source: str = Field(
        description="Origin of this constraint (rule_id or document reference)"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in constraint validity [0.0, 1.0]"
    )


class RoutingHint(BaseModel):
    """Routing guidance for specific nets or net classes.

    Provides high-level routing requirements that guide the auto-router
    or design rule checker. These are hints, not hard constraints.

    Attributes:
        nets: List of net names this hint applies to
        hint_type: Type of routing guidance (impedance, length, differential, etc.)
        value: Numeric value for the hint (impedance in ohms, length in mm, etc.)
        unit: Unit for the value (Ohm, mm, dB, etc.)
        note: Human-readable explanation of the routing requirement
    """

    nets: list[str] = Field(
        description="List of net names this hint applies to"
    )
    hint_type: Literal[
        "impedance_controlled",
        "length_matched",
        "differential_pair",
        "min_width",
        "max_length",
        "isolation",
    ] = Field(description="Type of routing guidance")
    value: Optional[float] = Field(
        default=None, description="Numeric value for the hint"
    )
    unit: Optional[str] = Field(
        default=None, description="Unit for the value (Ohm, mm, dB, etc.)"
    )
    note: str = Field(
        description="Human-readable explanation of the routing requirement"
    )


class ComponentGroup(BaseModel):
    """Logical grouping of components for placement clustering.

    Defines a named collection of components that should be kept together
    or isolated from other groups based on design requirements.

    Attributes:
        name: Group identifier (e.g., "Buck_Regulator_Stage", "ADC_Analog_Frontend")
        refs: List of component reference designators in this group
        keep_together: True if components should be placed in proximity
        isolation_required: True if group must be isolated from others
    """

    name: str = Field(
        description="Group identifier (e.g., 'Buck_Regulator_Stage')"
    )
    refs: list[str] = Field(
        description="List of component reference designators in this group"
    )
    keep_together: bool = Field(
        default=True,
        description="True if components should be placed in proximity",
    )
    isolation_required: bool = Field(
        default=False,
        description="True if group must be isolated from other components",
    )


class BoardSpec(BaseModel):
    """Physical board specifications and manufacturing constraints.

    Defines the PCB stackup, materials, and design rule constraints
    that govern all placement and routing decisions.

    Attributes:
        layers: Number of copper layers (1, 2, 4, or 6)
        material: Base material (e.g., "FR-4", "Rogers RO4350B")
        thickness_mm: Total board thickness in millimeters
        copper_weight_oz: Copper weight in ounces per square foot (default 1.0 oz)
        min_trace_width_mm: Minimum trace width per design rules
        min_clearance_mm: Minimum clearance between copper features
        min_via_drill_mm: Minimum via drill diameter
        surface_finish: Surface finish type (HASL, ENIG, OSP, etc.)
    """

    layers: Literal[1, 2, 4, 6] = Field(
        description="Number of copper layers (1, 2, 4, or 6)"
    )
    material: str = Field(
        description="Base material (e.g., 'FR-4', 'Rogers RO4350B')"
    )
    thickness_mm: float = Field(
        gt=0.0, description="Total board thickness in millimeters"
    )
    copper_weight_oz: float = Field(
        default=1.0, gt=0.0, description="Copper weight in oz/ft² (default 1.0 oz)"
    )
    min_trace_width_mm: float = Field(
        gt=0.0, description="Minimum trace width per design rules"
    )
    min_clearance_mm: float = Field(
        gt=0.0, description="Minimum clearance between copper features"
    )
    min_via_drill_mm: float = Field(
        default=0.3, gt=0.0, description="Minimum via drill diameter in mm (default 0.3)"
    )
    surface_finish: str = Field(
        default="HASL", description="Surface finish type (HASL, ENIG, OSP, etc.)"
    )


class ReviewFlag(BaseModel):
    """Flag for human review of design decisions or extraction results.

    Represents an issue or concern that requires human attention before
    the design can proceed to layout or manufacturing.

    Attributes:
        item_ref: Reference to the item needing review (component ref, net name, etc.)
        reason: Human-readable explanation of the issue
        severity: Issue classification (CRITICAL blocks progress, WARNING is advisory)
        stage: Pipeline stage where flag was raised (extraction, validation, etc.)
        suggested_resolution: Optional guidance for resolving the issue
    """

    item_ref: str = Field(
        description="Reference to the item needing review (component ref, net name, etc.)"
    )
    reason: str = Field(description="Human-readable explanation of the issue")
    severity: Literal["CRITICAL", "WARNING", "INFO"] = Field(
        description="Issue classification (CRITICAL blocks progress, WARNING is advisory)"
    )
    stage: str = Field(
        description="Pipeline stage where flag was raised (extraction, validation, etc.)"
    )
    suggested_resolution: Optional[str] = Field(
        default=None, description="Optional guidance for resolving the issue"
    )


class NIR(BaseModel):
    """Native Intermediate Representation — canonical PCB design intent.

    Root container for all design data flowing from design capture
    through layout automation to export generators. NIR is the
    interchange format between Team D (design capture) and Team E
    (layout automation/export).

    Attributes:
        schema_version: NIR schema version for compatibility checking
        design_id: Unique identifier for this design
        prompt: Original user intent/design goal that created this NIR
        design_methodology: Reference to design methodology/recipe used
        components: List of component instances in the design
        netlist: Electrical connectivity graph
        placement_constraints: Geometric/topological placement rules
        component_groups: Logical component clusters
        routing_hints: High-level routing guidance
        board_spec: Physical board and manufacturing constraints
        bom: Bill of materials (flexible dict for tool-specific data)
        justifications: Mapping of refs to design rationales
        source_citations: Provenance mapping (ref → source document)
        confidence_scores: Per-component confidence from extraction
        net_confidence: Per-net confidence from netlist extraction — BS-3
        review_flags: Issues requiring human attention
        extraction_metadata: Tool/version info from extraction pipeline
        created_at: ISO 8601 timestamp of NIR creation
        pipeline_version: Version of pipeline that generated this NIR
    """

    schema_version: str = Field(
        default="1.0", description="NIR schema version for compatibility"
    )
    design_id: str = Field(description="Unique identifier for this design")
    prompt: str = Field(
        description="Original user intent/design goal that created this NIR"
    )
    design_methodology: str = Field(
        description="Reference to design methodology/recipe used"
    )
    components: list[ComponentRef] = Field(
        description="List of component instances in the design"
    )
    netlist: list[NetlistEntry] = Field(
        description="Electrical connectivity graph"
    )
    placement_constraints: list[PlacementConstraint] = Field(
        description="Geometric/topological placement rules"
    )
    component_groups: list[ComponentGroup] = Field(
        default_factory=list, description="Logical component clusters"
    )
    routing_hints: list[RoutingHint] = Field(
        default_factory=list, description="High-level routing guidance"
    )
    board_spec: BoardSpec = Field(
        description="Physical board and manufacturing constraints"
    )
    bom: list[dict[str, Any]] = Field(
        default_factory=list, description="Bill of materials (tool-specific)"
    )
    justifications: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of component refs to design rationales",
    )
    source_citations: dict[str, str] = Field(
        default_factory=dict, description="Provenance (ref → source document)"
    )
    confidence_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Per-component confidence from datasheet extraction",
    )
    net_confidence: dict[str, float] = Field(
        default_factory=dict,
        description="Per-net confidence from netlist extraction — BS-3 fix",
    )
    review_flags: list[ReviewFlag] = Field(
        default_factory=list, description="Issues requiring human attention"
    )
    extraction_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Tool/version info from extraction"
    )
    created_at: str = Field(description="ISO 8601 timestamp of NIR creation")
    pipeline_version: str = Field(
        default="1.0",
        description="Version of pipeline that generated this NIR",
    )

    def get_component(self, ref: str) -> Optional[ComponentRef]:
        """Retrieve a component by its reference designator.

        Args:
            ref: Component reference designator (e.g., "U1", "C3")

        Returns:
            ComponentRef matching the ref, or None if not found.
        """
        return next((c for c in self.components if c.ref == ref), None)

    def get_net(self, net_name: str) -> Optional[NetlistEntry]:
        """Retrieve a net entry by its name.

        Args:
            net_name: Net identifier (e.g., "VCC_3V3", "GND")

        Returns:
            NetlistEntry matching the net_name, or None if not found.
        """
        return next((n for n in self.netlist if n.net_name == net_name), None)

    def critical_flags(self) -> list[ReviewFlag]:
        """Return only CRITICAL severity review flags.

        Returns:
            List of ReviewFlag objects with severity == "CRITICAL".
        """
        return [f for f in self.review_flags if f.severity == "CRITICAL"]

    def is_review_required(self) -> bool:
        """Check if any CRITICAL review flags exist.

        Returns:
            True if there are any CRITICAL flags requiring human review,
            False otherwise.
        """
        return len(self.critical_flags()) > 0


__all__ = [
    "ComponentRef",
    "PinRef",
    "NetlistEntry",
    "PlacementConstraint",
    "RoutingHint",
    "ComponentGroup",
    "BoardSpec",
    "ReviewFlag",
    "NIR",
]
