"""Methodology classifier — validates and potentially overrides LLM methodology classification.

Uses keyword matching as a deterministic override when LLM classification is uncertain.
Priority order for multiple triggers: RF_highfreq > mixed_signal > power_management > through_hole > standard_SMD
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.schemas.intent import DesignMethodology

logger = logging.getLogger(__name__)

# Keyword triggers for each methodology (lowercase for matching)
METHODOLOGY_TRIGGERS: dict["DesignMethodology", list[str]] = {
    "RF_highfreq": [  # type: ignore
        "antenna",
        "rf",
        "2.4ghz",
        "5ghz",
        "bluetooth",
        "wifi",
        "lora",
        "ghz",
        "microwave",
        "wireless",
        "impedance matching",
        "2.4 ghz",
        "5 ghz",
    ],
    "power_management": [  # type: ignore
        "buck",
        "boost",
        "ldo",
        "regulator",
        "battery",
        "charger",
        "smps",
        "converter",
        "power supply",
        "voltage rail",
        "power management",
    ],
    "mixed_signal": [  # type: ignore
        "adc",
        "dac",
        "op-amp",
        "opamp",
        "analog",
        "sensor",
        "measurement",
        "precision",
        "instrumentation",
        "operational amplifier",
    ],
    "through_hole": [  # type: ignore
        "prototype",
        "hand solder",
        "tht",
        "dip",
        "through-hole",
        "through hole",
        "breadboard",
        "hand-solder",
    ],
}

# Priority order for conflicting triggers (highest priority first)
_METHODOLOGY_PRIORITY: list[str] = [
    "RF_highfreq",
    "mixed_signal",
    "power_management",
    "through_hole",
]


def _get_triggered_methodologies(prompt: str) -> list["DesignMethodology"]:
    """Return list of methodologies triggered by keywords in prompt."""
    from src.schemas.intent import DesignMethodology

    prompt_lower = prompt.lower()
    triggered: list[DesignMethodology] = []

    for methodology_name, keywords in METHODOLOGY_TRIGGERS.items():
        for keyword in keywords:
            if keyword in prompt_lower:
                # Map string name to enum
                methodology = DesignMethodology(methodology_name)
                if methodology not in triggered:
                    triggered.append(methodology)
                break  # Only need one keyword match per methodology

    return triggered


def validate_methodology(
    llm_result: "DesignMethodology",
    prompt: str,
) -> tuple["DesignMethodology", bool]:
    """Validate LLM methodology against keyword triggers.

    If keyword triggers for a DIFFERENT methodology appear in the prompt,
    override the LLM result and return was_overridden=True.

    If multiple methodologies trigger: use priority order:
    RF_highfreq > mixed_signal > power_management > through_hole > standard_SMD

    Args:
        llm_result: The methodology selected by the LLM
        prompt: The original user prompt

    Returns:
        Tuple of (final_methodology, was_overridden)

    Example:
        >>> from src.schemas.intent import DesignMethodology
        >>> llm_result = DesignMethodology.STANDARD_SMD
        >>> final, overridden = validate_methodology(
        ...     llm_result, "design a 2.4GHz patch antenna for drones"
        ... )
        >>> print(final)
        DesignMethodology.RF_HIGHFREQ
        >>> print(overridden)
        True
    """
    from src.schemas.intent import DesignMethodology

    triggered = _get_triggered_methodologies(prompt)

    # If LLM result is already triggered by keywords, trust it
    if llm_result in triggered:
        return llm_result, False

    # If no triggers found, trust LLM result (use standard_SMD as default if LLM gave something else)
    if not triggered:
        if llm_result == DesignMethodology.STANDARD_SMD:
            return llm_result, False
        # LLM picked something but no keywords - still trust LLM
        return llm_result, False

    # LLM result conflicts with keyword triggers - use highest priority trigger
    for priority_name in _METHODOLOGY_PRIORITY:
        for triggered_method in triggered:
            if triggered_method.value == priority_name:
                if triggered_method != llm_result:
                    logger.warning(
                        f"Methodology override: LLM chose {llm_result.value}, "
                        f"but keywords triggered {triggered_method.value}"
                    )
                    return triggered_method, True
                return llm_result, False

    # Fallback: return first triggered (shouldn't reach here)
    if triggered[0] != llm_result:
        logger.warning(
            f"Methodology override: LLM chose {llm_result.value}, "
            f"but keywords triggered {triggered[0].value}"
        )
        return triggered[0], True

    return llm_result, False
