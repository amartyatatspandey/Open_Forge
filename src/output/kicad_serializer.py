"""NIR → KiCad files serializer via KiCad MCP server."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.config import Config
from src.nir.migrations import check_version
from src.output.kicad_footprint_map import resolve_kicad_footprint
from src.output.kicad_symbol_map import resolve_kicad_symbol
from src.schemas.nir import NIR

logger = logging.getLogger(__name__)


class KiCadMCPError(Exception):
    pass


class KiCadMCPClient:
    """
    Wraps KiCad MCP server calls.
    In production: makes HTTP calls to running KiCad MCP server.
    In tests: can be replaced with MockKiCadMCPClient.
    """

    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url

    def call(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        """POST to MCP server. Raises KiCadMCPError on failure."""
        import requests  # type: ignore[import-untyped]

        response = requests.post(
            f"{self.base_url}/tools/{tool}",
            json=params,
            timeout=30,
        )
        if response.status_code != 200:
            raise KiCadMCPError(f"MCP tool '{tool}' failed: {response.text}")
        result: dict[str, Any] = response.json()
        return result


class MockKiCadMCPClient:
    """In-memory MCP client for tests and validation gates."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool, params))
        if tool == "run_erc":
            return {"passed": True, "violations": []}
        if tool == "run_drc":
            return {"passed": True, "violations": []}
        return {}


class KiCadOutput(BaseModel):
    schematic_path: Optional[Path] = None
    pcb_path: Optional[Path] = None
    gerber_dir: Optional[Path] = None
    bom_path: Optional[Path] = None
    erc_passed: Optional[bool] = None
    drc_passed: Optional[bool] = None
    erc_violations: list[str] = Field(default_factory=list)
    drc_violations: list[str] = Field(default_factory=list)
    success: bool = False
    error: Optional[str] = None


def _compute_initial_positions(nir: NIR) -> dict[str, dict[str, Any]]:
    """
    Assign rough initial (x, y) positions based on component groups.
    Groups are placed in grid regions. Within each group,
    components are placed in a row with 5mm spacing.
    Returns: {ref: {"x": float, "y": float, "layer": str, "rotation": int}}
    """
    positions: dict[str, dict[str, Any]] = {}
    group_origin_x = 0.0
    for group in nir.component_groups:
        y = 0.0
        for i, ref in enumerate(group.refs):
            positions[ref] = {
                "x": group_origin_x + (i * 5.0),
                "y": y,
                "layer": "top",
                "rotation": 0,
            }
        group_origin_x += (len(group.refs) + 2) * 5.0

    ungrouped = [c.ref for c in nir.components if c.ref not in positions]
    for i, ref in enumerate(ungrouped):
        positions[ref] = {
            "x": group_origin_x + (i * 5.0),
            "y": 30.0,
            "layer": "top",
            "rotation": 0,
        }
    return positions


def serialize_to_kicad(
    nir: NIR,
    output_dir: Path,
    config: Config,
    mcp_client: KiCadMCPClient | MockKiCadMCPClient | None = None,
) -> KiCadOutput:
    """
    Serialize NIR to KiCad files via KiCad MCP server.
    mcp_client can be injected for testing (pass MockKiCadMCPClient).
    Never raises — returns KiCadOutput with error field on failure.

    Raises ValueError if NIR schema version does not match the serializer.
    """
    check_version(nir)

    client = mcp_client or KiCadMCPClient(config.kicad_mcp_url)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        client.call("create_schematic", {"name": nir.design_id})

        for comp in nir.components:
            symbol = resolve_kicad_symbol(comp.component_id, comp.component_type)
            footprint = resolve_kicad_footprint(comp.footprint)
            client.call(
                "add_symbol",
                {
                    "reference": comp.ref,
                    "library": symbol.library,
                    "symbol": symbol.symbol,
                    "value": comp.value or comp.component_id,
                    "footprint": footprint,
                },
            )

        power_nets = [n for n in nir.netlist if n.net_type == "power"]
        for net in power_nets:
            client.call("add_power_symbol", {"net_name": net.net_name})

        for net in nir.netlist:
            pins = net.connections
            for i in range(len(pins) - 1):
                client.call(
                    "add_wire",
                    {
                        "net": net.net_name,
                        "from_component": pins[i].ref,
                        "from_pin": pins[i].pin_name,
                        "to_component": pins[i + 1].ref,
                        "to_pin": pins[i + 1].pin_name,
                    },
                )

        for net in nir.netlist:
            if len(net.connections) > 2:
                for pin in net.connections:
                    client.call(
                        "add_net_label",
                        {
                            "net_name": net.net_name,
                            "component": pin.ref,
                            "pin": pin.pin_name,
                        },
                    )

        erc_result = client.call("run_erc", {})

        client.call(
            "create_pcb",
            {
                "name": nir.design_id,
                "layers": nir.board_spec.layers,
            },
        )

        positions = _compute_initial_positions(nir)
        for comp in nir.components:
            pos = positions.get(
                comp.ref,
                {"x": 0, "y": 0, "layer": "top", "rotation": 0},
            )
            client.call(
                "place_footprint",
                {
                    "reference": comp.ref,
                    "x": pos["x"],
                    "y": pos["y"],
                    "layer": pos["layer"],
                    "rotation": pos["rotation"],
                },
            )

        for hint in nir.routing_hints:
            if hint.hint_type == "impedance_controlled":
                client.call(
                    "set_net_class",
                    {
                        "nets": hint.nets,
                        "trace_width": hint.value,
                        "clearance": nir.board_spec.min_clearance_mm,
                    },
                )
            elif hint.hint_type == "differential_pair":
                client.call(
                    "add_differential_pair_rule",
                    {"nets": hint.nets},
                )

        keepouts = [
            c for c in nir.placement_constraints if c.constraint_type == "keepout"
        ]
        for keepout in keepouts:
            client.call(
                "add_keepout_zone",
                {
                    "reference": keepout.ref,
                    "clearance_mm": keepout.min_distance_mm or 1.0,
                },
            )

        drc_result = client.call("run_drc", {})

        gerber_dir = output_dir / "gerbers"
        sch_path = output_dir / f"{nir.design_id}.kicad_sch"
        pcb_path = output_dir / f"{nir.design_id}.kicad_pcb"
        bom_path = output_dir / "bom.csv"
        client.call("export_gerbers", {"output_dir": str(gerber_dir)})
        client.call("export_bom", {"output_path": str(bom_path), "format": "csv"})
        client.call(
            "save_all",
            {
                "schematic_path": str(sch_path),
                "pcb_path": str(pcb_path),
            },
        )

        return KiCadOutput(
            schematic_path=sch_path,
            pcb_path=pcb_path,
            gerber_dir=gerber_dir,
            bom_path=bom_path,
            erc_passed=erc_result.get("passed", False),
            drc_passed=drc_result.get("passed", False),
            erc_violations=erc_result.get("violations", []),
            drc_violations=drc_result.get("violations", []),
            success=True,
        )

    except KiCadMCPError as exc:
        logger.error("KiCad MCP error: %s", exc)
        return KiCadOutput(success=False, error=str(exc))
    except Exception as exc:
        logger.error("KiCad serialization failed: %s", exc)
        return KiCadOutput(success=False, error=f"Unexpected: {exc}")
