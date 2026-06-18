"""Unit normalization for Phase 3 semantic extraction.

Converts raw unit strings from datasheets to canonical units with normalized
float values. Handles OCR errors and common unit aliases.

Supported canonical units:
- Voltage: V
- Current: A
- Resistance: Ω
- Capacitance: F
- Frequency: Hz
- Time: s
- Temperature: °C
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# Unit conversion multipliers to canonical units
# Format: (canonical_unit, multiplier_to_canonical)
UNIT_CONVERSIONS: dict[str, tuple[str, float]] = {
    # Voltage
    "mV": ("V", 1e-3),
    "µV": ("V", 1e-6),
    "uV": ("V", 1e-6),  # OCR alias
    "kV": ("V", 1e3),
    "MV": ("V", 1e6),
    "V": ("V", 1.0),
    # Current
    "mA": ("A", 1e-3),
    "µA": ("A", 1e-6),
    "uA": ("A", 1e-6),  # OCR alias
    "nA": ("A", 1e-9),
    "pA": ("A", 1e-12),
    "kA": ("A", 1e3),
    "A": ("A", 1.0),
    # Resistance
    "kΩ": ("Ω", 1e3),
    "kohm": ("Ω", 1e3),
    "kOhm": ("Ω", 1e3),
    "KΩ": ("Ω", 1e3),  # OCR variant
    "MΩ": ("Ω", 1e6),
    "Mohm": ("Ω", 1e6),
    "MOhm": ("Ω", 1e6),
    "mΩ": ("Ω", 1e-3),
    "mohm": ("Ω", 1e-3),
    "Ω": ("Ω", 1.0),
    "ohm": ("Ω", 1.0),
    "Ohm": ("Ω", 1.0),
    "ohms": ("Ω", 1.0),
    # Capacitance
    "nF": ("F", 1e-9),
    "µF": ("F", 1e-6),
    "uF": ("F", 1e-6),  # OCR alias
    "µf": ("F", 1e-6),  # lowercase variant
    "uf": ("F", 1e-6),
    "pF": ("F", 1e-12),
    "pf": ("F", 1e-12),
    "mF": ("F", 1e-3),
    "F": ("F", 1.0),
    # Frequency
    "GHz": ("Hz", 1e9),
    "MHz": ("Hz", 1e6),
    "kHz": ("Hz", 1e3),
    "Hz": ("Hz", 1.0),
    # Time
    "ns": ("s", 1e-9),
    "µs": ("s", 1e-6),
    "us": ("s", 1e-6),  # OCR alias
    "ms": ("s", 1e-3),
    "s": ("s", 1.0),
    # Temperature (no conversion needed)
    "°C": ("°C", 1.0),
    "°c": ("°C", 1.0),
    "C": ("°C", 1.0),  # Without degree symbol
    "°F": ("°F", 1.0),  # Fahrenheit preserved (rare in datasheets)
    "K": ("K", 1.0),  # Kelvin preserved
}


def _normalize_unit_text(raw_unit: str) -> str:
    """Normalize unit text by handling OCR aliases.

    Args:
        raw_unit: Raw unit string from datasheet

    Returns:
        Normalized unit string
    """
    unit = raw_unit.strip()
    
    # Handle 'u' as 'µ' (common OCR error)
    if unit.startswith('u') and len(unit) > 1:
        # uV -> µV, uA -> µA, uF -> µF, us -> µs
        unit = 'µ' + unit[1:]
    
    # Handle 'ohm' variants
    if unit.lower() == 'ohm' or unit.lower() == 'ohms':
        unit = 'Ω'
    
    # Handle lowercase capacitance
    if unit in ('pf', 'uf', 'nf', 'mf'):
        unit = unit.upper()
    
    return unit


def _parse_numeric_value(value_text: str) -> Optional[float]:
    """Parse numeric value from text, handling common formats.

    Args:
        value_text: Raw numeric string (e.g., "3.3", "1.5k", "2M")

    Returns:
        Parsed float value, or None if parsing fails
    """
    if not value_text or not value_text.strip():
        return None
    
    text = value_text.strip()
    
    # Remove common prefixes/suffixes
    text = text.replace(',', '')  # Remove thousand separators
    
    # Handle engineering notation suffixes
    multipliers = {
        'p': 1e-12, 'n': 1e-9, 'µ': 1e-6, 'u': 1e-6,
        'm': 1e-3, 'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9,
    }
    
    # Check for suffix multiplier
    for suffix, mult in multipliers.items():
        if text.endswith(suffix):
            try:
                base = float(text[:-1])
                return base * mult
            except ValueError:
                continue
    
    # Standard float parsing
    try:
        return float(text)
    except ValueError:
        # Try to extract numeric part with regex
        match = re.search(r'[-+]?[\d.]+(?:[eE][-+]?\d+)?', text)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        
        logger.warning(f"Could not parse numeric value: '{value_text}'")
        return None


def normalize_unit(
    value_text: str,
    unit_text: str,
) -> tuple[Optional[float], str, bool]:
    """Normalize raw value and unit to canonical form.

    Converts values with units to canonical units with normalized float values.
    Handles OCR errors, unit aliases, and common datasheet formats.

    Supported conversions:
    - mV→V, µV→V, kV→V (voltage)
    - mA→A, µA→A (current)
    - kΩ→Ω, MΩ→Ω (resistance)
    - nF→F, µF→F, pF→F (capacitance)
    - MHz→Hz, GHz→Hz, kHz→Hz (frequency)
    - ns→s, µs→s, ms→s (time)
    - °C stays °C (temperature)

    OCR aliases handled:
    - 'u' as 'µ' (uF→µF, uA→µA, etc.)
    - 'ohm' as 'Ω' (kohm→kΩ)

    Args:
        value_text: Raw numeric value string (e.g., "100", "3.3", "1.5k")
        unit_text: Raw unit string (e.g., "mV", "µA", "kohm")

    Returns:
        Tuple of (normalized_value, canonical_unit, needs_review):
        - normalized_value: Float value in canonical unit, or None if unknown unit
        - canonical_unit: Canonical unit string (V, A, Ω, F, Hz, s, °C)
        - needs_review: True if unit was not recognized and needs human review

    Examples:
        >>> normalize_unit("100", "mV")
        (0.1, "V", False)
        >>> normalize_unit("100", "uV")  # OCR error
        (1e-07, "V", False)
        >>> normalize_unit("10", "pF")
        (1e-11, "F", False)
        >>> normalize_unit("100", "XYZ")
        (None, "XYZ", True)
    """
    # Parse the numeric value
    value = _parse_numeric_value(value_text)
    
    if value is None:
        logger.warning(f"Could not parse value: '{value_text}'")
        return None, unit_text, True
    
    # Normalize unit text
    normalized_unit = _normalize_unit_text(unit_text)
    
    # Check for known unit conversion
    if normalized_unit in UNIT_CONVERSIONS:
        canonical, multiplier = UNIT_CONVERSIONS[normalized_unit]
        normalized_value = value * multiplier
        return normalized_value, canonical, False
    
    # Unknown unit - needs review
    logger.warning(f"Unknown unit '{unit_text}' (normalized: '{normalized_unit}')")
    return None, unit_text, True


def normalize_value_string(value_string: str) -> tuple[Optional[float], str, bool]:
    """Parse and normalize a combined value+unit string.

    Args:
        value_string: Combined value and unit (e.g., "3.3V", "100mA", "10µF")

    Returns:
        Tuple of (normalized_value, canonical_unit, needs_review)

    Examples:
        >>> normalize_value_string("3.3V")
        (3.3, "V", False)
        >>> normalize_value_string("100mV")
        (0.1, "V", False)
        >>> normalize_value_string("10uF")  # OCR error
        (1e-05, "F", False)
    """
    if not value_string or not value_string.strip():
        return None, "", True
    
    # Try to separate value and unit
    # Pattern: number (with optional engineering suffix) + unit
    match = re.match(r'^([\d.,]+(?:[eE][-+]?\d+)?)([a-zA-ZµΩ°\-]+)$', value_string.strip())
    
    if match:
        value_part = match.group(1)
        unit_part = match.group(2)
        return normalize_unit(value_part, unit_part)
    
    # Try with space separator
    parts = value_string.strip().split()
    if len(parts) >= 2:
        return normalize_unit(parts[0], parts[1])
    
    # Just a number?
    try:
        return float(value_string), "", False
    except ValueError:
        pass
    
    logger.warning(f"Could not parse value string: '{value_string}'")
    return None, value_string, True