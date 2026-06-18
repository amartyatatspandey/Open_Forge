"""Context-based pin normalization for ambiguous pins.

Uses adjacent pin names to resolve ambiguous pin names like "CLK"
which could be SPI or I2C depending on neighboring pins.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.knowledge_graph.pin_normalizer.dictionary import PIN_NORMALIZATION_MAP

logger = logging.getLogger(__name__)

# Context indicators for different protocols
SPI_INDICATORS: set[str] = {"MOSI", "MISO", "CS", "CSB", "SS", "NSS", "NCS", "SDI", "SDO", "COPI", "CIPO"}
I2C_INDICATORS: set[str] = {"SDA", "SCL"}
UART_INDICATORS: set[str] = {"TX", "TXD", "RX", "RXD", "RTS", "CTS"}
CAN_INDICATORS: set[str] = {"CANH", "CANL", "CAN_H", "CAN_L"}
USB_INDICATORS: set[str] = {"DP", "DM", "D+", "D-", "VBUS", "ID"}


def _clean_pin_name(raw_name: str) -> str:
    """Clean a pin name for comparison.

    Args:
        raw_name: Raw pin name

    Returns:
        Cleaned uppercase name with trailing digits and active-low prefixes removed
    """
    clean = raw_name.strip().upper()
    # Remove active-low prefixes (! or N)
    if clean.startswith("!"):
        clean = clean[1:]
    elif clean.startswith("N") and len(clean) > 1:
        # Check if it's an active-low indicator (N followed by valid pin name)
        without_n = clean[1:]
        if without_n not in ("A", "O", "C"):
            clean = without_n
    # Remove trailing digits
    while clean and clean[-1].isdigit():
        clean = clean[:-1]
    return clean


def resolve_with_context(
    raw_name: str,
    adjacent_pin_names: list[str],
) -> Optional[str]:
    """Resolve ambiguous pin using context from adjacent pins.

    Uses heuristics based on neighboring pin names to disambiguate
    pin names that could have multiple meanings (e.g., CLK could be
    SPI or I2C depending on whether SDA or MOSI is present).

    Args:
        raw_name: The ambiguous pin name to resolve
        adjacent_pin_names: List of all other pin names in the same component

    Returns:
        Canonical function string if context provides clear resolution,
        None if still ambiguous

    Examples:
        >>> resolve_with_context("CLK", ["SDA", "SCL", "INT"])
        'I2C_CLOCK'
        >>> resolve_with_context("CLK", ["MOSI", "MISO", "CS"])
        'SPI_CLOCK'
        >>> resolve_with_context("CLK", ["ANT", "GND"])  # Ambiguous
        None
    """
    clean_name = _clean_pin_name(raw_name)

    # Clean all adjacent pin names for comparison
    clean_adjacent = [_clean_pin_name(p) for p in adjacent_pin_names]

    # CLK ambiguity: could be SPI or I2C
    if clean_name in ("CLK", "SCLK", "CLOCK", "CK"):
        has_spi = any(p in SPI_INDICATORS for p in clean_adjacent)
        has_i2c = any(p in I2C_INDICATORS for p in clean_adjacent)

        if has_spi and not has_i2c:
            logger.debug(f"Context resolved CLK → SPI_CLOCK (SPI indicators present)")
            return "SPI_CLOCK"
        elif has_i2c and not has_spi:
            logger.debug(f"Context resolved CLK → I2C_CLOCK (I2C indicators present)")
            return "I2C_CLOCK"
        else:
            # Both or neither present - still ambiguous
            return None

    # SCL ambiguity: could be I2C or SPI
    if clean_name == "SCL":
        has_i2c = any(p in I2C_INDICATORS for p in clean_adjacent)
        has_spi = any(p in SPI_INDICATORS for p in clean_adjacent)

        if has_i2c and not has_spi:
            return "I2C_CLOCK"
        elif has_spi and not has_i2c:
            # Some chips use SCL for SPI (unusual but possible)
            return "SPI_CLOCK"
        # Ambiguous
        return None

    # DATA ambiguity: could be many things
    if clean_name in ("DATA", "D", "DAT"):
        has_spi = any(p in SPI_INDICATORS for p in clean_adjacent)
        has_i2c = any(p in I2C_INDICATORS for p in clean_adjacent)
        has_uart = any(p in UART_INDICATORS for p in clean_adjacent)

        if has_spi and not has_i2c and not has_uart:
            return "SPI_DATA_IN"  # Default assumption for SPI
        elif has_i2c and not has_spi and not has_uart:
            return "I2C_DATA"
        elif has_uart and not has_spi and not has_i2c:
            # Check if TX or RX present to determine direction
            has_tx = any(p in ("TX", "TXD", "UART_TX") for p in clean_adjacent)
            if has_tx:
                return "UART_RECEIVE"
            else:
                return "UART_TRANSMIT"
        # Ambiguous
        return None

    # CS/SS ambiguity: could be SPI chip select or something else
    if clean_name in ("CS", "SS", "CSB", "NSS", "NCS"):
        has_spi = any(p in SPI_INDICATORS for p in clean_adjacent)
        if has_spi:
            # Check for active-low indicators
            if raw_name.strip().upper() in ("NCS", "CSB", "NSS", "CSN", "!CS"):
                return "SPI_CHIP_SELECT"
            return "SPI_CHIP_SELECT"

    # INT ambiguity: could be interrupt or something else
    if clean_name in ("INT", "IRQ"):
        # Most common interpretation is interrupt
        return "INTERRUPT"

    # EN ambiguity: could be enable or something else
    if clean_name in ("EN", "ENABLE"):
        # Check for active-low
        clean_raw = raw_name.strip().upper()
        if clean_raw.startswith("N") or clean_raw.startswith("!"):
            return "ENABLE_ACTIVE_LOW"
        return "ENABLE"

    # RST/RESET ambiguity
    if clean_name in ("RST", "RESET"):
        clean_raw = raw_name.strip().upper()
        if clean_raw.startswith("N") or clean_raw.startswith("!"):
            return "RESET"  # Active-low indicated by name prefix
        return "RESET"

    # No context resolution available for this pin
    return None
