"""Table-type-aware extraction prompts for future LLM path."""

from __future__ import annotations

SYSTEM_PROMPTS = {
    "electrical_characteristics": (
        "Extract electrical characteristics as structured JSON. "
        "Each parameter must include name, min, typ, max, unit, and conditions."
    ),
    "pinout": (
        "Extract pin definitions as structured JSON. "
        "Each pin must include pin_number, pin_name, pin_type, and description."
    ),
    "absolute_maximum_ratings": (
        "Extract absolute maximum ratings as structured JSON. "
        "Each entry must include parameter name, max value, and unit."
    ),
}


def build_extraction_prompt(
    section_type: str,
    grid_rows: list[list[str]],
    footnote_map: dict[str, str] | None = None,
) -> str:
    """Build a user prompt for LLM extraction from grid rows."""
    system = SYSTEM_PROMPTS.get(
        section_type,
        "Extract tabular datasheet data as structured JSON.",
    )
    rows_text = "\n".join(" | ".join(row) for row in grid_rows[:20])
    footnotes = ""
    if footnote_map:
        footnotes = "\nFootnotes:\n" + "\n".join(
            f"{marker}: {text}" for marker, text in footnote_map.items()
        )
    return f"{system}\n\nTable:\n{rows_text}{footnotes}"
