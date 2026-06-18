"""Utility functions for datasheet processing.

This module provides helper functions for package normalization,
PDF hashing, and confidence aggregation used throughout the
datasheet extraction pipeline.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Final

from src.schemas.datasheet import ExtractionMethod
from src.schemas.kg import EXTRACTION_METHOD_CONFIDENCE


# =============================================================================
# Constants for compute_extraction_confidence
# =============================================================================

# Weight factors for confidence aggregation
# These sum to 1.0 and represent the relative importance of each factor
METHOD_CONFIDENCE_WEIGHT: Final[float] = 0.4
PHASE2_CONFIDENCE_WEIGHT: Final[float] = 0.3
FIELD_COVERAGE_WEIGHT: Final[float] = 0.3

# Chunk size for SHA-256 hashing (8KB for memory efficiency)
SHA256_CHUNK_SIZE: Final[int] = 8192


# =============================================================================
# Package Normalization
# =============================================================================

# IPC-7351 normalized footprint names with regex patterns for matching
PACKAGE_PATTERNS: Final[dict[str, list[str]]] = {
    "SOT-23-5": [
        r"SOT-?23-?5",
        r"SOT23-?5",
        r"5-?pin\s+SOT-?23",
        r"SOT-?23\s*\(?5-?pin\)?",
        r"SOT-?23\s*5",
        r"DRLR.*SOT-?23-?5",
    ],
    "SOT-23-3": [
        r"SOT-?23-?3",
        r"SOT23-?3",
        r"3-?pin\s+SOT-?23",
        r"SOT-?23\s*\(?3-?pin\)?",
    ],
    "SOT-23": [
        r"SOT-?23\b",
        r"SOT23\b",
    ],
    "SOIC-8": [
        r"SOIC-?8",
        r"SOIC8",
        r"8-?pin\s+SOIC",
        r"SOIC\s*\(?8-?pin\)?",
        r"SOIC\s*8",
    ],
    "SOIC-16": [
        r"SOIC-?16",
        r"SOIC16",
        r"16-?pin\s+SOIC",
        r"SOIC\s*\(?16-?pin\)?",
        r"SOIC\s*16",
    ],
    "DIP-8": [
        r"DIP-?8",
        r"DIP8",
        r"8-?pin\s+DIP",
        r"DIP\s*\(?8-?pin\)?",
        r"DIP\s*8",
        r"PDIP-?8",
        r"PDIP8",
    ],
    "DIP-14": [
        r"DIP-?14",
        r"DIP14",
        r"14-?pin\s+DIP",
        r"DIP\s*\(?14-?pin\)?",
        r"DIP\s*14",
        r"PDIP-?14",
        r"PDIP14",
    ],
    "QFN-16": [
        r"QFN-?16",
        r"QFN16",
        r"16-?pin\s+QFN",
        r"QFN\s*\(?16-?pin\)?",
        r"QFN\s*16",
    ],
    "QFN-24": [
        r"QFN-?24",
        r"QFN24",
        r"24-?pin\s+QFN",
        r"QFN\s*\(?24-?pin\)?",
        r"QFN\s*24",
    ],
    "QFN-32": [
        r"QFN-?32",
        r"QFN32",
        r"32-?pin\s+QFN",
        r"QFN\s*\(?32-?pin\)?",
        r"QFN\s*32",
    ],
    "TSSOP-8": [
        r"TSSOP-?8",
        r"TSSOP8",
        r"8-?pin\s+TSSOP",
        r"TSSOP\s*\(?8-?pin\)?",
        r"TSSOP\s*8",
    ],
    "TSSOP-16": [
        r"TSSOP-?16",
        r"TSSOP16",
        r"16-?pin\s+TSSOP",
        r"TSSOP\s*\(?16-?pin\)?",
        r"TSSOP\s*16",
    ],
    "TO-220": [
        r"TO-?220",
        r"TO220",
        r"TO-?220AB",
    ],
    "TO-92": [
        r"TO-?92",
        r"TO92",
    ],
    "0402": [
        r"\b0402\b",
        r"0402\s*\(?metric\s*1005\)?",
        r"1005\s*\(?0402\)?",
    ],
    "0603": [
        r"\b0603\b",
        r"0603\s*\(?metric\s*1608\)?",
        r"1608\s*\(?0603\)?",
    ],
    "0805": [
        r"\b0805\b",
        r"0805\s*\(?metric\s*2012\)?",
        r"2012\s*\(?0805\)?",
    ],
    "1206": [
        r"\b1206\b",
        r"1206\s*\(?metric\s*3216\)?",
        r"3216\s*\(?1206\)?",
    ],
}

# Compile patterns for efficiency
COMPILED_PATTERNS: Final[dict[str, list[re.Pattern[str]]]] = {
    name: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for name, patterns in PACKAGE_PATTERNS.items()
}


def normalize_package(raw_text: str) -> tuple[str, bool]:
    """Normalize raw datasheet package text to IPC-7351 footprint name.

    Uses regex pattern matching to identify common package naming variants
    and map them to standardized IPC-7351 footprint names.

    Examples:
        "5-pin SOT-23 package" -> ("SOT-23-5", False)
        "DRLR (SOT-23-5)" -> ("SOT-23-5", False)
        "8-pin SOIC" -> ("SOIC-8", False)
        "DIP-8" -> ("DIP-8", False)
        "Unknown XYZ-99" -> ("Unknown XYZ-99", True)

    Args:
        raw_text: Raw package text from datasheet (e.g., "5-pin SOT-23 package")

    Returns:
        Tuple of (normalized_name, needs_review). needs_review is False if
        a recognized IPC-7351 pattern was matched, True if the package is
        unknown or unrecognizable.

    Notes:
        - Never raises an exception. Unknown packages return (raw_text, True).
        - Patterns are case-insensitive.
        - Longer/more specific patterns are checked first to avoid false matches
          (e.g., "SOT-23-5" before "SOT-23").
    """
    if not raw_text or not isinstance(raw_text, str):
        return (raw_text if raw_text else "", True)

    cleaned_text = raw_text.strip()

    # Sort by length of pattern key descending to check specific before general
    # (e.g., SOT-23-5 before SOT-23)
    for name in sorted(COMPILED_PATTERNS.keys(), key=len, reverse=True):
        for pattern in COMPILED_PATTERNS[name]:
            if pattern.search(cleaned_text):
                return (name, False)

    # No match found - return original text with review flag
    return (cleaned_text, True)


# =============================================================================
# PDF Hashing
# =============================================================================


def compute_pdf_sha256(pdf_path: Path) -> str:
    """Return SHA-256 hex digest of file at pdf_path.

    Reads the file in chunks of 8192 bytes for memory efficiency,
    making it suitable for large PDF files.

    Args:
        pdf_path: Path to the PDF file to hash

    Returns:
        Lowercase hexadecimal string of the SHA-256 digest

    Raises:
        FileNotFoundError: If pdf_path does not exist
        PermissionError: If pdf_path cannot be read
        IsADirectoryError: If pdf_path is a directory

    Example:
        >>> compute_pdf_sha256(Path("datasheet.pdf"))
        'a1b2c3d4e5f6789012345678901234567890abcd...'
    """
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if path.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a file: {pdf_path}")

    sha256_hash = hashlib.sha256()

    with open(path, "rb") as f:
        while chunk := f.read(SHA256_CHUNK_SIZE):
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest().lower()


# =============================================================================
# Confidence Aggregation
# =============================================================================


def compute_extraction_confidence(
    method: ExtractionMethod,
    phase2_confidence: float,
    phase3_field_coverage: float,
) -> float:
    """Aggregate confidence for the full ComponentDatasheet.

    Computes a weighted aggregate confidence score based on:
    - Method confidence: Base confidence from extraction method (40%)
    - Phase 2 confidence: Table structure recognition quality (30%)
    - Field coverage: Fraction of expected fields extracted (30%)

    Args:
        method: Which extraction method was used for the majority of tables.
                Used to look up base confidence in EXTRACTION_METHOD_CONFIDENCE.
        phase2_confidence: Confidence score from pick_best_grid() [0.0, 1.0]
        phase3_field_coverage: Fraction of expected fields successfully
                               extracted [0.0, 1.0]

    Returns:
        Weighted aggregate confidence clamped to [0.0, 1.0]

    Raises:
        ValueError: If method is not a valid ExtractionMethod

    Notes:
        - Weights sum to 1.0: METHOD_CONFIDENCE_WEIGHT + PHASE2_CONFIDENCE_WEIGHT
          + FIELD_COVERAGE_WEIGHT = 1.0
        - Result is clamped to [0.0, 1.0] even if inputs exceed these bounds
        - Method confidence is retrieved from EXTRACTION_METHOD_CONFIDENCE

    Example:
        >>> compute_extraction_confidence(
        ...     ExtractionMethod.P1_VECTOR,
        ...     phase2_confidence=0.95,
        ...     phase3_field_coverage=0.88
        ... )
        0.937  # 0.97*0.4 + 0.95*0.3 + 0.88*0.3 = 0.937
    """
    # Get base confidence for the extraction method
    method_confidence = EXTRACTION_METHOD_CONFIDENCE.get(method, 0.5)

    # Compute weighted aggregate
    aggregate = (
        method_confidence * METHOD_CONFIDENCE_WEIGHT
        + phase2_confidence * PHASE2_CONFIDENCE_WEIGHT
        + phase3_field_coverage * FIELD_COVERAGE_WEIGHT
    )

    # Clamp to valid range [0.0, 1.0]
    return max(0.0, min(1.0, aggregate))
