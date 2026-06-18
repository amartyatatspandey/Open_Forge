#!/usr/bin/env python3
"""Team C Gate - Intent parser and BOM validation checks."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
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
print("TEAM C GATE - Intent & BOM")
print("=" * 60)

from src.config import get_config

config = get_config()

# CHECK 1 — All Team C modules import without error
print("\n" + "-" * 60)
try:
    from src.intent import parse_intent, get_clarification_questions
    from src.intent.pipeline import run_intent_pipeline
    from src.intent.methodology_classifier import validate_methodology
    from src.intent.constraint_inferrer import infer_constraints
    from src.intent.ambiguity_detector import detect_ambiguities
    from src.bom import generate_bom
    from src.bom.validator import validate_bom
    from src.bom.supplier_cache import check_availability, AvailabilityStatus, upsert_availability

    check(1, "All Team C modules import without error", True)
except ImportError as e:
    check(1, "All Team C modules import without error", False, str(e))

# CHECK 2 — Goal extraction produces clean snake_case nouns
print("\n" + "-" * 60)
try:
    from src.intent import parser as intent_parser

    clean_goal_fn = getattr(intent_parser, "clean_goal", None)
    if clean_goal_fn is None:
        check(
            2,
            "Goal extraction produces clean snake_case nouns",
            False,
            "Goal post-processing missing — LLM produces invalid goals "
            "containing articles and prepositions. Must be fixed before Team D.",
        )
    else:
        bad_goals = [
            ("a_3_3v_ldo", "ldo_regulator"),
            ("a_2_4ghz_patch", "patch_antenna"),
            ("a_buck_converter_for", "buck_converter"),
            ("the_motor_driver", "motor_driver"),
        ]
        errors = []
        for raw, expected in bad_goals:
            result = clean_goal_fn(raw)
            if result != expected:
                errors.append(f"{raw!r}: got {result!r}, expected {expected!r}")
        if errors:
            check(
                2,
                "Goal extraction produces clean snake_case nouns",
                False,
                "; ".join(errors),
            )
        else:
            check(2, "Goal extraction produces clean snake_case nouns", True)
except Exception as e:
    check(
        2,
        "Goal extraction produces clean snake_case nouns",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 3 — Methodology classifier overrides wrong LLM result
print("\n" + "-" * 60)
try:
    from src.intent.methodology_classifier import validate_methodology
    from src.schemas.intent import DesignMethodology

    result, overridden = validate_methodology(
        DesignMethodology.STANDARD_SMD,
        "I need to design a 2.4GHz Bluetooth antenna",
    )
    errors = []
    if result != DesignMethodology.RF_HIGHFREQ:
        errors.append(f"result={result!r}, expected DesignMethodology.RF_HIGHFREQ")
    if overridden is not True:
        errors.append(f"overridden={overridden!r}, expected True")
    if errors:
        check(3, "Methodology classifier overrides wrong LLM result", False, "; ".join(errors))
    else:
        check(3, "Methodology classifier overrides wrong LLM result", True)
except Exception as e:
    check(3, "Methodology classifier overrides wrong LLM result", False, f"{type(e).__name__}: {e}")

# CHECK 4 — RF design without frequency triggers CRITICAL ambiguity
print("\n" + "-" * 60)
try:
    from src.intent.ambiguity_detector import detect_ambiguities
    from src.schemas.intent import IntentDict, DesignMethodology

    parsed = IntentDict(
        goal="patch_antenna",
        application="drone",
        design_methodology=DesignMethodology.RF_HIGHFREQ,
        frequency=None,
        board_type="standard_SMD",
        raw_prompt="build an antenna for a drone",
    )
    flags = detect_ambiguities(parsed, parsed.raw_prompt)
    critical = [f for f in flags if f.severity == "CRITICAL" and f.field == "frequency"]
    if len(critical) == 0:
        check(
            4,
            "RF design without frequency triggers CRITICAL ambiguity",
            False,
            "RF design with no frequency must produce CRITICAL ambiguity on frequency field",
        )
    else:
        check(4, "RF design without frequency triggers CRITICAL ambiguity", True)
except Exception as e:
    check(
        4,
        "RF design without frequency triggers CRITICAL ambiguity",
        False,
        f"{type(e).__name__}: {e}",
    )

# CHECK 5 — BOM design_id is a valid UUID
print("\n" + "-" * 60)
try:
    from src.bom import generate_bom
    from src.schemas.intent import IntentDict, DesignMethodology
    from src.schemas.kg import DesignSubgraph

    empty_subgraph = DesignSubgraph(
        component_types=[],
        component_instances=[],
        design_rules=[],
        placement_rules=[],
        routing_hints=[],
        design_methodology="standard_SMD",
        path_confidences={},
        query_depth=0,
    )
    intent = IntentDict(
        goal="test_component",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt="test",
    )
    bom = generate_bom(empty_subgraph, intent, config)
    try:
        uuid.UUID(bom.design_id)
        print("CHECK 5: PASS — valid UUID")
        check(5, "BOM design_id is a valid UUID", True)
    except ValueError:
        print(f"CHECK 5: FAIL — design_id is not a UUID: {bom.design_id!r}")
        check(
            5,
            "BOM design_id is a valid UUID",
            False,
            f"design_id is not a UUID: {bom.design_id!r}",
        )
except Exception as e:
    check(5, "BOM design_id is a valid UUID", False, f"{type(e).__name__}: {e}")

# CHECK 6 — validate_bom never mutates input
print("\n" + "-" * 60)
try:
    from src.bom import generate_bom, validate_bom
    from src.schemas.intent import IntentDict, DesignMethodology
    from src.schemas.kg import DesignSubgraph

    empty_subgraph = DesignSubgraph(
        component_types=[],
        component_instances=[],
        design_rules=[],
        placement_rules=[],
        routing_hints=[],
        design_methodology="standard_SMD",
        path_confidences={},
        query_depth=0,
    )
    intent = IntentDict(
        goal="test_component",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt="test",
    )
    bom_before = generate_bom(empty_subgraph, intent, config)
    result_bom = validate_bom(bom_before, config)

    errors = []
    if result_bom is bom_before:
        errors.append("validate_bom returned same object as input")
    if id(result_bom.components) == id(bom_before.components):
        errors.append("validate_bom.components is same list object as input")

    if errors:
        check(6, "validate_bom never mutates input", False, "; ".join(errors))
    else:
        print("validate_bom returns new object: PASS")
        check(6, "validate_bom never mutates input", True)
except Exception as e:
    check(6, "validate_bom never mutates input", False, f"{type(e).__name__}: {e}")

# CHECK 7 — supplier cache round-trip with temp SQLite
print("\n" + "-" * 60)
try:
    from src.bom.supplier_cache import (
        AvailabilityStatus,
        check_availability,
        upsert_availability,
    )

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name

    cache_config = config.model_copy(update={"supplier_cache_path": Path(tmp_path)})
    try:
        upsert_availability(
            "TPS62933DRLR",
            AvailabilityStatus.AVAILABLE,
            price_usd=0.85,
            stock_count=5000,
            supplier="DigiKey",
            snapshot_date="2026-01-01",
            config=cache_config,
        )
        status = check_availability("TPS62933DRLR", cache_config)
        status_unknown = check_availability("NONEXISTENT999", cache_config)

        errors = []
        if status != AvailabilityStatus.AVAILABLE:
            errors.append(f"expected AVAILABLE, got {status!r}")
        if status_unknown != AvailabilityStatus.UNKNOWN:
            errors.append(f"expected UNKNOWN for missing part, got {status_unknown!r}")

        if errors:
            check(7, "supplier cache round-trip with temp SQLite", False, "; ".join(errors))
        else:
            print("CHECK 7: PASS")
            check(7, "supplier cache round-trip with temp SQLite", True)
    finally:
        os.unlink(tmp_path)
except Exception as e:
    check(7, "supplier cache round-trip with temp SQLite", False, f"{type(e).__name__}: {e}")

# CHECK 8 — mypy on src/intent/ and src/bom/
print("\n" + "-" * 60)
try:
    mypy_result = subprocess.run(
        ["mypy", "src/intent/", "src/bom/", "--ignore-missing-imports"],
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
            "mypy on src/intent/ and src/bom/",
            False,
            "\n  ".join([""] + error_lines),
        )
    else:
        check(8, "mypy on src/intent/ and src/bom/", True)
except Exception as e:
    check(8, "mypy on src/intent/ and src/bom/", False, f"{type(e).__name__}: {e}")

print("\n" + "=" * 60)
passed = sum(1 for _, _, p, _ in results if p)
total = len(results)

if passed == total:
    print(f"Team C: PASS ({passed}/{total} checks passed)")
else:
    print(f"Team C: FAIL ({passed}/{total} checks passed)")
    print("\nFailed checks:")
    for num, name, p, error in results:
        if not p:
            print(f"  CHECK {num} — {name}")
            if error:
                print(f"    {error}")

print("=" * 60)
sys.exit(0 if passed == total else 1)
