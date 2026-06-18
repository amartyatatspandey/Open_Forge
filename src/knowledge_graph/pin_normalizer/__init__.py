"""Pin normalization package (Problem 2 / P2).

Normalizes raw pin names from ComponentDatasheets to canonical functions.

Three-tier process:
1. Dictionary lookup (confidence=1.0)
2. Context resolution using adjacent pins (confidence=0.90)
3. LLM fallback via Qwen2.5-7B (variable confidence)

Never mutates input objects. Always returns new ComponentDatasheets
with updated pins via model_copy().

Public API:
    normalize_pins(datasheets, config) -> list[ComponentDatasheet]

Example:
    >>> from src.knowledge_graph.pin_normalizer import normalize_pins
    >>> from src.config import get_config
    >>> config = get_config()
    >>> normalized = normalize_pins([ds1, ds2], config)
    >>> normalized[0].pins[0].normalized_function
    'POWER_POSITIVE'
"""

from __future__ import annotations

from src.knowledge_graph.pin_normalizer.normalizer import normalize_pins

__all__ = ["normalize_pins"]
