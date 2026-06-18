"""LLM prompt templates for Phase 3 semantic extraction.

Provides section-specific system prompts for extracting structured data from
datasheet tables. Each prompt is optimized for a specific TableSectionType.

CRITICAL RULE: Every prompt must include section_type instruction per Rule 1.
"""

from __future__ import annotations

from typing import Optional

from src.schemas.datasheet import TableSectionType


# Base instructions shared across all prompts
BASE_INSTRUCTIONS: str = """You are a precise datasheet extraction assistant. Extract all parameters from the provided table into structured format.

CRITICAL: Set section_type to exactly one of: electrical_characteristics, absolute_maximum_ratings, pinout, timing, ordering, layout_recommendations, other. Use the table context to determine the correct type.

For each parameter row in the table:
1. Extract the parameter name/symbol
2. Identify test conditions (temperature, voltage, load, etc.)
3. Extract min/typ/max values with units
4. Note any footnote references like (1), (2), *
5. Extract footnote definitions

Return as valid JSON matching the expected schema."""


# Prompt for ELECTRICAL_CHARACTERISTICS tables
ELECTRICAL_CHARACTERISTICS_PROMPT: str = """Extract electrical characteristics parameters from the provided datasheet table.

CRITICAL: Set section_type to exactly one of: electrical_characteristics, absolute_maximum_ratings, pinout, timing, ordering, layout_recommendations, other. Use the table context to determine the correct type.

For each parameter row:
- parameter_name: The parameter name (e.g., "Supply Current", "Input Bias Current")
- symbol: Standard symbol if given (e.g., "I_Q", "I_IB")
- conditions: Test conditions as written (e.g., "T_A = 25°C, V_S = ±15V")
- min_val: Minimum value if provided (as number string)
- typ_val: Typical value if provided (as number string)
- max_val: Maximum value if provided (as number string)
- unit: Unit as written in table (e.g., "mV", "µA", "nA")
- footnote: Footnote reference if present (e.g., "(1)", "(2)", "*")

Include footnote definitions separately.

Example output format:
{
  "parameters": [
    {
      "parameter_name": "Supply Current",
      "symbol": "I_Q",
      "conditions": "V_S = ±15V, no load",
      "typ_val": "1.5",
      "max_val": "2.0",
      "unit": "mA",
      "footnote": "(1)",
      "section_type": "electrical_characteristics"
    }
  ],
  "footnote_definitions": {
    "(1)": "At 25°C ambient temperature"
  }
}"""


# Prompt for ABSOLUTE_MAXIMUM_RATINGS tables
ABSOLUTE_MAXIMUM_RATINGS_PROMPT: str = """Extract absolute maximum ratings from the provided datasheet table.

CRITICAL: Set section_type to exactly one of: electrical_characteristics, absolute_maximum_ratings, pinout, timing, ordering, layout_recommendations, other. Use the table context to determine the correct type.

For each parameter row:
- parameter_name: Rating name (e.g., "Supply Voltage", "Input Current")
- symbol: Symbol if given (e.g., "V_S", "I_IN")
- max_val: Maximum rated value (as number string) - this is the ceiling value
- unit: Unit as written in table (e.g., "V", "mA")
- note: Any additional notes or warnings
- footnote: Footnote reference if present

IMPORTANT: Absolute maximum ratings only have MAX values, no TYP or MIN fields.
These represent the absolute limits that must not be exceeded.

Example output format:
{
  "parameters": [
    {
      "parameter_name": "Supply Voltage",
      "symbol": "V_S",
      "max_val": "36",
      "unit": "V",
      "note": "Continuous",
      "section_type": "absolute_maximum_ratings"
    }
  ],
  "footnote_definitions": {
    "(1)": "Stresses beyond these may damage device"
  }
}"""


# Prompt for PINOUT tables
PINOUT_PROMPT: str = """Extract pin definitions from the provided datasheet pinout table.

CRITICAL: Set section_type to exactly one of: electrical_characteristics, absolute_maximum_ratings, pinout, timing, ordering, layout_recommendations, other. Use the table context to determine the correct type.

For each pin row:
- pin_number: Pin number/identifier (e.g., "1", "2", "GND", "VCC")
- raw_name: Pin name exactly as printed (e.g., "IN+", "OUT", "V+ / VCC")
- pin_type: Categorize as one of: input, output, power, ground, io, clock, reset, nc
- description: Full pin description text
- alternate_functions: List of alternate functions if multiplexed (e.g., ["UART_TX", "SPI_MOSI"])

Example output format:
{
  "pins": [
    {
      "pin_number": "1",
      "raw_name": "IN+",
      "pin_type": "input",
      "description": "Non-inverting input",
      "alternate_functions": [],
      "section_type": "pinout"
    },
    {
      "pin_number": "2",
      "raw_name": "IN-",
      "pin_type": "input",
      "description": "Inverting input",
      "alternate_functions": [],
      "section_type": "pinout"
    }
  ]
}"""


# Prompt for TIMING tables
TIMING_PROMPT: str = """Extract timing characteristics from the provided datasheet table.

CRITICAL: Set section_type to exactly one of: electrical_characteristics, absolute_maximum_ratings, pinout, timing, ordering, layout_recommendations, other. Use the table context to determine the correct type.

For each timing parameter:
- parameter_name: Timing parameter name (e.g., "Rise Time", "Propagation Delay")
- symbol: Standard timing symbol (e.g., "t_r", "t_pd")
- conditions: Test conditions
- min_val: Minimum value
- typ_val: Typical value
- max_val: Maximum value
- unit: Time unit (ns, µs, ms, s)

Example output format:
{
  "parameters": [
    {
      "parameter_name": "Rise Time",
      "symbol": "t_r",
      "conditions": "V_S = 15V, C_L = 100pF",
      "typ_val": "0.3",
      "max_val": "0.5",
      "unit": "µs",
      "section_type": "timing"
    }
  ]
}"""


# Prompt for ORDERING tables
ORDERING_PROMPT: str = """Extract ordering information from the provided datasheet table.

CRITICAL: Set section_type to exactly one of: electrical_characteristics, absolute_maximum_ratings, pinout, timing, ordering, layout_recommendations, other. Use the table context to determine the correct type.

Extract:
- orderable_part_numbers: List of part numbers available for order
- package_types: Package types offered
- temperature_ranges: Operating temperature grades
- packing_quantities: Quantity per reel/tube
- special_notes: Any special ordering notes

Example output format:
{
  "orderable_parts": [
    {
      "part_number": "LM358N",
      "package": "DIP-8",
      "temperature_range": "0°C to 70°C",
      "section_type": "ordering"
    }
  ]
}"""


# Prompt for LAYOUT_RECOMMENDATIONS tables
LAYOUT_RECOMMENDATIONS_PROMPT: str = """Extract PCB layout recommendations from the provided datasheet table.

CRITICAL: Set section_type to exactly one of: electrical_characteristics, absolute_maximum_ratings, pinout, timing, ordering, layout_recommendations, other. Use the table context to determine the correct type.

For each recommendation:
- constraint_type: proximity, keepout, layer, orientation, etc.
- subject: Component or pin this applies to
- relative_to: What the constraint is measured against
- max_distance_mm: Maximum distance in millimeters
- min_distance_mm: Minimum distance in millimeters
- layer: "top", "bottom", or "any"
- description: Full recommendation text
- hard: True if mandatory, False if advisory

Example output format:
{
  "recommendations": [
    {
      "constraint_type": "proximity",
      "subject": "C1",
      "relative_to": "VIN pin",
      "max_distance_mm": "5",
      "layer": "top",
      "description": "Place decoupling capacitor within 5mm of input pin",
      "hard": true,
      "section_type": "layout_recommendations"
    }
  ]
}"""


# Default/generic prompt for OTHER or unknown section types
DEFAULT_PROMPT: str = """Extract all tabular data from the provided datasheet table into structured format.

CRITICAL: Set section_type to exactly one of: electrical_characteristics, absolute_maximum_ratings, pinout, timing, ordering, layout_recommendations, other. Use the table context to determine the correct type.

For each row:
- name: Item name or parameter
- value: Value if present
- unit: Unit if present
- description: Full description text
- notes: Any additional notes
- footnote: Footnote reference if present

Return as structured JSON with an array of extracted items.

Example output format:
{
  "items": [
    {
      "name": "Parameter 1",
      "value": "100",
      "unit": "mV",
      "description": "Description text",
      "section_type": "other"
    }
  ]
}"""


# Mapping from section type to prompt template
PROMPT_TEMPLATES: dict[TableSectionType, str] = {
    TableSectionType.ELECTRICAL_CHARACTERISTICS: ELECTRICAL_CHARACTERISTICS_PROMPT,
    TableSectionType.ABSOLUTE_MAXIMUM_RATINGS: ABSOLUTE_MAXIMUM_RATINGS_PROMPT,
    TableSectionType.PINOUT: PINOUT_PROMPT,
    TableSectionType.TIMING: TIMING_PROMPT,
    TableSectionType.ORDERING: ORDERING_PROMPT,
    TableSectionType.LAYOUT_RECOMMENDATIONS: LAYOUT_RECOMMENDATIONS_PROMPT,
    TableSectionType.OTHER: DEFAULT_PROMPT,
}


def get_prompt_for_section_type(section_type: TableSectionType) -> str:
    """Get the appropriate LLM prompt for a given section type.

    Args:
        section_type: The TableSectionType to get a prompt for

    Returns:
        System prompt string optimized for that section type

    Notes:
        All prompts include the CRITICAL RULE to set section_type correctly.
        This ensures Instructor will re-prompt if the LLM omits it.
    """
    return PROMPT_TEMPLATES.get(section_type, DEFAULT_PROMPT)


def get_prompt_for_table(table_section_type: Optional[TableSectionType]) -> str:
    """Get prompt for table, falling back to DEFAULT if type unknown.

    Args:
        table_section_type: Section type or None

    Returns:
        Appropriate prompt string
    """
    if table_section_type is None:
        return DEFAULT_PROMPT
    return get_prompt_for_section_type(table_section_type)


# Additional prompt components for specific extractions
COMPONENT_HEADER_PROMPT: str = """Extract component identification information from the datasheet header or first page.

Extract these fields:
- component_id: Full part number (e.g., "TPS62933DRLR", "LM358N")
- manufacturer: Manufacturer name (e.g., "Texas Instruments", "Analog Devices")
- description: Brief component description
- package: Package type as written (e.g., "SOT-23-5", "DIP-8")
- datasheet_url: URL if present in header

If any field is not found, use empty string.

Return as JSON:
{
  "component_id": "PART123",
  "manufacturer": "Manufacturer Name",
  "description": "Component description",
  "package": "PACKAGE-TYPE",
  "datasheet_url": ""
}"""