#!/usr/bin/env python3
"""Team A Gate - Datasheet pipeline and review queue validation."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


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
print("TEAM A GATE - Datasheet Pipeline & Review Queue")
print("=" * 60)

# CHECK 1
print("\n" + "-" * 60)
check1_ok = False
try:
    from src.datasheet.pipeline import parse_datasheet, DatasheetPipelineError
    from src.datasheet.utils import (
        normalize_package,
        compute_pdf_sha256,
        compute_extraction_confidence,
    )
    from src.datasheet.phase1_dla import process as phase1_process
    from src.datasheet.phase2_tsr import process as phase2_process
    from src.datasheet.phase3_extract import process as phase3_process
    from src.datasheet.phase4_validate import check as phase4_check, apply_verdict
    from src.datasheet.phase5_layout import extract_layout_constraints
    from src.review.queue import enqueue, list_pending, update_status, export_corrections

    check(1, "All Team A modules import without error", True)
    check1_ok = True
except ImportError as e:
    check(1, "All Team A modules import without error", False, str(e))

from src.config import get_config

config = get_config()

if not check1_ok:
    try:
        from src.datasheet.utils import normalize_package
    except ImportError:
        normalize_package = None  # type: ignore[assignment,misc]
    try:
        from src.datasheet.phase5_layout import extract_layout_constraints
    except ImportError:
        extract_layout_constraints = None  # type: ignore[assignment,misc]
    try:
        from src.review.queue import enqueue, list_pending, update_status
    except ImportError:
        enqueue = list_pending = update_status = None  # type: ignore[assignment,misc]
    try:
        from src.datasheet.pipeline import parse_datasheet, DatasheetPipelineError
    except ImportError:
        parse_datasheet = DatasheetPipelineError = None  # type: ignore[assignment,misc]
    try:
        from src.datasheet.phase4_validate import ValidationResult
    except ImportError:
        ValidationResult = None  # type: ignore[assignment,misc]
else:
    from src.datasheet.phase4_validate import ValidationResult

from src.datasheet.phase1_dla._schemas import Phase1Output, TableCrop
from src.schemas.datasheet import (
    ComponentDatasheet,
    ExtractionMethod,
    TableSectionType,
)

# CHECK 2
print("\n" + "-" * 60)
if normalize_package is None:
    check(2, "normalize_package() returns IPC-7351 strings", False, "normalize_package not imported")
else:
    cases = [
        ("SOT-23-5 package", "SOT-23-5"),
        ("8-pin SOIC", "SOIC-8"),
        ("DIP-8", "DIP-8"),
        ("0402", "0402"),
    ]
    check2_errors = []
    for raw, expected in cases:
        result, _needs_review = normalize_package(raw)
        if result != expected:
            check2_errors.append(f"{raw!r}: expected {expected!r}, got {result!r}")

    if check2_errors:
        check(
            2,
            "normalize_package() returns IPC-7351 strings",
            False,
            "; ".join(check2_errors),
        )
    else:
        check(2, "normalize_package() returns IPC-7351 strings", True)

# CHECK 3
print("\n" + "-" * 60)
if normalize_package is None:
    check(
        3,
        "normalize_package() returns needs_review=True for unknown input",
        False,
        "normalize_package not imported",
    )
else:
    _result, needs_review = normalize_package("some completely unknown package XYZ")
    if needs_review is not True:
        check(
            3,
            "normalize_package() returns needs_review=True for unknown input",
            False,
            f"needs_review={needs_review!r}, expected True",
        )
    else:
        check(3, "normalize_package() returns needs_review=True for unknown input", True)

# CHECK 4
print("\n" + "-" * 60)
if extract_layout_constraints is None:
    check(
        4,
        "Phase 5 returns empty list when no LAYOUT_RECOMMENDATIONS crops exist",
        False,
        "extract_layout_constraints not imported",
    )
else:
    try:
        phase1_output = Phase1Output(
            pdf_path="test.pdf",
            source_pdf_hash="abc123",
            total_pages=1,
            table_crops=[
                TableCrop(
                    page_number=1,
                    section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
                    image_bytes=b"",
                    bounding_box=(0, 0, 100, 100),
                    detection_confidence=0.9,
                )
            ],
            footnote_maps=[],
            processing_time_ms=1.0,
        )
        layout_result = extract_layout_constraints(
            Path("nonexistent.pdf"), phase1_output, config
        )
        if layout_result != []:
            check(
                4,
                "Phase 5 returns empty list when no LAYOUT_RECOMMENDATIONS crops exist",
                False,
                f"expected [], got {layout_result!r}",
            )
        else:
            check(
                4,
                "Phase 5 returns empty list when no LAYOUT_RECOMMENDATIONS crops exist",
                True,
            )
    except Exception as e:
        check(
            4,
            "Phase 5 returns empty list when no LAYOUT_RECOMMENDATIONS crops exist",
            False,
            f"{type(e).__name__}: {e}",
        )

# CHECK 5
print("\n" + "-" * 60)
if (
    enqueue is None
    or list_pending is None
    or update_status is None
    or ValidationResult is None
):
    check(
        5,
        "Review queue round-trip using temp SQLite",
        False,
        "review queue or ValidationResult not imported",
    )
else:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_path = f.name
        config.review_queue_path = Path(tmp_path)

        datasheet = ComponentDatasheet(
            component_id="GATE_TEST",
            manufacturer="TestCorp",
            description="Gate test component",
            package="SOIC-8",
            source_pdf_hash="gate_test_hash",
            extraction_method=ExtractionMethod.MANUAL,
            extraction_confidence=0.5,
            review_required=True,
            review_flags=["gate test flag"],
            created_at="2026-06-18T00:00:00Z",
        )
        validation_result = ValidationResult(
            verdict="WARN",
            severity="WARNING",
            confidence=0.5,
            flags=["gate test flag"],
        )

        item = enqueue(datasheet, validation_result, config)
        if item is None:
            check(
                5,
                "Review queue round-trip using temp SQLite",
                False,
                "enqueue returned None",
            )
        else:
            pending = list_pending(config)
            errors = []
            if len(pending) == 0:
                errors.append("list_pending returned empty list")
            elif pending[0].item_id != item.item_id:
                errors.append(
                    f"pending[0].item_id={pending[0].item_id!r} != item.item_id={item.item_id!r}"
                )
            else:
                update_status(item.item_id, "approved", "gate test", config)
                pending_after = list_pending(config)
                if any(p.item_id == item.item_id for p in pending_after):
                    errors.append("item still in pending list after approval")

            if errors:
                check(
                    5,
                    "Review queue round-trip using temp SQLite",
                    False,
                    "; ".join(errors),
                )
            else:
                check(5, "Review queue round-trip using temp SQLite", True)
    except Exception as e:
        check(
            5,
            "Review queue round-trip using temp SQLite",
            False,
            f"{type(e).__name__}: {e}",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

# CHECK 6
print("\n" + "-" * 60)
if parse_datasheet is None or DatasheetPipelineError is None:
    check(
        6,
        "DatasheetPipelineError is raised when phase fails",
        False,
        "parse_datasheet or DatasheetPipelineError not imported",
    )
else:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_pdf = Path(f.name)
    try:
        with patch(
            "src.datasheet.phase1_dla.process",
            side_effect=RuntimeError("mock phase1 failure"),
        ):
            try:
                parse_datasheet("TEST001", tmp_pdf, config)
                print("CHECK 6: FAIL — no exception raised")
                check(
                    6,
                    "DatasheetPipelineError is raised when phase fails",
                    False,
                    "no exception raised",
                )
            except DatasheetPipelineError as e:
                print(f"CHECK 6: PASS — DatasheetPipelineError raised, phase={e.phase}")
                check(6, "DatasheetPipelineError is raised when phase fails", True)
            except Exception as e:
                print(f"CHECK 6: FAIL — wrong exception type: {type(e).__name__}: {e}")
                check(
                    6,
                    "DatasheetPipelineError is raised when phase fails",
                    False,
                    f"wrong exception type: {type(e).__name__}: {e}",
                )
    finally:
        tmp_pdf.unlink(missing_ok=True)

# CHECK 7
print("\n" + "-" * 60)
try:
    mypy_result = subprocess.run(
        ["mypy", "src/datasheet/", "src/review/", "--ignore-missing-imports"],
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
            7,
            "mypy on src/datasheet/ and src/review/",
            False,
            "\n  ".join([""] + error_lines[:20]),
        )
    else:
        check(7, "mypy on src/datasheet/ and src/review/", True)
except Exception as e:
    check(
        7,
        "mypy on src/datasheet/ and src/review/",
        False,
        f"{type(e).__name__}: {e}",
    )

print("\n" + "=" * 60)
passed = sum(1 for _, _, p, _ in results if p)
total = len(results)

if passed == total:
    print(f"Team A: PASS ({passed}/{total} checks passed)")
else:
    print(f"Team A: FAIL ({passed}/{total} checks passed)")
    print("\nFailed checks:")
    for num, name, p, error in results:
        if not p:
            print(f"  CHECK {num} — {name}")
            if error:
                print(f"    {error}")

print("=" * 60)
sys.exit(0 if passed == total else 1)
