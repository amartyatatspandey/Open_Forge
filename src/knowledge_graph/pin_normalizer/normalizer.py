"""Pin normalization orchestrator.

Coordinates the three-tier normalization process:
1. Dictionary lookup (highest confidence)
2. Context resolution (medium confidence)
3. LLM fallback (variable confidence)

Never mutates input objects. Always returns new ComponentDatasheets with
model_copy() applied to update pins.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from src.knowledge_graph.pin_normalizer.context_resolver import resolve_with_context
from src.knowledge_graph.pin_normalizer.dictionary import normalize_from_dictionary
from src.knowledge_graph.pin_normalizer.llm_fallback import normalize_via_llm
from src.schemas.datasheet import ComponentDatasheet, PinDefinition

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Confidence levels for different tiers
DICTIONARY_CONFIDENCE = 1.0
CONTEXT_CONFIDENCE = 0.90


def _normalize_single_pin(
    pin: PinDefinition,
    adjacent_pin_names: list[str],
    config: Config,
) -> Tuple[Optional[str], float, str]:
    """Normalize a single pin through all three tiers.

    Args:
        pin: The PinDefinition to normalize
        adjacent_pin_names: Names of other pins in the same component
        config: Application configuration

    Returns:
        Tuple of (canonical, confidence, method)
    """
    raw_name = pin.raw_name

    # Tier 1: Dictionary lookup
    canonical = normalize_from_dictionary(raw_name)
    if canonical is not None:
        return canonical, DICTIONARY_CONFIDENCE, "dictionary"

    # Tier 2: Context resolution
    canonical = resolve_with_context(raw_name, adjacent_pin_names)
    if canonical is not None:
        return canonical, CONTEXT_CONFIDENCE, "context"

    # Tier 3: LLM fallback
    canonical, confidence, method = normalize_via_llm(raw_name, config)
    return canonical, confidence, method


def _normalize_pins_in_datasheet(
    datasheet: ComponentDatasheet,
    config: Config,
) -> ComponentDatasheet:
    """Normalize all pins in a single ComponentDatasheet.

    Processes each pin through dictionary → context → LLM tiers.
    Pins that fail all tiers get normalized_function=None and trigger
    a review flag.

    Args:
        datasheet: ComponentDatasheet to process
        config: Application configuration

    Returns:
        New ComponentDatasheet with normalized pins (never mutates input)
    """
    review_flags = list(datasheet.review_flags or [])
    normalized_pins: list[PinDefinition] = []

    # Collect all pin names for context resolution
    all_pin_names = [p.raw_name for p in datasheet.pins]

    for pin in datasheet.pins:
        # Get adjacent pins (all other pins)
        adjacent = [p for p in all_pin_names if p != pin.raw_name]

        # Normalize through all tiers
        canonical, confidence, method = _normalize_single_pin(pin, adjacent, config)

        if canonical is not None:
            # Successful normalization
            new_pin = pin.model_copy(update={
                "normalized_function": canonical,
                "normalization_confidence": confidence,
            })
            normalized_pins.append(new_pin)
            logger.debug(
                f"Normalized pin {pin.pin_number} ({pin.raw_name}): "
                f"{canonical} via {method}"
            )
        else:
            # All tiers failed
            new_pin = pin.model_copy(update={
                "normalized_function": None,
                "normalization_confidence": confidence,  # Usually 0.0
            })
            normalized_pins.append(new_pin)

            # Add review flag
            flag = f"Pin {pin.pin_number} ({pin.raw_name}): normalization failed"
            review_flags.append(flag)
            logger.warning(flag)

    # Create new datasheet with updated pins and review flags
    return datasheet.model_copy(update={
        "pins": normalized_pins,
        "review_flags": review_flags,
    })


def normalize_pins(
    datasheets: list[ComponentDatasheet],
    config: Config,
) -> list[ComponentDatasheet]:
    """Normalize pins across multiple ComponentDatasheets.

    Returns new list of ComponentDatasheets with normalized_function and
    normalization_confidence populated on every PinDefinition.
    Never raises. Pins that cannot be normalized get normalized_function=None
    and a review_flag added to the parent ComponentDatasheet.

    Three-tier normalization process per pin:
    1. Dictionary lookup (confidence=1.0)
    2. Context resolution (confidence=0.90)
    3. LLM fallback (variable confidence)

    Args:
        datasheets: List of ComponentDatasheets to process
        config: Application configuration

    Returns:
        New list of ComponentDatasheets with normalized pins.
        Never mutates input objects.

    Example:
        >>> from src.knowledge_graph.pin_normalizer import normalize_pins
        >>> from src.config import get_config
        >>> config = get_config()
        >>> normalized = normalize_pins([ds1, ds2], config)
        >>> normalized[0].pins[0].normalized_function
        'POWER_POSITIVE'
    """
    if not datasheets:
        return []

    logger.info(f"Normalizing pins for {len(datasheets)} datasheets")

    normalized_datasheets: list[ComponentDatasheet] = []
    total_pins = 0
    normalized_count = 0
    failed_count = 0

    for datasheet in datasheets:
        try:
            pin_count = len(datasheet.pins)
            total_pins += pin_count

            # Normalize this datasheet
            normalized = _normalize_pins_in_datasheet(datasheet, config)
            normalized_datasheets.append(normalized)

            # Count results
            for pin in normalized.pins:
                if pin.normalized_function is not None:
                    normalized_count += 1
                else:
                    failed_count += 1

        except Exception as e:
            # Should not happen given our design, but handle gracefully
            logger.error(
                f"Unexpected error normalizing datasheet "
                f"{datasheet.component_id}: {e}"
            )
            # Return original datasheet as fallback
            normalized_datasheets.append(datasheet)

    logger.info(
        f"Pin normalization complete: {normalized_count}/{total_pins} successful, "
        f"{failed_count} failed, {len(normalized_datasheets)} datasheets processed"
    )

    return normalized_datasheets
