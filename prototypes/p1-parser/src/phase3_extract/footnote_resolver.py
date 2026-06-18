"""Resolve footnote markers to footnote text on extracted values."""

from __future__ import annotations

import re

from src.schemas.datasheet import AbsoluteMaxRating, ElectricalParameter, PinDefinition

_FOOTNOTE_PATTERN = re.compile(r"(\(\d+\)|\*|†|‡|§)")


def extract_footnote_marker(text: str) -> str | None:
    """Extract footnote marker from text."""
    match = _FOOTNOTE_PATTERN.search(text)
    return match.group(1) if match else None


def _link_value_footnotes(value, footnote_map: dict[str, str]) -> None:
    if value is None or value.footnote is not None:
        return
    marker = extract_footnote_marker(value.raw_text)
    if marker and marker in footnote_map:
        value.footnote = footnote_map[marker]


def resolve_footnotes_in_extraction(
    parameters: list[ElectricalParameter],
    pins: list[PinDefinition],
    abs_max_ratings: list[AbsoluteMaxRating],
    footnote_map: dict[str, str] | None = None,
) -> None:
    """Post-process extracted data to link footnote text in-place."""
    if not footnote_map:
        return

    for param in parameters:
        for value in (param.min_value, param.typ_value, param.max_value):
            _link_value_footnotes(value, footnote_map)

    for rating in abs_max_ratings:
        _link_value_footnotes(rating.max_value, footnote_map)

    for pin in pins:
        if pin.description:
            marker = extract_footnote_marker(pin.description)
            if marker and marker in footnote_map:
                pin.description = f"{pin.description} — {footnote_map[marker]}"
