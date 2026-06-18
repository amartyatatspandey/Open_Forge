#!/usr/bin/env python3
"""Team D Gate - Synthesis pipeline validation checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

results: list[tuple[int, str, bool, str]] = []


def check(num: int, name: str, passed: bool, error: str = "") -> None:
    results.append((num, name, passed, error))
    status = "PASS" if passed else "FAIL"
    print(f"CHECK {num} — {name}: {status}")
    if error:
        print(f"  Error: {error}")


print("=" * 60)
print("TEAM D GATE - Synthesis Pipeline")
print("=" * 60)

from src.config import get_config

config = get_config()

# CHECK 1 — All Team D modules import without error
print("\n" + "-" * 60)
try:
    from src.schematic import synthesize_schematic
    from src.schematic._schemas import SchematicGraph
    from src.layout import generate_layout_spec, LayoutSpec
    from src.layout.board_spec_selector import select_board_spec
    from src.nir import build_nir
    from src.nir.validator import validate_nir
    from src.schematic.net_assigner import assign_power_nets
    from src.schematic._ref_mapper import build_ref_map
    from src.synthesis.pipeline import run_synthesis_pipeline

    check(1, "All Team D modules import without error", True)
except ImportError as e:
    check(1, "All Team D modules import without error", False, str(e))

# CHECK 2 — synthesize_schematic returns SchematicGraph for minimal BOM
print("\n" + "-" * 60)
try:
    from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod
    from src.schemas.intent import (
        BOMEntry,
        DesignMethodology,
        IntentDict,
        ValidatedBOM,
    )
    from src.schemas.kg import DesignSubgraph
    from src.schematic import synthesize_schematic
    from src.schematic._schemas import SchematicGraph

    intent = IntentDict(
        goal="test",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt="test",
    )
    bom = ValidatedBOM(
        design_id="test-design",
        intent=intent,
        components=[],
        total_confidence=0.0,
        review_required=False,
        created_at="2026-01-01T00:00:00Z",
    )
    subgraph = DesignSubgraph(
        component_types=[],
        component_instances=[],
        design_rules=[],
        placement_rules=[],
        routing_hints=[],
        design_methodology="standard_SMD",
        path_confidences={},
        query_depth=0,
    )

    schematic = synthesize_schematic(bom, [], subgraph, config)
    if isinstance(schematic, SchematicGraph):
        check(2, "synthesize_schematic returns SchematicGraph for minimal BOM", True)
    else:
        check(
            2,
            "synthesize_schematic returns SchematicGraph for minimal BOM",
            False,
            f"expected SchematicGraph, got {type(schematic).__name__}",
        )
except Exception as e:
    check(
        2,
        "synthesize_schematic returns SchematicGraph for minimal BOM",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 3 — power net assignment creates VCC and GND nets
print("\n" + "-" * 60)
try:
    from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod, PinDefinition
    from src.schemas.intent import BOMEntry, DesignMethodology, IntentDict, ValidatedBOM
    from src.schematic._ref_mapper import build_ref_map
    from src.schematic.net_assigner import assign_power_nets

    ds = ComponentDatasheet(
        component_id="IC1",
        manufacturer="TI",
        description="Test IC",
        package="SOIC-8",
        source_pdf_hash="abc",
        extraction_method=ExtractionMethod.P1_VECTOR,
        extraction_confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
        pins=[
            PinDefinition(
                pin_number="1",
                raw_name="VCC",
                normalized_function="POWER_POSITIVE",
                normalization_confidence=0.95,
                pin_type="power",
            ),
            PinDefinition(
                pin_number="2",
                raw_name="GND",
                normalized_function="POWER_GROUND",
                normalization_confidence=0.95,
                pin_type="ground",
            ),
        ],
    )
    intent = IntentDict(
        goal="test",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt="test",
    )
    bom = ValidatedBOM(
        design_id="test-design",
        intent=intent,
        components=[
            BOMEntry(
                ref="U1",
                component_type="regulator",
                specific_part="IC1",
                justification="test",
                source="test",
                confidence=0.9,
            )
        ],
        total_confidence=0.9,
        review_required=False,
        created_at="2026-01-01T00:00:00Z",
    )
    ref_map = build_ref_map(bom, [ds])
    nets = assign_power_nets(ref_map)
    net_names = {net.net_name for net in nets}

    errors = []
    if "VCC" not in net_names:
        errors.append("VCC net missing")
    if "GND" not in net_names:
        errors.append("GND net missing")

    if errors:
        check(3, "power net assignment creates VCC and GND nets", False, "; ".join(errors))
    else:
        check(3, "power net assignment creates VCC and GND nets", True)
except Exception as e:
    check(3, "power net assignment creates VCC and GND nets", False, f"{type(e).__name__}: {e}")

# CHECK 4 — layout engine selects correct board spec per methodology
print("\n" + "-" * 60)
try:
    from src.layout.board_spec_selector import select_board_spec

    rf_spec = select_board_spec("RF_highfreq")
    smd_spec = select_board_spec("standard_SMD")

    errors = []
    if rf_spec.material != "Rogers_4003C":
        errors.append(f"RF_highfreq material={rf_spec.material!r}")
    if smd_spec.material != "FR4":
        errors.append(f"standard_SMD material={smd_spec.material!r}")

    if errors:
        check(4, "layout engine selects correct board spec per methodology", False, "; ".join(errors))
    else:
        check(4, "layout engine selects correct board spec per methodology", True)
except Exception as e:
    check(
        4,
        "layout engine selects correct board spec per methodology",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 5 — validate_nir adds CRITICAL flag for unknown netlist ref
print("\n" + "-" * 60)
try:
    from src.nir.validator import validate_nir
    from src.schemas.nir import BoardSpec, ComponentRef, NIR, NetlistEntry, PinRef

    nir = NIR(
        design_id="design-001",
        prompt="test",
        design_methodology="standard_SMD",
        components=[
            ComponentRef(
                ref="U1",
                component_id="IC1",
                component_type="regulator",
                footprint="SOIC-8",
                datasheet_confidence=0.9,
                justification="test",
            )
        ],
        netlist=[
            NetlistEntry(
                net_name="SIG",
                net_type="signal",
                connections=[PinRef(ref="U99", pin_name="OUT", pin_number="1")],
                source_rule="test",
                net_confidence=0.8,
            )
        ],
        placement_constraints=[],
        board_spec=BoardSpec(
            layers=2,
            material="FR4",
            thickness_mm=1.6,
            min_trace_width_mm=0.15,
            min_clearance_mm=0.15,
        ),
        created_at="2026-01-01T00:00:00Z",
    )

    validated = validate_nir(nir)
    critical = [f for f in validated.review_flags if f.severity == "CRITICAL"]
    if any("unknown ref U99" in f.reason for f in critical):
        check(5, "validate_nir adds CRITICAL flag for unknown netlist ref", True)
    else:
        check(
            5,
            "validate_nir adds CRITICAL flag for unknown netlist ref",
            False,
            "no CRITICAL flag for unknown ref U99",
        )
except Exception as e:
    check(
        5,
        "validate_nir adds CRITICAL flag for unknown netlist ref",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 6 — validate_nir never mutates input NIR
print("\n" + "-" * 60)
try:
    from src.nir.validator import validate_nir
    from src.schemas.nir import BoardSpec, ComponentRef, NIR, NetlistEntry, PinRef

    nir = NIR(
        design_id="design-001",
        prompt="test",
        design_methodology="standard_SMD",
        components=[
            ComponentRef(
                ref="U1",
                component_id="IC1",
                component_type="regulator",
                footprint="SOIC-8",
                datasheet_confidence=0.9,
                justification="test",
            )
        ],
        netlist=[
            NetlistEntry(
                net_name="SIG",
                net_type="signal",
                connections=[PinRef(ref="U99", pin_name="OUT", pin_number="1")],
                source_rule="test",
                net_confidence=0.8,
            )
        ],
        placement_constraints=[],
        board_spec=BoardSpec(
            layers=2,
            material="FR4",
            thickness_mm=1.6,
            min_trace_width_mm=0.15,
            min_clearance_mm=0.15,
        ),
        created_at="2026-01-01T00:00:00Z",
    )
    original_count = len(nir.review_flags)

    validated = validate_nir(nir)

    errors = []
    if validated is nir:
        errors.append("returned same object as input")
    if len(nir.review_flags) != original_count:
        errors.append("input review_flags mutated")

    if errors:
        check(6, "validate_nir never mutates input NIR", False, "; ".join(errors))
    else:
        check(6, "validate_nir never mutates input NIR", True)
except Exception as e:
    check(6, "validate_nir never mutates input NIR", False, f"{type(e).__name__}: {e}")

# CHECK 7 — run_synthesis_pipeline returns NIR (never raises)
print("\n" + "-" * 60)
try:
    from src.schemas.intent import DesignMethodology, IntentDict, ValidatedBOM
    from src.schemas.kg import DesignSubgraph
    from src.schemas.nir import NIR
    from src.synthesis.pipeline import run_synthesis_pipeline

    intent = IntentDict(
        goal="test",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt="test",
    )
    bom = ValidatedBOM(
        design_id="pipeline-test",
        intent=intent,
        components=[],
        total_confidence=0.0,
        review_required=False,
        created_at="2026-01-01T00:00:00Z",
    )
    subgraph = DesignSubgraph(
        component_types=[],
        component_instances=[],
        design_rules=[],
        placement_rules=[],
        routing_hints=[],
        design_methodology="standard_SMD",
        path_confidences={},
        query_depth=0,
    )

    result = run_synthesis_pipeline(bom, [], subgraph, config)

    if isinstance(result, NIR):
        check(7, "run_synthesis_pipeline returns NIR (never raises)", True)
    else:
        check(
            7,
            "run_synthesis_pipeline returns NIR (never raises)",
            False,
            f"expected NIR, got {type(result).__name__}",
        )
except Exception as e:
    check(
        7,
        "run_synthesis_pipeline returns NIR (never raises)",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 8 — mypy on Team D packages
print("\n" + "-" * 60)
try:
    mypy_result = subprocess.run(
        [
            "mypy",
            "src/schematic/",
            "src/layout/",
            "src/nir/",
            "src/synthesis/",
            "--ignore-missing-imports",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    output = (mypy_result.stdout + mypy_result.stderr).strip()
    error_lines = [
        line for line in output.split("\n") if line.strip() and "error:" in line.lower()
    ]

    if mypy_result.returncode != 0 or error_lines:
        check(
            8,
            "mypy on src/schematic/ src/layout/ src/nir/ src/synthesis/",
            False,
            "\n  ".join([""] + error_lines[:25]),
        )
    else:
        check(8, "mypy on src/schematic/ src/layout/ src/nir/ src/synthesis/", True)
except Exception as e:
    check(
        8,
        "mypy on src/schematic/ src/layout/ src/nir/ src/synthesis/",
        False,
        f"{type(e).__name__}: {e}",
    )

print("\n" + "=" * 60)
passed = sum(1 for _, _, p, _ in results if p)
total = len(results)

if passed == total:
    print(f"Team D: PASS ({passed}/{total} checks passed)")
else:
    print(f"Team D: FAIL ({passed}/{total} checks passed)")
    print("\nFailed checks:")
    for num, name, p, error in results:
        if not p:
            print(f"  CHECK {num} — {name}")
            if error:
                print(f"    {error}")

print("=" * 60)
sys.exit(0 if passed == total else 1)
