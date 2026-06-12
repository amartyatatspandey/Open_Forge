#!/usr/bin/env python3
"""Validate all golden ground-truth JSON files against ComponentDatasheet schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.datasheet import ComponentDatasheet

EXPECTED_GOLDEN_COUNT: int = 5

# Known corpus entries; missing files are reported but do not fail validation.
EXPECTED_GOLDEN_FILES: tuple[str, ...] = (
    "TI_SN74LVC1G04_v1_ground_truth.json",
    "TI_TLV7021_v1_ground_truth.json",
    "TI_INA219_v1_ground_truth.json",
    "TI_LM5176_v1_ground_truth.json",
    "TI_TPS62933_v1_ground_truth.json",
)


def discover_ground_truth_files(golden_dir: Path) -> list[Path]:
    """Return sorted paths matching the golden ground-truth glob pattern."""
    return sorted(golden_dir.glob("*_ground_truth.json"))


def load_json(path: Path) -> dict:
    """Load and parse a JSON file from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def validate_ground_truth_file(path: Path) -> tuple[bool, str | None]:
    """
    Parse a ground-truth JSON file and instantiate ComponentDatasheet.

    Returns:
        A tuple of (success, error_detail). error_detail is None on success.
    """
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}"
    except OSError as exc:
        return False, f"could not read file: {exc}"

    try:
        ComponentDatasheet(**data)
    except Exception as exc:
        return False, str(exc)

    return True, None


def print_missing_file_notice(filename: str) -> None:
    """Print a non-fatal notice for an expected but absent golden file."""
    print(f"⏳ {filename} not found (pending annotation)")


def main() -> int:
    """Validate golden corpus JSON files and print a pass/fail summary."""
    golden_dir = Path(__file__).parent
    discovered = {path.name: path for path in discover_ground_truth_files(golden_dir)}

    passed_count = 0
    failed_count = 0

    for filename in EXPECTED_GOLDEN_FILES:
        path = discovered.get(filename)
        if path is None:
            print_missing_file_notice(filename)
            continue

        success, error_detail = validate_ground_truth_file(path)
        if success:
            passed_count += 1
            print(f"✅ {filename} validates")
        else:
            failed_count += 1
            print(f"❌ {filename} failed: {error_detail}")

    # Report any unexpected ground-truth files not in the expected list.
    unexpected = sorted(set(discovered) - set(EXPECTED_GOLDEN_FILES))
    for filename in unexpected:
        path = discovered[filename]
        success, error_detail = validate_ground_truth_file(path)
        if success:
            passed_count += 1
            print(f"✅ {filename} validates (unexpected file)")
        else:
            failed_count += 1
            print(f"❌ {filename} failed: {error_detail}")

    print()
    pending = [name for name in EXPECTED_GOLDEN_FILES if name not in discovered]
    status_suffix = " ✅" if failed_count == 0 else ""
    print(f"Summary: {passed_count}/{EXPECTED_GOLDEN_COUNT} golden datasheets valid{status_suffix}")
    if pending:
        pending_id = pending[0].replace("_v1_ground_truth.json", "")
        print(f"({pending_id} pending annotation)")

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
