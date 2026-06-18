"""Layout specification schemas."""

from __future__ import annotations

from pydantic import BaseModel

from src.schemas.nir import BoardSpec, ComponentGroup, PlacementConstraint, RoutingHint

# Re-export NIR placement constraint type for LayoutSpec consumers.
NIRConstraint = PlacementConstraint


class LayoutSpec(BaseModel):
    placement_constraints: list[NIRConstraint]
    component_groups: list[ComponentGroup]
    routing_hints: list[RoutingHint]
    board_spec: BoardSpec
