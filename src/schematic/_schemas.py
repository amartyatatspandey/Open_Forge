"""Schematic synthesis schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.nir import NetlistEntry, PinRef, ReviewFlag


class FunctionalBlock(BaseModel):
    name: str
    refs: list[str]
    block_type: Literal["power", "digital", "RF", "analog", "passive", "mixed"]
    isolation_required: bool = False


class ERCViolation(BaseModel):
    severity: Literal["CRITICAL", "WARNING"]
    rule_name: str
    affected_refs: list[str]
    message: str


class ERCResult(BaseModel):
    passed: bool
    violations: list[ERCViolation]
    rules_checked: int


class SchematicGraph(BaseModel):
    netlist: list[NetlistEntry]
    blocks: list[FunctionalBlock]
    erc_result: ERCResult
    synthesis_confidence: float = Field(ge=0.0, le=1.0)
    unresolved_pins: list[PinRef]
    review_flags: list[ReviewFlag]
