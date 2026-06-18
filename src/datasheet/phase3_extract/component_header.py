"""Component header extraction for Phase 3.

Extracts component identity fields (component_id, manufacturer, description, package)
from first-page header text or header grids.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.datasheet.utils import normalize_package

logger = logging.getLogger(__name__)


def _extract_from_text(text: str) -> dict[str, str]:
    """Extract component info from raw header text using heuristics.

    Args:
        text: Header text from first page

    Returns:
        Dict with component_id, manufacturer, description, package fields
    """
    result = {
        "component_id": "",
        "manufacturer": "",
        "description": "",
        "package": "",
    }
    
    # Simple heuristic extraction
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not lines:
        return result
    
    # First non-empty line often contains part number
    for line in lines[:5]:  # Check first 5 lines
        # Look for patterns like "LM358", "TPS62933", "OPA2134"
        import re
        match = re.search(r'\b([A-Z]{2,}\d{3,}[A-Z]*)\b', line)
        if match and len(match.group(1)) >= 4:
            result["component_id"] = match.group(1)
            break
    
    # Look for manufacturer
    manufacturers = [
        "Texas Instruments", "TI", "Analog Devices", "ADI",
        "STMicroelectronics", "ST", "Microchip", "NXP", "Infineon",
        "ON Semiconductor", "onsemi", "Renesas", "Maxim", "Linear Technology",
    ]
    
    for mfr in manufacturers:
        if mfr.lower() in text.lower():
            result["manufacturer"] = mfr
            break
    
    # Look for description (often after part number)
    for line in lines[:10]:
        if any(word in line.lower() for word in [
            "amplifier", "regulator", "converter", "sensor",
            "driver", "controller", "interface", "transceiver"
        ]):
            result["description"] = line[:200]  # Limit length
            break
    
    # Look for package in text
    for line in lines:
        import re
        # Common package patterns
        pkg_match = re.search(r'\b(SOT-?\d{2}-?\d|SOIC-?\d{1,2}|DIP-?\d{1,2}|QFN-?\d{1,2}|TSSOP-?\d{1,2}|TO-?\d{1,3})\b', line, re.IGNORECASE)
        if pkg_match:
            result["package"] = pkg_match.group(1).upper()
            break
    
    return result


class ComponentHeaderInfo:
    """Container for extracted component header information."""
    
    def __init__(
        self,
        component_id: str = "",
        manufacturer: str = "",
        description: str = "",
        raw_package: str = "",
        package_review_required: bool = False,
    ):
        self.component_id = component_id
        self.manufacturer = manufacturer
        self.description = description
        self.raw_package = raw_package
        self.package_review_required = package_review_required
        self.normalized_package: str = raw_package
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for ComponentDatasheet creation."""
        return {
            "component_id": self.component_id,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "package": self.normalized_package,
        }
    
    def get_review_flags(self) -> list[str]:
        """Get list of review flags for this extraction."""
        flags = []
        
        if not self.component_id:
            flags.append("Component ID not extracted from header")
        
        if not self.manufacturer:
            flags.append("Manufacturer not extracted from header")
        
        if not self.description:
            flags.append("Description not extracted from header")
        
        if self.package_review_required:
            flags.append(f"Package normalization uncertain: {self.raw_package}")
        
        return flags


def extract_component_header(
    header_text: str,
    use_llm: bool = False,
) -> ComponentHeaderInfo:
    """Extract component identity from header text.

    Extracts component_id, manufacturer, description, and package from
    the first page header text of a datasheet. Uses rule-based heuristics
    by default, optionally LLM-assisted.

    Args:
        header_text: Raw text from first page header
        use_llm: If True, use LLM for extraction (currently not implemented)

    Returns:
        ComponentHeaderInfo with extracted and normalized fields

    Rule 2: normalize_package() must be called on every extracted package string.
    """
    logger.info("Extracting component header information")
    
    # Extract raw values using heuristics
    extracted = _extract_from_text(header_text)
    
    raw_package = extracted.get("package", "")
    
    # Rule 2: normalize_package() must be called (only if we have a package)
    if raw_package:
        normalized_package, needs_review = normalize_package(raw_package)
        if needs_review:
            logger.warning(f"Package normalization uncertain: '{raw_package}' -> '{normalized_package}'")
    else:
        normalized_package = ""
        needs_review = False  # Empty package doesn't need normalization review
    
    return ComponentHeaderInfo(
        component_id=extracted.get("component_id", ""),
        manufacturer=extracted.get("manufacturer", ""),
        description=extracted.get("description", ""),
        raw_package=raw_package,
        package_review_required=needs_review,
    )