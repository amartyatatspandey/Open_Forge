"""Dictionary-based pin normalization.

Provides the canonical mapping of raw pin names to normalized functions
using a comprehensive lookup table for common pin naming conventions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from src.config import Config, get_config


def load_canonical_functions(config: Config) -> dict[str, str]:
    """Load raw pin name → canonical function map from YAML config."""
    path = Path(config.canonical_functions_path)
    if not path.exists():
        raise FileNotFoundError(f"Canonical functions file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        raise ValueError("canonical_functions.yaml 'aliases' must be a mapping")

    return {str(raw): str(canonical) for raw, canonical in aliases.items()}


PIN_NORMALIZATION_MAP: dict[str, str] = load_canonical_functions(get_config())


def normalize_from_dictionary(raw_name: str) -> Optional[str]:
    """Look up pin normalization from dictionary.

    Performs tiered lookup:
    1. Direct lookup after stripping whitespace and uppercasing
    2. Strip trailing digits and retry ("GPIO0" → "GPIO")
    3. Strip leading N/! for active-low pins and retry ("NRST" → "RST")

    Args:
        raw_name: Raw pin name from datasheet (e.g., "VDD", "GPIO0", "NRST")

    Returns:
        Canonical function string from PIN_NORMALIZATION_MAP, or None if no match

    Examples:
        >>> normalize_from_dictionary("VDD")
        'POWER_POSITIVE'
        >>> normalize_from_dictionary("  vdd  ")
        'POWER_POSITIVE'
        >>> normalize_from_dictionary("GPIO0")
        'GPIO'
        >>> normalize_from_dictionary("NRST")
        'RESET'
        >>> normalize_from_dictionary("UNKNOWN123")
        None
    """
    if not raw_name:
        return None

    # Clean and normalize input
    clean_name = raw_name.strip().upper()

    # Tier 1: Direct lookup
    if clean_name in PIN_NORMALIZATION_MAP:
        return PIN_NORMALIZATION_MAP[clean_name]

    # Tier 2: Strip trailing digits
    # Handle cases like "GPIO0", "IO1", "INT2", etc.
    name_no_digits = clean_name
    while name_no_digits and name_no_digits[-1].isdigit():
        name_no_digits = name_no_digits[:-1]

    if name_no_digits and name_no_digits in PIN_NORMALIZATION_MAP:
        return PIN_NORMALIZATION_MAP[name_no_digits]

    # Tier 3: Handle active-low prefixes
    # "NRST" → "RST", "!EN" → "EN", "CSN" → "CS"
    if clean_name.startswith("N") and len(clean_name) > 1:
        without_n = clean_name[1:]
        if without_n in PIN_NORMALIZATION_MAP:
            return PIN_NORMALIZATION_MAP[without_n]

    if clean_name.startswith("!") and len(clean_name) > 1:
        without_bang = clean_name[1:]
        if without_bang in PIN_NORMALIZATION_MAP:
            return PIN_NORMALIZATION_MAP[without_bang]

    # Handle _N and _L suffixes (active-low indicators)
    if clean_name.endswith("_N") or clean_name.endswith("_L"):
        without_suffix = clean_name[:-2]
        if without_suffix in PIN_NORMALIZATION_MAP:
            base = PIN_NORMALIZATION_MAP[without_suffix]
            # Return active-low variant if exists, otherwise return base
            return base

    # No match found
    return None
