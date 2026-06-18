"""Functional block to component group conversion."""

from __future__ import annotations

from src.schemas.nir import ComponentGroup
from src.schematic._schemas import FunctionalBlock


def build_groups(blocks: list[FunctionalBlock]) -> list[ComponentGroup]:
    """Convert FunctionalBlock → ComponentGroup (NIR type)."""
    return [
        ComponentGroup(
            name=block.name,
            refs=block.refs,
            keep_together=True,
            isolation_required=block.isolation_required,
        )
        for block in blocks
    ]
