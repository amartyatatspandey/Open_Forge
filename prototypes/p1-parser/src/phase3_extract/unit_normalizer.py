"""Unit normalization for extracted electrical values."""

from __future__ import annotations

import re

CANONICAL_UNITS = {
    "voltage": "V",
    "current": "mA",
    "resistance": "Ω",
    "capacitance": "pF",
    "inductance": "nH",
    "frequency": "MHz",
    "temperature": "°C",
    "time": "ns",
    "power": "mW",
    "other": "V",
}

UNIT_CONVERSION_TABLE: dict[str, tuple[float | None, str]] = {
    "uv": (1e-6, "V"),
    "µv": (1e-6, "V"),
    "mv": (1e-3, "V"),
    "v": (1.0, "V"),
    "kv": (1e3, "V"),
    "ua": (1e-3, "mA"),
    "µa": (1e-3, "mA"),
    "ma": (1.0, "mA"),
    "a": (1e3, "mA"),
    "ω": (1.0, "Ω"),
    "ohm": (1.0, "Ω"),
    "kohm": (1e3, "Ω"),
    "kω": (1e3, "Ω"),
    "mohm": (1e6, "Ω"),
    "mω": (1e6, "Ω"),
    "pf": (1.0, "pF"),
    "nf": (1e3, "pF"),
    "uf": (1e6, "pF"),
    "µf": (1e6, "pF"),
    "mf": (1e9, "pF"),
    "nh": (1.0, "nH"),
    "uh": (1e3, "nH"),
    "µh": (1e3, "nH"),
    "mh": (1e6, "nH"),
    "hz": (1e-6, "MHz"),
    "khz": (1e-3, "MHz"),
    "mhz": (1.0, "MHz"),
    "ghz": (1e3, "MHz"),
    "ps": (1e-3, "ns"),
    "ns": (1.0, "ns"),
    "us": (1e3, "ns"),
    "µs": (1e3, "ns"),
    "ms": (1e6, "ns"),
    "°c": (1.0, "°C"),
    "c": (1.0, "°C"),
    "uw": (1e-3, "mW"),
    "µw": (1e-3, "mW"),
    "mw": (1.0, "mW"),
    "w": (1e3, "mW"),
    "db": (1.0, "dB"),
    "%": (1.0, "%"),
}


def _normalize_unit_key(raw_unit: str) -> str:
    """Normalize unit string for lookup."""
    key = raw_unit.strip().lower().replace(" ", "")
    if len(key) >= 2 and key[0] == "u" and key[1].isalpha():
        key = "µ" + key[1:]
    key = re.sub(r"[.,;]$", "", key)
    return key


def normalize_unit(raw_value: str, raw_unit: str, param_type: str) -> tuple[float, str]:
    """Convert any unit to canonical form for the parameter type.

    Args:
        raw_value: Numeric string from cell.
        raw_unit: Unit string from table.
        param_type: Parameter category (voltage, current, etc.).

    Returns:
        Tuple of normalized value and canonical unit.

    Raises:
        ValueError: If value or unit is invalid.
    """
    if not str(raw_value).strip():
        raise ValueError("Empty value")
    if param_type not in CANONICAL_UNITS and param_type != "other":
        raise ValueError(f"Unknown param_type '{param_type}'")

    unit_key = _normalize_unit_key(raw_unit)
    if unit_key not in UNIT_CONVERSION_TABLE:
        raise ValueError(f"Unknown unit '{raw_unit}' for param_type '{param_type}'")

    multiplier, canonical = UNIT_CONVERSION_TABLE[unit_key]
    numeric = float(str(raw_value).replace(",", ""))
    if multiplier is None:
        raise ValueError(f"Unit '{raw_unit}' requires special handling")
    return round(numeric * multiplier, 9), canonical
