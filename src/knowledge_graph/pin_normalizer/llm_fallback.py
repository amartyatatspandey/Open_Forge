"""LLM-based pin normalization fallback.

Uses Qwen2.5-7B via Instructor to normalize pin names that are not found
in the dictionary. Provides confidence scoring for normalization decisions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# List of valid canonical functions the LLM can choose from
VALID_CANONICAL_FUNCTIONS: list[str] = [
    "POWER_POSITIVE",
    "POWER_GROUND",
    "POWER_INPUT",
    "POWER_INPUT_POSITIVE",
    "POWER_INPUT_NEGATIVE",
    "SPI_CLOCK",
    "SPI_DATA_IN",
    "SPI_DATA_OUT",
    "SPI_CHIP_SELECT",
    "I2C_DATA",
    "I2C_CLOCK",
    "UART_TRANSMIT",
    "UART_RECEIVE",
    "ENABLE",
    "ENABLE_ACTIVE_LOW",
    "RESET",
    "INTERRUPT",
    "PWM_OUTPUT",
    "NO_CONNECT",
    "RF_OUTPUT",
    "ANALOG_INPUT_POSITIVE",
    "ANALOG_INPUT_NEGATIVE",
    "ANALOG_OUTPUT",
    "FEEDBACK",
    "SWITCH_NODE",
    "BOOTSTRAP",
    "GPIO",
    "VOLTAGE_REFERENCE",
    "CURRENT_SENSE",
    "CRYSTAL",
    "CLOCK_INPUT",
    "CLOCK_OUTPUT",
    "JTAG_CLOCK",
    "JTAG_DATA_IN",
    "JTAG_DATA_OUT",
    "SWD_CLOCK",
    "SWD_DATA",
    "CAN_HIGH",
    "CAN_LOW",
    "UNKNOWN",
]

# Minimum confidence threshold for accepting LLM normalization
MIN_LLM_CONFIDENCE = 0.70


class NormalizationOutput(BaseModel):
    """Schema for LLM normalization response.

    Instructor-enforced output format for pin normalization.
    """

    model_config = {"extra": "forbid"}

    canonical: str = Field(
        description="The canonical function name from the approved list",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the normalization decision",
    )


SYSTEM_PROMPT = """You are an electronics engineer specializing in PCB component pin naming conventions.

Given a PCB component pin name, return the most appropriate canonical function from this list:
[POWER_POSITIVE, POWER_GROUND, POWER_INPUT, SPI_CLOCK, SPI_DATA_IN, SPI_DATA_OUT,
SPI_CHIP_SELECT, I2C_DATA, I2C_CLOCK, UART_TRANSMIT, UART_RECEIVE, ENABLE, RESET,
INTERRUPT, PWM_OUTPUT, NO_CONNECT, RF_OUTPUT, ANALOG_INPUT_POSITIVE,
ANALOG_INPUT_NEGATIVE, ANALOG_OUTPUT, FEEDBACK, SWITCH_NODE, BOOTSTRAP, GPIO,
VOLTAGE_REFERENCE, CURRENT_SENSE, CRYSTAL, CLOCK_INPUT, CLOCK_OUTPUT, JTAG_CLOCK,
JTAG_DATA_IN, JTAG_DATA_OUT, SWD_CLOCK, SWD_DATA, CAN_HIGH, CAN_LOW, UNKNOWN]

Return UNKNOWN if you are not confident about the normalization.
Consider:
- Power pins typically start with V (VDD, VCC, VIN)
- Ground pins start with G or are named GND, VSS
- SPI pins often contain SCK/SCLK, MOSI, MISO, CS
- I2C pins are SDA and SCL
- UART pins are TX/RX or TXD/RXD
- Analog input pins often have IN+ or INP in the name
- Reset pins contain RST or RESET
- Enable pins contain EN or ENABLE

Respond with the canonical function name and your confidence (0.0-1.0)."""


def _load_llm(config: Config) -> Optional[object]:
    """Load the Qwen2.5-7B model via Instructor.

    Args:
        config: Application configuration with model paths

    Returns:
        Instructor client or None if model unavailable
    """
    try:
        import instructor
        from openai import OpenAI
    except ImportError:
        logger.warning("instructor or openai not available for LLM fallback")
        return None
    # Placeholder: In production, this would load Qwen2.5-7B-Instruct
    # For now, return None to trigger unavailable path
    logger.debug("LLM model loading not implemented in prototype")
    return None


def normalize_via_llm(
    raw_name: str,
    config: Config,
) -> Tuple[Optional[str], float, str]:
    """Normalize a pin name using LLM fallback.

    Uses Qwen2.5-7B via Instructor to determine the canonical function
    for unknown pin names. Returns None if confidence is too low or
    if the model is unavailable.

    Args:
        raw_name: The raw pin name to normalize
        config: Application configuration

    Returns:
        Tuple of (canonical_function, confidence, method):
        - canonical_function: Normalized function or None if failed
        - confidence: Confidence score (0.0-1.0)
        - method: "llm_fallback" on success, "llm_unavailable" if model missing,
                  or "llm_low_confidence" if confidence below threshold

    Example:
        >>> canonical, conf, method = normalize_via_llm("MY_CUSTOM_PIN", config)
        >>> canonical is None or isinstance(canonical, str)
        True
    """
    # Try to load LLM
    llm_client = _load_llm(config)

    if llm_client is None:
        logger.warning(f"LLM unavailable for pin normalization: {raw_name}")
        return None, 0.0, "llm_unavailable"

    try:
        # In production, this would call the LLM via Instructor
        # For prototype, simulate LLM response
        logger.debug(f"Would call LLM for pin: {raw_name}")

        # Placeholder: Return UNKNOWN with low confidence
        # Real implementation would use instructor to get structured output
        result = NormalizationOutput(
            canonical="UNKNOWN",
            confidence=0.5,
        )

        # Validate the canonical function is in our approved list
        if result.canonical not in VALID_CANONICAL_FUNCTIONS:
            logger.warning(
                f"LLM returned invalid canonical function: {result.canonical}"
            )
            return None, result.confidence, "llm_invalid_output"

        # Check confidence threshold
        if result.canonical == "UNKNOWN" or result.confidence < MIN_LLM_CONFIDENCE:
            return None, result.confidence, "llm_low_confidence"

        return result.canonical, result.confidence, "llm_fallback"

    except Exception as e:
        logger.error(f"LLM normalization failed for {raw_name}: {e}")
        return None, 0.0, "llm_error"
