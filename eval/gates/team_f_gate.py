#!/usr/bin/env python3
"""Team F Gate - Schema validation checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Track results

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

results: list[tuple[int, str, bool, str]] = []


def check(num: int, name: str, passed: bool, error: str = "") -> None:
    """Record check result."""
    results.append((num, name, passed, error))
    status = "PASS" if passed else "FAIL"
    if error:
        print(f"CHECK {num} — {name}: {status}")
        print(f"  Error: {error}")
    else:
        print(f"CHECK {num} — {name}: {status}")


print("=" * 60)
print("TEAM F GATE - Schema Validation")
print("=" * 60)

# CHECK 1 — All schemas import without error
print("\n" + "-" * 60)
error_msg = ""
try:
    from src.schemas.datasheet import (
        ComponentDatasheet,
        PinDefinition,
        ElectricalParameter,
        AbsoluteMaxRating,
        PlacementConstraint,
        TableSectionType,
        ExtractionMethod,
        ExtractedValue,
    )
    from src.schemas.kg import (
        KGNode,
        KGEdge,
        KGNodeType,
        KGRelation,
        DesignSubgraph,
        ComponentSearchResult,
        EXTRACTION_METHOD_CONFIDENCE,
    )
    from src.schemas.nir import (
        NIR,
        ComponentRef,
        NetlistEntry,
        PinRef,
        RoutingHint,
        BoardSpec,
        ReviewFlag,
    )
    from src.schemas.intent import (
        IntentDict,
        ValidatedBOM,
        BOMEntry,
        DesignMethodology,
        FrequencySpec,
        AmbiguityFlag,
    )
    check(1, "All schemas import without error", True)
except Exception as e:
    error_msg = f"{type(e).__name__}: {e}"
    check(1, "All schemas import without error", False, error_msg)
    print("\nCannot proceed with checks 2-6 due to import failure.")
    print("=" * 60)
    print("Team F: FAIL (0/7 checks passed)")
    print("=" * 60)
    sys.exit(1)

# CHECK 2 — EXTRACTION_METHOD_CONFIDENCE covers every ExtractionMethod value
print("\n" + "-" * 60)
try:
    missing = [
        m.value for m in ExtractionMethod if m not in EXTRACTION_METHOD_CONFIDENCE
    ]
    if missing:
        check(
            2,
            "EXTRACTION_METHOD_CONFIDENCE covers all ExtractionMethod values",
            False,
            f"Missing values: {missing}",
        )
    else:
        check(
            2,
            "EXTRACTION_METHOD_CONFIDENCE covers all ExtractionMethod values",
            True,
        )
except Exception as e:
    check(
        2,
        "EXTRACTION_METHOD_CONFIDENCE covers all ExtractionMethod values",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 3 — Both PlacementConstraint classes have relative_to_type
print("\n" + "-" * 60)
try:
    DSPlacement = PlacementConstraint
    from src.schemas.nir import PlacementConstraint as NIRPlacement

    errors = []
    if "relative_to_type" not in DSPlacement.model_fields:
        errors.append("PlacementConstraint (datasheet) missing 'relative_to_type'")
    if "relative_to_type" not in NIRPlacement.model_fields:
        errors.append("PlacementConstraint (nir) missing 'relative_to_type'")

    if errors:
        check(
            3,
            "Both PlacementConstraint classes have relative_to_type",
            False,
            "; ".join(errors),
        )
    else:
        check(3, "Both PlacementConstraint classes have relative_to_type", True)
except Exception as e:
    check(
        3,
        "Both PlacementConstraint classes have relative_to_type",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 4 — NIR has net_confidence field
print("\n" + "-" * 60)
try:
    if "net_confidence" not in NIR.model_fields:
        check(
            4,
            "NIR has net_confidence field",
            False,
            "'net_confidence' not in NIR.model_fields",
        )
    else:
        check(4, "NIR has net_confidence field", True)
except Exception as e:
    check(4, "NIR has net_confidence field", False, f"{type(e).__name__}: {e}")

# CHECK 5 — DesignSubgraph has has_specific_parts() and min_path_confidence()
print("\n" + "-" * 60)
try:
    errors = []
    if not hasattr(DesignSubgraph, "has_specific_parts"):
        errors.append("DesignSubgraph missing 'has_specific_parts' method")
    if not hasattr(DesignSubgraph, "min_path_confidence"):
        errors.append("DesignSubgraph missing 'min_path_confidence' method")

    if errors:
        check(
            5,
            "DesignSubgraph has has_specific_parts() and min_path_confidence()",
            False,
            "; ".join(errors),
        )
    else:
        check(
            5,
            "DesignSubgraph has has_specific_parts() and min_path_confidence()",
            True,
        )
except Exception as e:
    check(
        5,
        "DesignSubgraph has has_specific_parts() and min_path_confidence()",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 6 — Basic instantiation round-trips to JSON without error
print("\n" + "-" * 60)
try:
    errors = []

    # Minimal valid objects for each schema class
    test_objects: list[tuple[str, Any]] = [
        ("ComponentDatasheet", None),  # Will create separately
        ("PinDefinition", None),
        ("ElectricalParameter", None),
        ("AbsoluteMaxRating", None),
        ("PlacementConstraint", None),
        ("TableSectionType", None),
        ("ExtractionMethod", None),
        ("KGNode", None),
        ("KGEdge", None),
        ("KGNodeType", None),
        ("KGRelation", None),
        ("DesignSubgraph", None),
        ("ComponentSearchResult", None),
        ("NIR", None),
        ("ComponentRef", None),
        ("NetlistEntry", None),
        ("RoutingHint", None),
        ("BoardSpec", None),
        ("ReviewFlag", None),
        ("IntentDict", None),
        ("ValidatedBOM", None),
        ("BOMEntry", None),
        ("DesignMethodology", None),
        ("FrequencySpec", None),
        ("AmbiguityFlag", None),
    ]

    # Instantiate and test
    sample_value = ExtractedValue(
        raw_text="3.3V",
        normalized_value=3.3,
        unit="V",
        typ_val=3.3,
        confidence=0.95,
    )

    try:
        # ComponentDatasheet
        obj = ComponentDatasheet(
            component_id="TEST123",
            manufacturer="TestCorp",
            description="Test component",
            package="SOT-23-5",
            source_pdf_hash="a1b2c3d4e5f6789012345678901234567890abcd",
            extraction_method=ExtractionMethod.MANUAL,
            extraction_confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"ComponentDatasheet: {e}")

    try:
        # PinDefinition
        obj = PinDefinition(
            pin_number="1",
            raw_name="VCC",
            pin_type="power",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"PinDefinition: {e}")

    try:
        # ElectricalParameter
        obj = ElectricalParameter(
            parameter_name="V_CC",
            symbol="V_CC",
            value=sample_value,
            section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
            source_page=1,
            source_table_index=0,
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"ElectricalParameter: {e}")

    try:
        # AbsoluteMaxRating
        obj = AbsoluteMaxRating(
            parameter_name="V_CC_ABS",
            value=sample_value,
            source_page=1,
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"AbsoluteMaxRating: {e}")

    try:
        # PlacementConstraint
        obj = PlacementConstraint(
            constraint_type="proximity",
            subject="U1.VIN",
            relative_to="C1",
            relative_to_type="component",
            min_distance_mm=0.5,
            source_sentence="Place capacitor near VIN",
            confidence=0.9,
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"PlacementConstraint: {e}")

    try:
        # TableSectionType - enum
        obj = TableSectionType.PINOUT
        json.dumps(obj.value)
    except Exception as e:
        errors.append(f"TableSectionType: {e}")

    try:
        # ExtractionMethod - enum
        obj = ExtractionMethod.MANUAL
        json.dumps(obj.value)
    except Exception as e:
        errors.append(f"ExtractionMethod: {e}")

    sample_kg_node = KGNode(
        id="test:1",
        node_type=KGNodeType.COMPONENT_TYPE,
        layer=1,
        label="test",
        properties={},
        source="test",
        confidence=0.9,
        extraction_method=ExtractionMethod.MANUAL,
        created_at="2026-01-01T00:00:00Z",
    )
    sample_board_spec = BoardSpec(
        layers=2,
        material="FR-4",
        thickness_mm=1.6,
        min_trace_width_mm=0.15,
        min_clearance_mm=0.15,
    )
    sample_intent = IntentDict(
        goal="test regulator",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="2-layer FR4",
        raw_prompt="Design a test circuit",
    )

    try:
        # KGNode
        sample_kg_node.model_dump_json()
    except Exception as e:
        errors.append(f"KGNode: {e}")

    try:
        # KGEdge
        obj = KGEdge(
            source_id="test:1",
            target_id="test:2",
            relation=KGRelation.REQUIRES,
            source_document="test.pdf",
            confidence=0.9,
            layer=3,
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"KGEdge: {e}")

    try:
        # KGNodeType - enum
        obj = KGNodeType.COMPONENT_TYPE
        json.dumps(obj.value)
    except Exception as e:
        errors.append(f"KGNodeType: {e}")

    try:
        # KGRelation - enum
        obj = KGRelation.REQUIRES
        json.dumps(obj.value)
    except Exception as e:
        errors.append(f"KGRelation: {e}")

    try:
        # DesignSubgraph
        obj = DesignSubgraph(
            component_types=[],
            component_instances=[],
            design_rules=[],
            placement_rules=[],
            routing_hints=[],
            design_methodology="test",
            path_confidences={},
            query_depth=0,
            query_metadata={},
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"DesignSubgraph: {e}")

    try:
        # ComponentSearchResult
        obj = ComponentSearchResult(
            node=sample_kg_node,
            similarity_score=0.9,
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"ComponentSearchResult: {e}")

    try:
        # NIR
        obj = NIR(
            design_id="test",
            prompt="test design",
            design_methodology="standard_SMD",
            components=[
                ComponentRef(
                    ref="U1",
                    component_id="TEST123",
                    component_type="regulator",
                    footprint="SOT-23-5",
                    datasheet_confidence=0.9,
                    justification="test component",
                )
            ],
            netlist=[
                NetlistEntry(
                    net_name="VCC",
                    net_type="power",
                    connections=[PinRef(ref="U1", pin_name="VIN", pin_number="1")],
                    source_rule="power_rule",
                    net_confidence=0.9,
                )
            ],
            placement_constraints=[],
            board_spec=sample_board_spec,
            created_at="2026-01-01T00:00:00Z",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"NIR: {e}")

    try:
        # ComponentRef
        obj = ComponentRef(
            ref="R1",
            component_id="TEST123",
            component_type="resistor",
            footprint="0805",
            value="1k",
            datasheet_confidence=0.9,
            justification="test resistor",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"ComponentRef: {e}")

    try:
        # NetlistEntry
        obj = NetlistEntry(
            net_name="VCC",
            net_type="power",
            connections=[PinRef(ref="U1", pin_name="VIN", pin_number="1")],
            source_rule="power_rule",
            net_confidence=0.9,
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"NetlistEntry: {e}")

    try:
        # RoutingHint
        obj = RoutingHint(
            nets=["VCC"],
            hint_type="min_width",
            note="Keep power trace short",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"RoutingHint: {e}")

    try:
        # BoardSpec
        sample_board_spec.model_dump_json()
    except Exception as e:
        errors.append(f"BoardSpec: {e}")

    try:
        # ReviewFlag
        obj = ReviewFlag(
            item_ref="U1",
            reason="test",
            severity="WARNING",
            stage="validation",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"ReviewFlag: {e}")

    try:
        # IntentDict
        sample_intent.model_dump_json()
    except Exception as e:
        errors.append(f"IntentDict: {e}")

    try:
        # ValidatedBOM
        obj = ValidatedBOM(
            design_id="test",
            intent=sample_intent,
            components=[],
            total_confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"ValidatedBOM: {e}")

    try:
        # BOMEntry
        obj = BOMEntry(
            ref="R1",
            component_type="resistor",
            justification="test",
            source="test",
            confidence=0.9,
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"BOMEntry: {e}")

    try:
        # DesignMethodology - enum
        obj = DesignMethodology.STANDARD_SMD
        json.dumps(obj.value)
    except Exception as e:
        errors.append(f"DesignMethodology: {e}")

    try:
        # FrequencySpec
        obj = FrequencySpec(
            value=100.0,
            unit="MHz",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"FrequencySpec: {e}")

    try:
        # AmbiguityFlag
        obj = AmbiguityFlag(
            field="test",
            description="test",
            severity="WARNING",
        )
        obj.model_dump_json()
    except Exception as e:
        errors.append(f"AmbiguityFlag: {e}")

    if errors:
        check(
            6,
            "Basic instantiation round-trips to JSON without error",
            False,
            "; ".join(errors[:5]) + ("..." if len(errors) > 5 else ""),
        )
    else:
        check(6, "Basic instantiation round-trips to JSON without error", True)

except Exception as e:
    check(
        6,
        "Basic instantiation round-trips to JSON without error",
        False,
        f"Unexpected error: {type(e).__name__}: {e}",
    )

# CHECK 7 — mypy on src/schemas/ only
print("\n" + "-" * 60)
try:
    import subprocess
    import shlex

    result = subprocess.run(
        shlex.split("mypy src/schemas/ --ignore-missing-imports"),
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
    )

    # Filter for errors only (not warnings, not success messages)
    lines = result.stdout.strip().split("\n")
    error_lines = []
    for line in lines:
        if "error:" in line.lower() or (line.strip() and ".py:" in line and "warning:" not in line.lower()):
            if "success" not in line.lower() and "files checked" not in line.lower():
                error_lines.append(line)

    if result.returncode != 0 or error_lines:
        check(
            7,
            "mypy on src/schemas/ only",
            False,
            "\n  ".join([""] + error_lines[:10]),
        )
    else:
        check(7, "mypy on src/schemas/ only", True)

except Exception as e:
    check(7, "mypy on src/schemas/ only", False, f"{type(e).__name__}: {e}")

# Final summary
print("\n" + "=" * 60)
passed = sum(1 for _, _, passed, _ in results if passed)
total = len(results)

if passed == total:
    print(f"Team F: PASS ({passed}/{total} checks passed)")
else:
    print(f"Team F: FAIL ({passed}/{total} checks passed)")
    print("\nFailed checks:")
    for num, name, passed, error in results:
        if not passed:
            print(f"  CHECK {num} — {name}")
            if error:
                print(f"    {error}")

print("=" * 60)

sys.exit(0 if passed == total else 1)
