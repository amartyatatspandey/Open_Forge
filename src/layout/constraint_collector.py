"""Placement constraint collection from Phase 5 datasheets and KG-4 rules."""

from __future__ import annotations

import logging
from typing import Literal, cast

from src.schemas.datasheet import ComponentDatasheet, PlacementConstraint as DSConstraint
from src.schemas.kg import DesignSubgraph, KGNode
from src.schemas.nir import PlacementConstraint as NIRConstraint
from src.schematic._schemas import SchematicGraph

logger = logging.getLogger(__name__)

_VALID_CONSTRAINT_TYPES = frozenset({
    "proximity", "keepout", "layer", "orientation", "group"
})
_VALID_RELATIVE_TYPES = frozenset({"component", "pin", "board_edge"})
_VALID_LAYERS = frozenset({"top", "bottom", "any"})


def _normalize_constraint_type(value: str) -> Literal[
    "proximity", "keepout", "layer", "orientation", "group"
]:
    lowered = value.lower()
    if lowered in _VALID_CONSTRAINT_TYPES:
        return cast(
            Literal["proximity", "keepout", "layer", "orientation", "group"],
            lowered,
        )
    return "proximity"


def _normalize_relative_type(value: str) -> Literal["component", "pin", "board_edge"]:
    lowered = value.lower()
    if lowered in _VALID_RELATIVE_TYPES:
        return cast(Literal["component", "pin", "board_edge"], lowered)
    return "component"


def _normalize_layer(value: str | None) -> Literal["top", "bottom", "any"] | None:
    if value is None:
        return None
    lowered = value.lower()
    if lowered in _VALID_LAYERS:
        return cast(Literal["top", "bottom", "any"], lowered)
    return "any"


def _ds_to_nir(constraint: DSConstraint, source: str) -> NIRConstraint:
    return NIRConstraint(
        ref=constraint.subject,
        constraint_type=_normalize_constraint_type(constraint.constraint_type),
        relative_to=constraint.relative_to,
        relative_to_type=_normalize_relative_type(constraint.relative_to_type),
        max_distance_mm=constraint.max_distance_mm,
        min_distance_mm=constraint.min_distance_mm,
        layer=_normalize_layer(constraint.layer),
        hard=constraint.hard,
        source=source,
        confidence=constraint.confidence,
    )


def _kg_node_to_nir(node: KGNode) -> NIRConstraint:
    props = node.properties
    return NIRConstraint(
        ref=str(props.get("subject", node.label)),
        constraint_type=_normalize_constraint_type(str(props.get("constraint_type", "proximity"))),
        relative_to=str(props.get("relative_to", "")),
        relative_to_type=_normalize_relative_type(str(props.get("relative_to_type", "component"))),
        max_distance_mm=props.get("max_distance_mm"),
        min_distance_mm=props.get("min_distance_mm"),
        layer=_normalize_layer(props.get("layer")),
        hard=bool(props.get("hard", True)),
        source=node.source,
        confidence=node.confidence,
    )


def _constraint_key(constraint: NIRConstraint) -> tuple[str, str]:
    return (constraint.ref, constraint.relative_to)


def collect_constraints(
    schematic: SchematicGraph,
    datasheets: list[ComponentDatasheet],
    subgraph: DesignSubgraph,
) -> list[NIRConstraint]:
    """Collect placement constraints from Phase 5 datasheets and KG-4 rules."""
    _ = schematic

    phase5_constraints: list[NIRConstraint] = []
    phase5_keys: set[tuple[str, str]] = set()

    for datasheet in datasheets:
        source = f"phase5:{datasheet.component_id}"
        for ds_constraint in datasheet.layout_constraints:
            nir_constraint = _ds_to_nir(ds_constraint, source)
            phase5_constraints.append(nir_constraint)
            phase5_keys.add(_constraint_key(nir_constraint))

    merged: list[NIRConstraint] = list(phase5_constraints)

    for rule_node in subgraph.placement_rules:
        kg_constraint = _kg_node_to_nir(rule_node)
        key = _constraint_key(kg_constraint)
        if key in phase5_keys:
            logger.debug(
                "Discarding KG-4 constraint for %s — Phase 5 constraint takes priority",
                key,
            )
            continue
        merged.append(kg_constraint)

    return merged
